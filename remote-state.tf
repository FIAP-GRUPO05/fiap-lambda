locals {
  state_bucket = "fiap-tfstate-${data.aws_caller_identity.current.account_id}"
}

data "terraform_remote_state" "k8s" {
  backend = "s3"
  config = {
    bucket = local.state_bucket
    key    = "fiap/k8s.tfstate"
    region = var.region
  }
}

data "terraform_remote_state" "database" {
  backend = "s3"
  config = {
    bucket = local.state_bucket
    key    = "fiap/database.tfstate"
    region = var.region
  }
}

locals {
  db_host = var.db_host != "" ? var.db_host : data.terraform_remote_state.database.outputs.db_host
  api_url = var.api_url != "" ? var.api_url : data.terraform_remote_state.k8s.outputs.api_public_url
}
