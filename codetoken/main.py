import base64
import datetime
import json
import os

import bcrypt
import boto3
import jwt
import psycopg2

s3 = boto3.client("s3")
_private_key = None
_connection = None


def _get_private_key():
    global _private_key
    if _private_key is None:
        obj = s3.get_object(Bucket=os.environ["KEY_BUCKET"], Key=os.environ["KEY_OBJECT"])
        _private_key = obj["Body"].read()
    return _private_key


def _get_connection():
    global _connection
    if _connection is None or _connection.closed:
        _connection = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            connect_timeout=5,
        )
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


def lambda_handler(event, context):
    try:
        body = _read_body(event)
    except (ValueError, UnicodeDecodeError):
        return _response(400, {"message": "Body inválido"})

    email = body.get("email")
    password = body.get("password")
    if not email or not password:
        return _response(400, {"message": "'email' e 'password' são obrigatórios"})

    user = _find_user(email)

    if user is None or not bcrypt.checkpw(password.encode("utf-8"), user[1].encode("utf-8")):
        return _response(401, {"message": "Invalid credentials"})

    user_email, _, role, customer_id = user
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(seconds=int(os.getenv("JWT_EXP_SECONDS", "3600")))


    claims = {
        "iss": os.environ["JWT_ISSUER"],
        "aud": os.environ["JWT_AUDIENCE"],
        "sub": user_email,
        "roles": [role.removeprefix("ROLE_")],
        "iat": now,
        "exp": expires_at,
    }
    if customer_id is not None:
        claims["customerId"] = str(customer_id)

    token = jwt.encode(
        claims,
        _get_private_key(),
        algorithm="RS256",
        headers={"kid": os.environ["JWT_KID"]},
    )
    print('Gerando token')
    print(token)
    return _response(200, {
        "accessToken": token,
        "expiresAt": int(expires_at.timestamp() * 1000),
        "tokenType": "Bearer",
    })
