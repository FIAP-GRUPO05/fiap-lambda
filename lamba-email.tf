data "archive_file" "lambda_email_zip" {
  type        = "zip"
  source_file = "${path.module}/email/main.py"
  output_path = "${path.module}/build/lambda-email.zip"
}

resource "aws_lambda_function" "lambda-email" {
  function_name    = "lambda-email"
  role             = data.aws_iam_role.lab_role.arn
  handler          = "main.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.lambda_email_zip.output_path
  source_code_hash = data.archive_file.lambda_email_zip.output_base64sha256
  timeout          = 60
  environment {
    variables = {
      SMTP_SERVER        = "smtp.gmail.com"
      SMTP_PORT          = "587"
      REMETENTE_EMAIL    = var.remetente_email
      REMETENTE_SENHA    = var.remetente_senha
      DESTINATARIO_EMAIL = var.destinatario_email
    }
  }
}