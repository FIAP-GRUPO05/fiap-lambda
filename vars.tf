variable "remetente_email" {
  type        = string
  description = "E-mail do remetente"
}

variable "remetente_senha" {
  type        = string
  description = "Senha de app do e-mail"
  sensitive   = true
}

variable "destinatario_email" {
  type        = string
  description = "E-mail do destinatário"
}

variable "region" {
  type        = string
  default     = "us-east-1"
  description = "Região da AWS"
}

variable "vpc_name" {
  type        = string
  default     = "main-vpc"
  description = "Tag Name da VPC criada pelo fiap-k8s"
}



variable "db_host" {
  type        = string
  description = "Hostname do Load Balancer interno do Postgres (service postgres-internal do fiap-database)"

  validation {
    condition     = !can(regex("://|/|:", var.db_host))
    error_message = "db_host deve ser só o hostname, sem protocolo, porta ou barra (ex.: internal-xxx.us-east-1.elb.amazonaws.com)."
  }
}

variable "db_port" {
  type        = string
  default     = "5432"
  description = "Porta do Postgres"
}

variable "db_name" {
  type        = string
  description = "Nome do banco (mesmo postgresDb do fiap-database)"
}

variable "db_user" {
  type        = string
  description = "Usuário do banco (mesmo postgresUser do fiap-database)"
}

variable "db_password" {
  type        = string
  description = "Senha do banco (mesma postgresPassword do fiap-database)"
  sensitive   = true
}


variable "jwt_kid" {
  type        = string
  default     = "fiap-key-1"
  description = "kid da chave no jwks.json (o mesmo passado ao keys/generate-keys.py)"
}

variable "jwt_audience" {
  type        = string
  default     = "fiap-api"
  description = "Claim aud exigida pelo API Gateway e pela API"
}

variable "jwt_exp_seconds" {
  type        = string
  default     = "3600"
  description = "Validade do token em segundos"
}

variable "api_url" {
  type        = string
  description = "URL do Load Balancer da API (output api_public_url do fiap-k8s), ex.: http://xxx.elb.amazonaws.com:8080"
}
