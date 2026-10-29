import base64
import json
import os
import unittest
from unittest.mock import MagicMock, patch

with patch("boto3.client", side_effect=lambda *args, **kwargs: MagicMock()):
    from codetoken import main


class TokenEdgeTest(unittest.TestCase):
    def test_reads_base64_body_and_request_context_route(self):
        event = {"body": base64.b64encode(b'{"cpf":"52998224725"}').decode(), "isBase64Encoded": True,
                 "requestContext": {"http": {"method": "POST", "path": "/auth/customer"}}}
        self.assertEqual(main._read_body(event), {"cpf": "52998224725"})
        self.assertEqual(main._request_route(event), "POST /auth/customer")

    def test_unknown_route_and_malformed_customer_body(self):
        self.assertEqual(main.lambda_handler({"routeKey": "GET /missing"}, None)["statusCode"], 404)
        for body in ("{", "[]"):
            with self.subTest(body=body):
                self.assertEqual(main.lambda_handler({"routeKey": "POST /auth/customer", "body": body}, None)["statusCode"], 400)

    def test_login_rejects_missing_invalid_and_unknown_credentials(self):
        for body, expected in (("{", 400), ("[]", 400), ("{}", 400)):
            with self.subTest(body=body):
                self.assertEqual(main.lambda_handler({"routeKey": "POST /auth/login", "body": body}, None)["statusCode"], expected)
        with patch.object(main, "_find_user", return_value=None):
            self.assertEqual(main.lambda_handler({"routeKey": "POST /auth/login", "body": json.dumps({"email": "x", "password": "bad"})}, None)["statusCode"], 401)

    def test_private_key_is_fetched_once(self):
        with patch.dict(os.environ, {"KEY_BUCKET": "keys", "KEY_OBJECT": "private.pem"}), patch.object(main, "s3") as s3:
            old = main._private_key
            self.addCleanup(setattr, main, "_private_key", old)
            main._private_key = None
            s3.get_object.return_value["Body"].read.return_value = b"key"
            self.assertEqual(main._get_private_key(), b"key")
            self.assertEqual(main._get_private_key(), b"key")
            s3.get_object.assert_called_once_with(Bucket="keys", Key="private.pem")

    def test_database_connection_is_reused_and_reconnected_when_closed(self):
        with patch.dict(os.environ, {"DB_HOST": "db", "DB_NAME": "fiap", "DB_USER": "user", "DB_PASSWORD": "pass"}), patch.object(main.psycopg2, "connect") as connect:
            old = main._connection
            self.addCleanup(setattr, main, "_connection", old)
            main._connection = None
            first = connect.return_value
            first.closed = False
            self.assertIs(main._get_connection(), first)
            self.assertIs(main._get_connection(), first)
            first.closed = True
            main._get_connection()
            self.assertEqual(connect.call_count, 2)

    def test_customer_lookup_retries_after_disconnection(self):
        error = main.psycopg2.OperationalError("closed")
        with patch.object(main, "_query_customer", side_effect=[error, ("id", "cpf", "ACTIVE")]) as query:
            self.assertEqual(main._find_customer("cpf"), ("id", "cpf", "ACTIVE"))
            self.assertEqual(query.call_count, 2)
