import os
import unittest
from unittest.mock import MagicMock, patch

from codeemail.main import lambda_handler


class EmailLambdaTest(unittest.TestCase):
    def test_sends_plain_and_html_messages_using_configured_smtp(self):
        for html, subtype in ((False, "plain"), (True, "html")):
            with self.subTest(html=html), patch.dict(os.environ, {
                "SMTP_SERVER": "mail.example.test", "SMTP_PORT": "2525",
                "REMETENTE_EMAIL": "oficina@example.test", "REMETENTE_SENHA": "secret",
            }), patch("codeemail.main.smtplib.SMTP") as smtp:
                server = smtp.return_value.__enter__.return_value
                response = lambda_handler({"to": "client@example.test", "subject": "OS", "body": "Pronta", "html": html}, None)
                self.assertEqual(response["statusCode"], 200)
                smtp.assert_called_once_with("mail.example.test", 2525)
                server.starttls.assert_called_once_with()
                server.login.assert_called_once_with("oficina@example.test", "secret")
                args = server.sendmail.call_args.args
                self.assertEqual(args[:2], ("oficina@example.test", "client@example.test"))
                self.assertIn(f"Content-Type: text/{subtype}", args[2])

    def test_rejects_incomplete_payload_before_smtp(self):
        for payload in ({}, {"to": "client@example.test"}, {"to": "client@example.test", "subject": "OS"}):
            with self.subTest(payload=payload), patch("codeemail.main.smtplib.SMTP") as smtp:
                with self.assertRaisesRegex(ValueError, "Payload inválido"):
                    lambda_handler(payload, None)
                smtp.assert_not_called()

    def test_surfaces_smtp_failure(self):
        with patch("codeemail.main.smtplib.SMTP") as smtp:
            smtp.return_value.__enter__.return_value.starttls.side_effect = OSError("SMTP indisponível")
            with self.assertRaisesRegex(OSError, "SMTP indisponível"):
                lambda_handler({"to": "c@example.test", "subject": "OS", "body": "Pronta"}, None)
