variable "notification_sender" {
  type        = string
  default     = null
  description = "Verified SES sender in sa-east-1. Set TF_VAR_notification_sender from FIAP_NOTIFICATION_SENDER."
  validation {
    condition     = var.notification_sender == null ? true : can(regex("^[^@ ]+@[^@ ]+\\.[^@ ]+$", var.notification_sender))
    error_message = "Configure a valid SES sender email address."
  }
}

resource "aws_cloudwatch_log_group" "notifications" {
  for_each          = local.environments
  name              = "/aws/lambda/fiap-email-${each.key}"
  retention_in_days = 14
}

resource "aws_iam_role" "notifications" {
  for_each = local.environments
  name     = "fiap-email-${each.key}"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "notifications" {
  for_each = local.environments
  name     = "fiap-email-${each.key}"
  role     = aws_iam_role.notifications[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.notifications[each.key].arn}:*" },
      { Effect = "Allow", Action = ["ses:GetEmailIdentity"], Resource = "arn:aws:ses:sa-east-1:456687462806:identity/${var.notification_sender == null ? "unconfigured" : var.notification_sender}" },
      { Effect = "Allow", Action = ["ses:SendEmail"], Resource = "arn:aws:ses:sa-east-1:456687462806:identity/${var.notification_sender == null ? "unconfigured" : var.notification_sender}",
      Condition = { StringEquals = { "ses:FromAddress" = var.notification_sender == null ? "unconfigured" : var.notification_sender } } }
    ]
  })
}

data "archive_file" "notifications" {
  type        = "zip"
  source_file = "${path.module}/../../codeemail/main.py"
  output_path = "${path.module}/../../build/email.zip"
}

resource "aws_lambda_function" "notifications" {
  for_each         = local.environments
  function_name    = "fiap-email-${each.key}"
  description      = "Service-order notifications through SES with correlated logs"
  role             = aws_iam_role.notifications[each.key].arn
  runtime          = "python3.12"
  handler          = "main.lambda_handler"
  memory_size      = 128
  timeout          = 30
  filename         = data.archive_file.notifications.output_path
  source_code_hash = data.archive_file.notifications.output_base64sha256
  publish          = true
  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "INFO"
  }
  environment {
    variables = {
      ENVIRONMENT              = each.key
      EMAIL_PROVIDER           = "SES"
      NOTIFICATIONS_EMAIL_FROM = var.notification_sender == null ? "" : var.notification_sender
    }
  }
  lifecycle {
    ignore_changes = [filename, source_code_hash]
    precondition {
      condition     = var.notification_sender != null && var.notification_sender != ""
      error_message = "Set FIAP_NOTIFICATION_SENDER/TF_VAR_notification_sender before provisioning notifications."
    }
  }
  depends_on = [aws_iam_role_policy.notifications, aws_cloudwatch_log_group.notifications]
}

resource "aws_lambda_alias" "notifications_live" {
  for_each         = local.environments
  name             = "live"
  function_name    = aws_lambda_function.notifications[each.key].function_name
  function_version = aws_lambda_function.notifications[each.key].version
  lifecycle { ignore_changes = [function_version] }
}

output "notification_functions" {
  value = { for environment, function in aws_lambda_alias.notifications_live : environment => function.arn }
}
