import json
import os
import unittest
from unittest.mock import MagicMock, patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

with patch("boto3.client", side_effect=lambda *args, **kwargs: MagicMock()):
    from codetoken import main


class OidcDiscoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pem = cls.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption())

    def setUp(self):
        environment = patch.dict(os.environ, {"JWT_ISSUER": "https://issuer.example.test",
            "JWT_AUDIENCE": "fiap-api", "JWT_KID": "test-v1"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_discovery_does_not_access_database(self):
        with patch.object(main, "_get_connection") as database:
            response = main.lambda_handler({"routeKey": "GET /.well-known/openid-configuration"}, None)
            self.assertEqual(json.loads(response["body"]), {"issuer": "https://issuer.example.test",
                "jwks_uri": "https://issuer.example.test/.well-known/jwks.json"})
            database.assert_not_called()

    def test_jwks_exposes_only_public_material_and_verifies_issued_tokens(self):
        with patch.object(main, "_get_private_key", return_value=self.pem):
            response = main.lambda_handler({"routeKey": "GET /.well-known/jwks.json"}, None)
            key = json.loads(response["body"])["keys"][0]
            self.assertTrue({"d", "p", "q", "dp", "dq", "qi"}.isdisjoint(key))
            self.assertEqual(key["kid"], "test-v1")
            token = json.loads(main._issue_token("customer-id", "CUSTOMER", "customer-id")["body"])["accessToken"]
            claims = jwt.decode(token, jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key)),
                algorithms=["RS256"], audience="fiap-api", issuer="https://issuer.example.test")
            self.assertEqual(claims["customerId"], "customer-id")

    def test_private_key_can_be_loaded_from_secrets_manager(self):
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": self.pem.decode()}
        with patch.dict(os.environ, {"JWT_PRIVATE_KEY_SECRET_ARN": "signing-secret"}), \
             patch.object(main, "_private_key", None), patch.object(main, "secretsmanager", client), \
             patch.object(main, "s3") as s3:
            self.assertEqual(main._get_private_key(), self.pem)
            client.get_secret_value.assert_called_once_with(SecretId="signing-secret")
            s3.get_object.assert_not_called()

    def test_only_admin_receives_staff_management_scope(self):
        with patch.object(main, "_get_private_key", return_value=self.pem):
            for role in ("ROLE_ADMIN", "ADMIN", "ROLE_USER", "CUSTOMER"):
                response = main._issue_token("subject", role)
                token = json.loads(response["body"])["accessToken"]
                claims = jwt.decode(token, self.private.public_key(), algorithms=["RS256"],
                    audience="fiap-api", issuer="https://issuer.example.test")
                self.assertEqual(claims.get("scope"), "staff:manage" if role in {"ROLE_ADMIN", "ADMIN"} else None)

    def test_invalid_login_types_and_oversized_password_are_rejected_before_database(self):
        for payload in ({"email": 4, "password": "abc"}, {"email": "test@example.test", "password": 4},
                        {"email": "test@example.test", "password": "x" * 73}):
            with self.subTest(payload=payload), patch.object(main, "_find_user") as lookup:
                response = main.lambda_handler({"routeKey": "POST /auth/login", "body": json.dumps(payload)}, None)
                self.assertEqual(response["statusCode"], 400)
                lookup.assert_not_called()
