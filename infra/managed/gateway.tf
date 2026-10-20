resource "aws_apigatewayv2_api" "environment" {
  for_each      = local.environments
  name          = "fiap-${each.key}"
  protocol_type = "HTTP"
}

resource "aws_cloudwatch_log_group" "gateway" {
  for_each          = local.environments
  name              = "/aws/apigateway/fiap-${each.key}"
  retention_in_days = 14
}

resource "aws_apigatewayv2_stage" "environment" {
  for_each    = local.environments
  api_id      = aws_apigatewayv2_api.environment[each.key].id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.gateway[each.key].arn
    format = jsonencode({
      requestId        = "$context.requestId", routeKey = "$context.routeKey",
      status           = "$context.status", responseLength = "$context.responseLength",
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_apigatewayv2_integration" "authentication" {
  for_each               = local.environments
  api_id                 = aws_apigatewayv2_api.environment[each.key].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.live[each.key].invoke_arn
  payload_format_version = "2.0"
}

locals {
  authentication_routes = {
    for item in setproduct(local.environments, toset([
      "POST /auth/login", "POST /auth/customer", "GET /.well-known/openid-configuration", "GET /.well-known/jwks.json"
    ])) : "${item[0]}:${item[1]}" => { environment = item[0], route = item[1] }
  }
  public_routes = {
    for item in setproduct(local.environments, toset([
      "GET /", "POST /auth/register-account", "GET /actuator/health",
      "GET /actuator/health/{proxy+}", "GET /swagger-ui.html", "GET /swagger-ui/{proxy+}",
      "GET /v3/api-docs", "GET /v3/api-docs/{proxy+}",
      "GET /service-orders/{id}/budget", "GET /service-orders/{id}/budget/decision",
      "POST /service-orders/{id}/budget/approve", "POST /service-orders/{id}/budget/reject"
    ])) : "${item[0]}:${item[1]}" => { environment = item[0], route = item[1] }
  }
}

resource "aws_apigatewayv2_route" "authentication" {
  for_each  = local.authentication_routes
  api_id    = aws_apigatewayv2_api.environment[each.value.environment].id
  route_key = each.value.route
  target    = "integrations/${aws_apigatewayv2_integration.authentication[each.value.environment].id}"
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  for_each         = var.enable_backend_proxy ? local.environments : toset([])
  api_id           = aws_apigatewayv2_api.environment[each.key].id
  name             = "fiap-jwt-${each.key}"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    issuer   = aws_apigatewayv2_api.environment[each.key].api_endpoint
    audience = ["fiap-api"]
  }
  depends_on = [aws_apigatewayv2_route.authentication, aws_lambda_permission.gateway, aws_apigatewayv2_stage.environment]
}

data "aws_lb" "api" {
  count = var.enable_backend_proxy ? 1 : 0
  name  = "fiap-shared-api"
}

data "aws_lb_listener" "api" {
  count             = var.enable_backend_proxy ? 1 : 0
  load_balancer_arn = data.aws_lb.api[0].arn
  port              = 80
}

resource "aws_security_group" "vpc_link" {
  count       = var.enable_backend_proxy ? 1 : 0
  name        = "fiap-api-gateway-vpc-link"
  description = "API Gateway outbound access to the private application ALB"
  vpc_id      = data.terraform_remote_state.platform.outputs.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "vpc_link_alb" {
  count             = var.enable_backend_proxy ? 1 : 0
  security_group_id = aws_security_group.vpc_link[0].id
  cidr_ipv4         = data.terraform_remote_state.platform.outputs.vpc_cidr
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
}

resource "aws_apigatewayv2_vpc_link" "api" {
  count              = var.enable_backend_proxy ? 1 : 0
  name               = "fiap-shared-api"
  subnet_ids         = data.terraform_remote_state.platform.outputs.private_subnet_ids
  security_group_ids = [aws_security_group.vpc_link[0].id]
}

resource "aws_apigatewayv2_integration" "backend" {
  for_each           = var.enable_backend_proxy ? local.environments : toset([])
  api_id             = aws_apigatewayv2_api.environment[each.key].id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri    = data.aws_lb_listener.api[0].arn
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.api[0].id
  request_parameters = {
    "overwrite:path"                      = "/${each.key}$${request.path}"
    "overwrite:header.X-Forwarded-Prefix" = "/"
  }
}

resource "aws_apigatewayv2_route" "public" {
  for_each  = var.enable_backend_proxy ? local.public_routes : {}
  api_id    = aws_apigatewayv2_api.environment[each.value.environment].id
  route_key = each.value.route
  target    = "integrations/${aws_apigatewayv2_integration.backend[each.value.environment].id}"
}

resource "aws_apigatewayv2_route" "protected" {
  for_each           = var.enable_backend_proxy ? local.environments : toset([])
  api_id             = aws_apigatewayv2_api.environment[each.key].id
  route_key          = "ANY /{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.backend[each.key].id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt[each.key].id
}

resource "aws_apigatewayv2_route" "staff_registration" {
  for_each             = var.enable_backend_proxy ? local.environments : toset([])
  api_id               = aws_apigatewayv2_api.environment[each.key].id
  route_key            = "POST /auth/register"
  target               = "integrations/${aws_apigatewayv2_integration.backend[each.key].id}"
  authorization_type   = "JWT"
  authorizer_id        = aws_apigatewayv2_authorizer.jwt[each.key].id
  authorization_scopes = ["staff:manage"]
}

output "runtime_config" {
  value = { for environment, api in aws_apigatewayv2_api.environment : environment => {
    issuer = api.api_endpoint, api_url = api.api_endpoint
  } }
}

output "function_names" {
  value = { for environment, function in aws_lambda_function.authentication : environment => function.function_name }
}
