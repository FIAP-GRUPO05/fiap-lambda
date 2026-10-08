resource "aws_apigatewayv2_api" "this" {
  name          = "fiap-api-gateway"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
}


resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.this.id
  name             = "jwt-authorizer"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = local.jwt_issuer
    audience = [var.jwt_audience]
  }


  depends_on = [
    aws_s3_bucket_policy.jwks,
    aws_s3_object.openid_configuration,
    aws_s3_object.jwks,
  ]
}



resource "aws_apigatewayv2_integration" "token" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.this.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_lambda_permission" "api_gateway_token" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}


resource "aws_apigatewayv2_integration" "api" {
  api_id             = aws_apigatewayv2_api.this.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri    = local.api_url

  request_parameters = {
    "overwrite:path" = "$request.path"
  }

  lifecycle {
    precondition {
      condition     = local.api_url != ""
      error_message = "api_url vazio: o Load Balancer da API ainda não tem hostname. Aplique o fiap-k8s de novo em alguns minutos ou preencha api_url."
    }
  }
}



resource "aws_apigatewayv2_route" "login" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "POST /auth/login"
  target    = "integrations/${aws_apigatewayv2_integration.token.id}"
}


locals {
  public_api_routes = [
    "GET /",
    "POST /auth/register",
    "POST /auth/register-account",
    "GET /actuator/health",
    "GET /actuator/health/{proxy+}",
    "GET /swagger-ui.html",
    "GET /swagger-ui/{proxy+}",
    "GET /v3/api-docs",
    "GET /v3/api-docs/{proxy+}",
    "GET /service-orders/{id}/budget",
    "GET /service-orders/{id}/budget/decision",
    "POST /service-orders/{id}/budget/approve",
    "POST /service-orders/{id}/budget/reject",
  ]
}

resource "aws_apigatewayv2_route" "public" {
  for_each  = toset(local.public_api_routes)
  api_id    = aws_apigatewayv2_api.this.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}


resource "aws_apigatewayv2_route" "protected" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "ANY /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}
