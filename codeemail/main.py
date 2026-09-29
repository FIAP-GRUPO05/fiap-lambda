import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def lambda_handler(event, context):
    print(event)
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    remetente = os.getenv("REMETENTE_EMAIL")
    senha = os.getenv("REMETENTE_SENHA")
    destinatario = os.getenv("DESTINATARIO_EMAIL")
    remetente = os.getenv("REMETENTE_EMAIL")
    senha = os.getenv("REMETENTE_SENHA")

    destinatario = event.get("to")
    assunto = event.get("subject")
    corpo = event.get("body")
    tipo = "html" if event.get("html") else "plain"

    if not destinatario or not assunto or not corpo:
        raise ValueError("Payload inválido: 'to', 'subject' e 'body' são obrigatórios")

    mensagem = MIMEMultipart()
    mensagem["From"] = remetente
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.attach(MIMEText(corpo, tipo, "utf-8"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(remetente, senha)
        server.sendmail(remetente, destinatario, mensagem.as_string())

    return {"statusCode": 200, "body": "E-mail enviado"}