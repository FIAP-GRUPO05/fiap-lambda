import contextlib
import io
import json
import os
import sys
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import MagicMock, patch
from uuid import uuid4

import bcrypt
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.modules.setdefault("boto3", MagicMock())

from codetoken import main


class CustomerCpfValidationTest(unittest.TestCase):
    def test_accepts_unformatted_and_formatted_valid_cpf(self):
        self.assertEqual(main._normalize_cpf("52998224725"), "52998224725")
        self.assertEqual(main._normalize_cpf("529.982.247-25"), "52998224725")

    def test_rejects_invalid_cpf_inputs(self):
        invalid_values = (
            "529.982.247-25x",
            "5299822472",
            "529982247250",
            "00000000000",
            "11111111111",
            "52998224735",
            "52998224724",
            None,
            "",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertIsNone(main._normalize_cpf(value))


class TokenLambdaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_pem = cls.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        cls.public_key = cls.private_key.public_key()

    def setUp(self):
        self.env = patch.dict(os.environ, {
            "JWT_ISSUER": "https://issuer.example.test",
            "JWT_AUDIENCE": "fiap-api",
            "JWT_KID": "unit-test-kid",
            "JWT_EXP_SECONDS": "3600",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.customer_id = uuid4()
        self.customer_lookup = patch.object(
            main, "_find_customer", return_value=(self.customer_id, "52998224725", "ACTIVE")
        )
        self.find_customer = self.customer_lookup.start()
        self.addCleanup(self.customer_lookup.stop)
        self.private_key_lookup = patch.object(main, "_get_private_key", return_value=self.private_pem)
        self.private_key_lookup.start()
        self.addCleanup(self.private_key_lookup.stop)

    @staticmethod
    def event(route, payload):
        return {
            "routeKey": route,
            "body": json.dumps(payload),
            "isBase64Encoded": False,
        }

    def invoke_customer(self, cpf="52998224725"):
        return main.lambda_handler(self.event("POST /auth/customer", {"cpf": cpf}), None)

    def test_invalid_cpf_is_rejected_before_database_lookup(self):
        response = self.invoke_customer("529.982.247-25x")

        self.assertEqual(response["statusCode"], 400)
        self.find_customer.assert_not_called()

    def test_unknown_customer_is_rejected_generically(self):
        self.find_customer.return_value = None

        response = self.invoke_customer()

        self.assertEqual(response["statusCode"], 401)
        self.assertEqual(json.loads(response["body"])["message"], "Credenciais inválidas")

    def test_inactive_customer_is_forbidden(self):
        self.find_customer.return_value = (self.customer_id, "52998224725", "INACTIVE")

        response = self.invoke_customer()

        self.assertEqual(response["statusCode"], 403)

    def test_formatted_cpf_is_normalized_before_lookup(self):
        self.invoke_customer("529.982.247-25")

        self.find_customer.assert_called_once_with("52998224725")

    def test_active_customer_receives_valid_rs256_jwt_without_cpf_claim(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            response = self.invoke_customer()

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["tokenType"], "Bearer")
        claims = jwt.decode(
            body["accessToken"],
            self.public_key,
            algorithms=["RS256"],
            issuer="https://issuer.example.test",
            audience="fiap-api",
        )
        self.assertEqual(claims["iss"], "https://issuer.example.test")
        self.assertEqual(claims["aud"], "fiap-api")
        self.assertEqual(claims["roles"], ["CUSTOMER"])
        self.assertEqual(claims["customerId"], str(self.customer_id))
        self.assertEqual(claims["sub"], str(self.customer_id))
        self.assertIn("exp", claims)
        self.assertNotIn("cpf", claims)
        self.assertEqual(jwt.get_unverified_header(body["accessToken"])["alg"], "RS256")
        self.assertNotIn(body["accessToken"], stdout.getvalue())

    def test_customer_query_uses_parameterized_normalized_document(self):
        row = (self.customer_id, "52998224725", "ACTIVE")
        cursor = MagicMock()
        cursor.fetchone.return_value = row
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        with patch.object(main, "_get_connection", return_value=connection):
            result = main._query_customer("52998224725")

        self.assertEqual(result, row)
        cursor.execute.assert_called_once_with(
            "SELECT id, cnpj_cpf, status FROM customers WHERE cnpj_cpf = %s",
            ("52998224725",),
        )

    def test_existing_email_password_admin_login_still_works(self):
        hashed_password = bcrypt.hashpw(b"unit-test-password", bcrypt.gensalt()).decode("utf-8")
        user = ("admin@example.test", hashed_password, "ROLE_ADMIN", None)

        with patch.object(main, "_find_user", return_value=user):
            response = main.lambda_handler(
                self.event("POST /auth/login", {
                    "email": "admin@example.test",
                    "password": "unit-test-password",
                }),
                None,
            )

        self.assertEqual(response["statusCode"], 200)
        claims = jwt.decode(
            json.loads(response["body"])["accessToken"],
            self.public_key,
            algorithms=["RS256"],
            issuer="https://issuer.example.test",
            audience="fiap-api",
        )
        self.assertEqual(claims["roles"], ["ADMIN"])
        self.assertEqual(claims["sub"], "admin@example.test")


class CustomerAuthenticationEndToEndTest(unittest.TestCase):
    @unittest.skipUnless(
        os.getenv("API_GATEWAY_URL") and os.getenv("E2E_CUSTOMER_CPF"),
        "requires API_GATEWAY_URL and E2E_CUSTOMER_CPF for a deployed active Customer",
    )
    def test_customer_authentication_and_protected_my_orders(self):
        base_url = os.environ["API_GATEWAY_URL"].rstrip("/")
        cpf = os.environ["E2E_CUSTOMER_CPF"]
        status_code, body = self.request("POST", f"{base_url}/auth/customer", {"cpf": cpf})
        self.assertEqual(status_code, 200)
        access_token = json.loads(body)["accessToken"]
        self.assertTrue(access_token)

        status_code, _ = self.request(
            "GET", f"{base_url}/service-orders/my-orders", token=access_token
        )
        self.assertEqual(status_code, 200)

        status_code, _ = self.request("GET", f"{base_url}/service-orders/my-orders")
        self.assertEqual(status_code, 401)

        status_code, _ = self.request(
            "POST", f"{base_url}/auth/customer", {"cpf": "000.000.000-00"}
        )
        self.assertEqual(status_code, 400)

    @unittest.skipUnless(
        os.getenv("API_GATEWAY_URL") and os.getenv("E2E_INACTIVE_CUSTOMER_CPF"),
        "requires API_GATEWAY_URL and E2E_INACTIVE_CUSTOMER_CPF for a deployed inactive Customer",
    )
    def test_inactive_customer_is_forbidden_by_deployed_gateway(self):
        base_url = os.environ["API_GATEWAY_URL"].rstrip("/")
        status_code, _ = self.request(
            "POST",
            f"{base_url}/auth/customer",
            {"cpf": os.environ["E2E_INACTIVE_CUSTOMER_CPF"]},
        )
        self.assertEqual(status_code, 403)

    @staticmethod
    def request(method, url, body=None, token=None):
        headers = {}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=15) as response:
                return response.status, response.read().decode("utf-8")
        except HTTPError as error:
            return error.code, error.read().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
