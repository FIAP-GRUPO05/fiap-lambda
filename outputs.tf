output "api_gateway_url" {
  value       = aws_apigatewayv2_stage.default.invoke_url
  description = "URL pública do API Gateway (login em POST /auth/login)."
}

output "jwt_issuer" {
  value       = local.jwt_issuer
  description = "Valor para jwtIssuer no terraform.tfvars do fiap-k8s."
}

output "jwks_uri" {
  value       = "${local.jwt_issuer}/.well-known/jwks.json"
  description = "JWKS com a chave pública usada para validar os tokens."
}
