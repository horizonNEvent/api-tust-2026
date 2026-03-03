terraform {
  required_version = ">= 1.2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# 1. AWS SQS - Dead Letter Queue (DLQ)
resource "aws_sqs_queue" "tust_dlq" {
  name                      = "${var.project}-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 dias
  
  tags = {
    Environment = var.environment
    Project     = var.project
  }
}

# 2. AWS SQS - Inbound Queue (Fila Principal)
resource "aws_sqs_queue" "tust_queue" {
  name                      = "${var.project}-queue-${var.environment}"
  # KEDA Long Polling Optimization
  receive_wait_time_seconds = 20
  
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.tust_dlq.arn
    maxReceiveCount     = 5
  })

  tags = {
    Environment = var.environment
    Project     = var.project
  }
}

# 3. AWS DynamoDB - Tabela de Idempotência
resource "aws_dynamodb_table" "tust_idempotency" {
  name           = "${var.project}-idempotency-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "IdempotencyKey"

  attribute {
    name = "IdempotencyKey"
    type = "S"
  }

  tags = {
    Environment = var.environment
    Project     = var.project
  }
}

# 4. AWS S3 - Data Lake (Raw)
resource "aws_s3_bucket" "tust_datalake" {
  bucket = "${var.project}-datalake-raw-${var.environment}-${random_string.suffix.result}"
  
  tags = {
    Environment = var.environment
    Project     = var.project
  }
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# 5. IAM Policy - Least Privilege para o Worker
resource "aws_iam_policy" "tust_worker_policy" {
  name        = "${var.project}-worker-policy-${var.environment}"
  description = "Politica de Least Privilege para os Workers do TUST (KEDA)"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.tust_queue.arn
      },
      {
        Effect   = "Allow"
        Action   = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.tust_dlq.arn
      },
      {
        Effect   = "Allow"
        Action   = [
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.tust_idempotency.arn
      },
      {
        Effect   = "Allow"
        Action   = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.tust_datalake.arn}/*"
      }
    ]
  })
}
