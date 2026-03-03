# ========================================
# DynamoDB para Idempotência
# ========================================

resource "aws_dynamodb_table" "idempotency" {
  name           = "${var.project_name}-${var.dynamodb_idempotency_table_name}-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "IdempotencyKey"

  attribute {
    name = "IdempotencyKey"
    type = "S"
  }

  tags = {
    Name = "${var.project_name}-idempotency-table"
  }
}
