import base64
import datetime
import json
import os
import re

import bcrypt
import boto3
import jwt
import psycopg2
from cryptography.hazmat.primitives import serialization

import logging

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

s3 = boto3.client("s3")
secretsmanager = boto3.client("secretsmanager")
_private_key = None
_connection = None


def _get_private_key():
    global _private_key
    if _private_key is None:
        secret_arn = os.getenv("JWT_PRIVATE_KEY_SECRET_ARN")
        if secret_arn:
            _private_key = secretsmanager.get_secret_value(SecretId=secret_arn)["SecretString"].encode("utf-8")
        else:
            obj = s3.get_object(Bucket=os.environ["KEY_BUCKET"], Key=os.environ["KEY_OBJECT"])
            _private_key = obj["Body"].read()
    return _private_key


def _get_connection():
    global _connection
    if _connection is None or _connection.closed:
        secret_arn = os.getenv("DB_SECRET_ARN")
        if secret_arn:
            secret = json.loads(secretsmanager.get_secret_value(SecretId=secret_arn)["SecretString"])
            db_user = secret["username"]
            db_password = secret["password"]
        else:
            db_user = os.environ["DB_USER"]
            db_password = os.environ["DB_PASSWORD"]

        connection_options = dict(
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.environ["DB_NAME"],
            user=db_user,
            password=db_password,
            connect_timeout=5,
        )
        if secret_arn:
            connection_options["sslmode"] = "require"
        _connection = psycopg2.connect(**connection_options)
        _connection.autocommit = True
    return _connection


def _query_user(email):
    with _get_connection().cursor() as cursor:
        cursor.execute(
            "SELECT email, password, role, customer_id FROM users WHERE email = %s",
            (email,),
        )
        return cursor.fetchone()


def _find_user(email):
    global _connection
    try:
        return _query_user(email)
    except psycopg2.OperationalError:
        _connection = None
        return _query_user(email)


def _query_customer(cpf):
    with _get_connection().cursor() as cursor:
        cursor.execute(
            "SELECT id, cnpj_cpf, status FROM customers WHERE cnpj_cpf = %s",
            (cpf,),
        )
        return cursor.fetchone()


def _find_customer(cpf):
    global _connection
    try:
        return _query_customer(cpf)
    except psycopg2.OperationalError:
        _connection = None
        return _query_customer(cpf)


def _normalize_cpf(value):
    if not isinstance(value, str):
        return None

    cpf = value.strip()
    if not re.fullmatch(r"(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})", cpf):
        return None

    digits = re.sub(r"[.-]", "", cpf)
    if len(set(digits)) == 1:
        return None

    first_sum = sum(int(digit) * weight for digit, weight in zip(digits[:9], range(10, 1, -1)))
    first_remainder = first_sum % 11
    first_digit = 0 if first_remainder < 2 else 11 - first_remainder

    second_sum = sum(int(digit) * weight for digit, weight in zip(digits[:9], range(11, 2, -1)))
    second_sum += first_digit * 2
    second_remainder = second_sum % 11
    second_digit = 0 if second_remainder < 2 else 11 - second_remainder

    if digits[-2:] != f"{first_digit}{second_digit}":
        return None
    return digits


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _read_body(event):
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def _openid_configuration():
    issuer = os.environ["JWT_ISSUER"]
    return _response(200, {"issuer": issuer, "jwks_uri": f"{issuer}/.well-known/jwks.json"})


def _jwks():
    private_key = serialization.load_pem_private_key(_get_private_key(), password=None)
    public_key = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_key.update({"kid": os.environ["JWT_KID"], "use": "sig", "alg": "RS256"})
    response = _response(200, {"keys": [public_key]})
    response["headers"]["Cache-Control"] = "public, max-age=300"
    return response


def _request_route(event):
    route_key = event.get("routeKey")
    if route_key:
        return route_key
    http = event.get("requestContext", {}).get("http", {})
    if http.get("method") and http.get("path"):
        return f"{http['method']} {http['path']}"
    return None


def _issue_token(subject, role, customer_id=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(seconds=int(os.getenv("JWT_EXP_SECONDS", "3600")))
    claims = {
        "iss": os.environ["JWT_ISSUER"],
        "aud": os.environ["JWT_AUDIENCE"],
        "sub": str(subject),
        "roles": [role.removeprefix("ROLE_")],
        "iat": now,
        "exp": expires_at,
    }
    if customer_id is not None:
        claims["customerId"] = str(customer_id)
    if role.removeprefix("ROLE_") == "ADMIN":
        claims["scope"] = "staff:manage"

    token = jwt.encode(
        claims,
        _get_private_key(),
        algorithm="RS256",
        headers={"kid": os.environ["JWT_KID"]},
    )
    return _response(200, {
        "accessToken": token,
        "expiresAt": int(expires_at.timestamp() * 1000),
        "tokenType": "Bearer",
    })


def _login(event):
    try:
        body = _read_body(event)
    except (TypeError, ValueError, UnicodeDecodeError):
        return _response(400, {"message": "Body inválido"})

    if not isinstance(body, dict):
        return _response(400, {"message": "Body inválido"})

    email = body.get("email")
    password = body.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        return _response(400, {"message": "'email' e 'password' são obrigatórios"})
    if len(password.encode("utf-8")) > 72:
        return _response(400, {"message": "Password inválido"})
    user = _find_user(email)

    if user is None or not bcrypt.checkpw(password.encode("utf-8"), user[1].encode("utf-8")):
        return _response(401, {"message": "Invalid credentials"})

    user_email, _, role, customer_id = user
    return _issue_token(user_email, role, customer_id)


def _customer_login(event):
    try:
        body = _read_body(event)
    except (TypeError, ValueError, UnicodeDecodeError):
        return _response(400, {"message": "Body inválido"})

    if not isinstance(body, dict):
        return _response(400, {"message": "Body inválido"})

    cpf = _normalize_cpf(body.get("cpf"))
    if cpf is None:
        return _response(400, {"message": "CPF inválido"})

    customer = _find_customer(cpf)
    if customer is None:
        return _response(401, {"message": "Credenciais inválidas"})

    customer_id, _, status = customer
    if status != "ACTIVE":
        return _response(403, {"message": "Não foi possível autenticar o cliente"})

    return _issue_token(customer_id, "CUSTOMER", customer_id)


def lambda_handler(event, context):
    route = _request_route(event)
    if route == "GET /.well-known/openid-configuration":
        return _openid_configuration()
    if route == "GET /.well-known/jwks.json":
        return _jwks()
    if route == "POST /auth/customer":
        return _customer_login(event)
    if route in (None, "POST /auth/login"):
        return _login(event)
    return _response(404, {"message": "Rota não encontrada"})
