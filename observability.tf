resource "aws_cloudwatch_log_group" "lambda_token" {
  name              = "/aws/lambda/lambda-token"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "lambda_email" {
  name              = "/aws/lambda/lambda-email"
  retention_in_days = 14
}
