terraform {
  required_version = ">= 1.13.0"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
  backend "s3" {}
}

provider "aws" {
  region              = "sa-east-1"
  allowed_account_ids = ["456687462806"]
  default_tags {
    tags = { Project = "fiap-tech-challenge-fase-3", ManagedBy = "terraform" }
  }
}

variable "enable_backend_proxy" {
  type        = bool
  default     = true
  description = "Set false only during bootstrap before the shared internal ALB exists."
}

locals { environments = toset(["develop", "homol", "prod"]) }

data "terraform_remote_state" "platform" {
  backend = "s3"
  config = {
    bucket = "fiap-tfstate-456687462806"
    key    = "fiap/platform-shared.tfstate"
    region = "sa-east-1"
  }
}

data "terraform_remote_state" "database" {
  backend = "s3"
  config = {
    bucket = "fiap-tfstate-456687462806"
    key    = "fiap/database-shared.tfstate"
    region = "sa-east-1"
  }
}
