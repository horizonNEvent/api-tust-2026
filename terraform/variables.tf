variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "sa-east-1"
}

variable "environment" {
  description = "Environment name (local, dev, hml, prod)"
  type        = string
  
  validation {
    condition     = contains(["local", "dev", "hml", "prod"], var.environment)
    error_message = "Environment must be one of: local, dev, hml, prod"
  }
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "api-tust"
}

variable "sqs_tust_queue_name" {
  description = "SQS queue name for TUST robot tasks"
  type        = string
  default     = "tasks"
}

variable "s3_bucket_name" {
  description = "S3 bucket name for datalake raw (must be unique)"
  type        = string
  default     = "datalake-raw"
}

variable "dynamodb_idempotency_table_name" {
  description = "DynamoDB Table Name for Idempotency"
  type        = string
  default     = "idempotency"
}

variable "message_retention_days" {
  description = "SQS message retention period in days"
  type        = number
  default     = 14
}

variable "dlq_max_receive_count" {
  description = "Maximum number of receives before message goes to DLQ"
  type        = number
  default     = 5
}

variable "visibility_timeout_seconds" {
  description = "SQS visibility timeout in seconds"
  type        = number
  default     = 300
}

# ===========================
# LocalStack Support (From GD_Compartilhada standard)
# ===========================

variable "use_localstack" {
  description = "Flag para activar LocalStack (skip credentials validation, custom endpoints)"
  type        = bool
  default     = false
}

variable "aws_service_endpoints" {
  description = "Mapa de endpoints personalizados para servicios AWS (solo LocalStack)"
  type        = map(string)
  default     = {}
}
