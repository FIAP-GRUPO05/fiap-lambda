import json
import os
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, EndpointConnectionError
from codeemail import main


class EmailLambdaTest(unittest.TestCase):
    def setUp(self):
        self.settings = patch.dict(os.environ, {"EMAIL_PROVIDER": "SES", "ENVIRONMENT": "develop",
                                    "NOTIFICATIONS_EMAIL_FROM": "oficina@example.test"})
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.message = {"to": "client@example.test", "subject": "OS", "body": "Concluida",
                        "html": False, "correlationId": "request-123"}

    @patch.object(main, "_ses")
    def test_ses_plain_and_html_have_one_recipient_and_utf8(self, ses):
        ses.return_value.send_email.return_value = {"MessageId": "ses-id"}
        for html in (False, True):
            with self.subTest(html=html), self.assertLogs(main.logger, level="INFO") as logs:
                response = main.lambda_handler({**self.message, "html": html}, MagicMock(aws_request_id="lambda-id"))
                payload = ses.return_value.send_email.call_args.kwargs
                self.assertEqual(payload["Destination"], {"ToAddresses": ["client@example.test"]})
                self.assertEqual(payload["FromEmailAddress"], "oficina@example.test")
                self.assertEqual(payload["Content"]["Simple"]["Body"]["Html" if html else "Text"]["Charset"], "UTF-8")
                self.assertEqual(response, {"statusCode": 200, "messageId": "ses-id"})
                self.assertEqual(logs.records[0].correlationId, "request-123")
                self.assertNotIn("client@example.test", logs.output[0])

    @patch("codeemail.main.smtplib.SMTP")
    def test_local_runtime_sends_mime_without_credentials(self, smtp):
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "SMTP", "ENVIRONMENT": "local", "SMTP_SERVER": "mailhog"}):
            for html in (False, True):
                main.lambda_handler({**self.message, "html": html}, None)
                message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
                self.assertEqual(message["To"], self.message["to"])
                self.assertEqual(message["X-Correlation-Id"], "request-123")
                self.assertEqual(message.get_content_type(), "text/html" if html else "text/plain")
                self.assertIn("Concluida", message.get_content())
                smtp.assert_called_with("mailhog", 1025, timeout=10)

    def test_invalid_messages_fail_before_any_send(self):
        invalid = [None, [], {}, {**self.message, "to": "x\nBcc: y@a.test"},
                   {**self.message, "to": ["a@b.test"]}, {**self.message, "to": "a@b.test,c@d.test"},
                   {**self.message, "subject": ""}, {**self.message, "subject": "a\nb"},
                   {**self.message, "subject": "x" * 201}, {**self.message, "body": ""},
                   {**self.message, "body": 1}, {**self.message, "body": "x" * 131073},
                   {**self.message, "html": "true"}, {**self.message, "correlationId": "a\nb"}]
        for payload in invalid:
            with self.subTest(payload=type(payload)), patch.object(main, "_ses") as ses:
                with self.assertRaises(ValueError):
                    main.lambda_handler(payload, None)
                ses.assert_not_called()

    def test_settings_fail_closed(self):
        for update in ({"NOTIFICATIONS_EMAIL_FROM": ""}, {"EMAIL_PROVIDER": "invalid"}, {"EMAIL_PROVIDER": "SMTP"}):
            with self.subTest(update=update), patch.dict(os.environ, update), self.assertRaises(ValueError):
                main.lambda_handler(self.message, None)

    @patch.object(main, "_ses")
    def test_health_checks_verified_sender_without_sending(self, ses):
        ses.return_value.get_email_identity.return_value = {"VerifiedForSendingStatus": True}
        self.assertTrue(main.lambda_handler({"operation": "health"}, None)["ready"])
        ses.return_value.send_email.assert_not_called()
        ses.return_value.get_email_identity.return_value = {"VerifiedForSendingStatus": False}
        with self.assertRaisesRegex(RuntimeError, "not verified"):
            main.lambda_handler({"operation": "health"}, None)
        with patch.dict(os.environ, {"EMAIL_PROVIDER": "SMTP", "ENVIRONMENT": "local"}):
            self.assertTrue(main.lambda_handler({"operation": "health"}, None)["ready"])

    @patch.object(main, "_ses")
    def test_provider_failure_is_sanitized_and_correlated(self, ses):
        for error in (ClientError({"Error": {"Code": "MessageRejected", "Message": "sensitive recipient"}}, "SendEmail"),
                      EndpointConnectionError(endpoint_url="https://ses.example.test")):
            ses.return_value.send_email.side_effect = error
            with self.assertLogs(main.logger, level="ERROR") as logs, self.assertRaisesRegex(RuntimeError, "delivery failed") as result:
                main.lambda_handler(self.message, None)
            self.assertNotIn("sensitive", str(result.exception))
            self.assertNotIn("client@example.test", logs.output[0])
            self.assertEqual(logs.records[0].correlationId, "request-123")

    @patch("codeemail.main.boto3.client")
    def test_ses_client_has_bounded_timeouts_and_retries(self, client):
        main._ses()
        config = client.call_args.kwargs["config"]
        self.assertEqual(config.connect_timeout, 3)
        self.assertEqual(config.read_timeout, 10)
