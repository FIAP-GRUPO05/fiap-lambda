data "aws_secretsmanager_secret" "postgres" {
  for_each = local.environments
  name     = "fiap/${each.key}/postgres"
}

resource "aws_secretsmanager_secret" "jwt" {
  for_each                = local.environments
  name                    = "fiap/${each.key}/jwt-signing"
  description             = "RSA signing key for the ${each.key} authentication Lambda"
  recovery_window_in_days = 7
}

resource "aws_cloudwatch_log_group" "authentication" {
  for_each          = local.environments
  name              = "/aws/lambda/fiap-auth-${each.key}"
  retention_in_days = 14
}

resource "aws_iam_role" "authentication" {
  for_each = local.environments
  name     = "fiap-auth-${each.key}"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "authentication" {
  for_each = local.environments
  name     = "fiap-auth-${each.key}"
  role     = aws_iam_role.authentication[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.authentication[each.key].arn}:*" },
      { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_secretsmanager_secret.jwt[each.key].arn, data.aws_secretsmanager_secret.postgres[each.key].arn] },
      { Effect = "Allow", Action = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DescribeSubnets", "ec2:DeleteNetworkInterface", "ec2:AssignPrivateIpAddresses", "ec2:UnassignPrivateIpAddresses"], Resource = "*" }
    ]
  })
}

data "archive_file" "authentication" {
  type        = "zip"
  source_dir  = "${path.module}/../../build/token-package"
  output_path = "${path.module}/../../build/token.zip"
}

resource "aws_lambda_function" "authentication" {
  for_each         = local.environments
  function_name    = "fiap-auth-${each.key}"
  description      = "CPF and staff authentication with isolated database and RSA key"
  role             = aws_iam_role.authentication[each.key].arn
  runtime          = "python3.12"
  handler          = "main.lambda_handler"
  memory_size      = 256
  timeout          = 15
  filename         = data.archive_file.authentication.output_path
  source_code_hash = data.archive_file.authentication.output_base64sha256
  publish          = true
  vpc_config {
    subnet_ids         = data.terraform_remote_state.platform.outputs.private_subnet_ids
    security_group_ids = [data.terraform_remote_state.platform.outputs.lambda_security_group_id]
  }
  environment {
    variables = {
      DB_HOST                    = data.terraform_remote_state.database.outputs.db_address
      DB_PORT                    = "5432"
      DB_NAME                    = "oficina_${each.key}"
      DB_SECRET_ARN              = data.aws_secretsmanager_secret.postgres[each.key].arn
      JWT_PRIVATE_KEY_SECRET_ARN = aws_secretsmanager_secret.jwt[each.key].arn
      JWT_ISSUER                 = aws_apigatewayv2_api.environment[each.key].api_endpoint
      JWT_AUDIENCE               = "fiap-api"
      JWT_KID                    = "fiap-${each.key}-v1"
      JWT_EXP_SECONDS            = "3600"
    }
  }
  depends_on = [aws_iam_role_policy.authentication]
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_alias" "live" {
  for_each         = local.environments
  name             = "live"
  function_name    = aws_lambda_function.authentication[each.key].function_name
  function_version = aws_lambda_function.authentication[each.key].version
  lifecycle { ignore_changes = [function_version] }
}

resource "aws_lambda_permission" "gateway" {
  for_each      = local.environments
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authentication[each.key].function_name
  qualifier     = aws_lambda_alias.live[each.key].name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.environment[each.key].execution_arn}/*/*"
}
