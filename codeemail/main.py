"""Deliver notifications through SES; SMTP is restricted to local tests."""
import json
import logging
import os
import re
import smtplib
from email.message import EmailMessage

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _address(value):
    if not isinstance(value, str) or len(value) > 254 or not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", value):
        raise ValueError("Invalid email address")
    return value


def _settings():
    provider = os.getenv("EMAIL_PROVIDER", "SES").upper()
    sender = _address(os.getenv("NOTIFICATIONS_EMAIL_FROM", ""))
    if provider not in {"SES", "SMTP"}:
        raise ValueError("EMAIL_PROVIDER must be SES or SMTP")
    if provider == "SMTP" and os.getenv("ENVIRONMENT") != "local":
        raise ValueError("SMTP transport is restricted to ENVIRONMENT=local")
    return provider, sender


def _payload(event):
    if not isinstance(event, dict):
        raise ValueError("Payload must be an object")
    recipient = _address(event.get("to"))
    subject, body, html = event.get("subject"), event.get("body"), event.get("html", False)
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 200 or any(c in subject for c in "\r\n"):
        raise ValueError("Invalid subject")
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > 131072:
        raise ValueError("Invalid body")
    if not isinstance(html, bool):
        raise ValueError("html must be a boolean")
    correlation = event.get("correlationId", "")
    if not isinstance(correlation, str) or (correlation and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", correlation)):
        raise ValueError("Invalid correlationId")
    return recipient, subject, body, html, correlation


def _ses():
    return boto3.client("sesv2", config=Config(connect_timeout=3, read_timeout=10,
                        retries={"mode": "standard", "max_attempts": 3}))


def lambda_handler(event, context):
    provider, sender = _settings()
    if isinstance(event, dict) and event.get("operation") == "health":
        if provider == "SES" and not _ses().get_email_identity(EmailIdentity=sender).get("VerifiedForSendingStatus"):
            raise RuntimeError("SES sender identity is not verified")
        return {"statusCode": 200, "provider": provider, "ready": True}
    recipient, subject, body, html, correlation = _payload(event)
    try:
        if provider == "SES":
            result = _ses().send_email(FromEmailAddress=sender, Destination={"ToAddresses": [recipient]},
                Content={"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html" if html else "Text": {"Data": body, "Charset": "UTF-8"}}}})
            message_id = result["MessageId"]
        else:
            message = EmailMessage()
            message["From"], message["To"], message["Subject"] = sender, recipient, subject
            if correlation:
                message["X-Correlation-Id"] = correlation
            message.set_content(body, subtype="html" if html else "plain", charset="utf-8")
            with smtplib.SMTP(os.environ["SMTP_SERVER"], int(os.getenv("SMTP_PORT", "1025")), timeout=10) as server:
                server.send_message(message)
            message_id = "local-smtp"
    except (BotoCoreError, ClientError, OSError, smtplib.SMTPException) as error:
        code = error.response["Error"]["Code"] if isinstance(error, ClientError) else type(error).__name__
        logger.error("NotificationFailed", extra={"event": "NotificationFailed", "correlationId": correlation,
                               "environment": os.getenv("ENVIRONMENT"), "provider": provider, "errorCode": code})
        raise RuntimeError("Notification delivery failed: " + code) from None
    logger.info("NotificationSent", extra={"event": "NotificationSent", "correlationId": correlation,
                "environment": os.getenv("ENVIRONMENT"), "provider": provider, "messageId": message_id,
                "requestId": getattr(context, "aws_request_id", None)})
    return {"statusCode": 200, "messageId": message_id}
