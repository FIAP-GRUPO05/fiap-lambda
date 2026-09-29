
data "archive_file" "layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/layer"
  output_path = "${path.module}/build/layer.zip"
}

resource "aws_lambda_layer_version" "this" {
  layer_name          = "lambda-token-layer"
  filename            = data.archive_file.layer_zip.output_path
  source_code_hash    = data.archive_file.layer_zip.output_base64sha256
  compatible_runtimes = ["python3.11"]
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/codetoken"
  excludes    = ["__pycache__"]
  output_path = "${path.module}/build/lambda.zip"
}


resource "aws_security_group" "lambda_token" {
  name        = "lambda-token-sg"
  description = "Saida da lambda-token para o Postgres e o S3"
  vpc_id      = data.aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lambda_function" "this" {
  function_name    = "lambda-token"
  role             = data.aws_iam_role.lab_role.arn
  handler          = "main.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 30
  layers           = [aws_lambda_layer_version.this.arn]

  vpc_config {
    subnet_ids         = data.aws_subnets.eks.ids
    security_group_ids = [aws_security_group.lambda_token.id]
  }

  environment {
    variables = {
      DB_HOST         = var.db_host
      DB_PORT         = var.db_port
      DB_NAME         = var.db_name
      DB_USER         = var.db_user
      DB_PASSWORD     = var.db_password
      KEY_BUCKET      = terraform_data.keys_bucket.output
      KEY_OBJECT      = aws_s3_object.private_key.key
      JWT_ISSUER      = local.jwt_issuer
      JWT_AUDIENCE    = var.jwt_audience
      JWT_KID         = var.jwt_kid
      JWT_EXP_SECONDS = var.jwt_exp_seconds
    }
  }

  depends_on = [aws_vpc_endpoint.s3]
}
