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
