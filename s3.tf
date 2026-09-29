data "aws_caller_identity" "current" {}

locals {
  keys_bucket = "fiap-jwt-keys-${data.aws_caller_identity.current.account_id}"
  jwks_bucket = "fiap-jwt-jwks-${data.aws_caller_identity.current.account_id}"
  jwt_issuer  = "https://${terraform_data.jwks_bucket.output}.s3.${var.region}.amazonaws.com"
}


resource "terraform_data" "keys_bucket" {
  input = local.keys_bucket

  provisioner "local-exec" {
    command = "aws s3api head-bucket --bucket ${self.input} 2>/dev/null || aws s3api create-bucket --bucket ${self.input} --region ${var.region}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws s3 rb s3://${self.output} --force"
  }
}

resource "terraform_data" "jwks_bucket" {
  input = local.jwks_bucket

  provisioner "local-exec" {
    command = "aws s3api head-bucket --bucket ${self.input} 2>/dev/null || aws s3api create-bucket --bucket ${self.input} --region ${var.region}"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws s3 rb s3://${self.output} --force"
  }
}



resource "aws_s3_bucket_public_access_block" "keys" {
  bucket                  = terraform_data.keys_bucket.output
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "private_key" {
  bucket = terraform_data.keys_bucket.output
  key    = "private.pem"
  source = "${path.module}/keys/private.pem"
  etag   = filemd5("${path.module}/keys/private.pem")
}



resource "aws_s3_bucket_public_access_block" "jwks" {
  bucket                  = terraform_data.jwks_bucket.output
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}


resource "aws_s3_bucket_policy" "jwks" {
  bucket     = terraform_data.jwks_bucket.output
  depends_on = [aws_s3_bucket_public_access_block.jwks]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadJwks"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "arn:aws:s3:::${terraform_data.jwks_bucket.output}/.well-known/*"
    }]
  })
}

resource "aws_s3_object" "openid_configuration" {
  bucket       = terraform_data.jwks_bucket.output
  key          = ".well-known/openid-configuration"
  content_type = "application/json"
  content = jsonencode({
    issuer   = local.jwt_issuer
    jwks_uri = "${local.jwt_issuer}/.well-known/jwks.json"
  })
}

resource "aws_s3_object" "jwks" {
  bucket       = terraform_data.jwks_bucket.output
  key          = ".well-known/jwks.json"
  content_type = "application/json"
  source       = "${path.module}/keys/jwks.json"
  etag         = filemd5("${path.module}/keys/jwks.json")
}
