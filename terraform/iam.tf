# ========================================
# IAM Role para API TUST - Publicar SQS
# ========================================

resource "aws_iam_role" "api_role" {
  name = "${var.project_name}-api-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com" # EKS, ECS, or EC2
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-api-role"
  }
}

resource "aws_iam_role_policy" "api_policy" {
  name = "${var.project_name}-api-policy"
  role = aws_iam_role.api_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSQSSend"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueUrl"
        ]
        Resource = aws_sqs_queue.tust_queue.arn
      }
    ]
  })
}

# ========================================
# IAM Role para Workers (KEDA)
# ========================================

resource "aws_iam_role" "worker_role" {
  name = "${var.project_name}-worker-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-worker-role"
  }
}

resource "aws_iam_role_policy" "worker_policy" {
  name = "${var.project_name}-worker-policy"
  role = aws_iam_role.worker_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSQSReceive"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl"
        ]
        Resource = aws_sqs_queue.tust_queue.arn
      },
      {
        Sid    = "AllowSQSSendDLQ"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.tust_dlq.arn
      },
      {
        Sid    = "AllowDynamoDB"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.idempotency.arn
      },
      {
        Sid    = "AllowS3Write"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = "${aws_s3_bucket.datalake_raw.arn}/*"
      }
    ]
  })
}

# Instance profiles
resource "aws_iam_instance_profile" "api_profile" {
  name = "${var.project_name}-api-profile-${var.environment}"
  role = aws_iam_role.api_role.name
}

resource "aws_iam_instance_profile" "worker_profile" {
  name = "${var.project_name}-worker-profile-${var.environment}"
  role = aws_iam_role.worker_role.name
}
