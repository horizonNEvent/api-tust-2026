terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Credenciales Mock para LocalStack (Requeridas para evitar error "No valid credential sources")
  access_key = var.use_localstack ? "mock_access_key" : null
  secret_key = var.use_localstack ? "mock_secret_key" : null

  # ====================================================
  # SOPORTE HÍBRIDO: LocalStack (Testing) o AWS Real
  # ====================================================
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack
  
  # Forzar Path Style si es LocalStack
  s3_use_path_style           = var.use_localstack
  
  # Endpoints dinámicos (solo se activan si hay valores en el map)
  dynamic "endpoints" {
    for_each = length(var.aws_service_endpoints) > 0 ? [1] : []
    
    content {
      sqs      = lookup(var.aws_service_endpoints, "sqs", null)
      dynamodb = lookup(var.aws_service_endpoints, "dynamodb", null)
      s3       = lookup(var.aws_service_endpoints, "s3", null)
      iam      = lookup(var.aws_service_endpoints, "iam", null)
    }
  }
  
  default_tags {
    tags = {
      Project     = "TUST"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
