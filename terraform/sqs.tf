# ========================================
# Dead Letter Queues (DLQ)
# ========================================

resource "aws_sqs_queue" "tust_dlq" {
  name                      = "${var.project_name}-${var.sqs_tust_queue_name}-dlq-${var.environment}"
  message_retention_seconds = var.message_retention_days * 86400
  
  tags = {
    Name = "${var.project_name}-tasks-dlq"
  }
}

# ========================================
# Main Queues
# ========================================

resource "aws_sqs_queue" "tust_queue" {
  name                       = "${var.project_name}-${var.sqs_tust_queue_name}-${var.environment}"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_days * 86400
  delay_seconds              = 0
  max_message_size           = 262144 # 256 KB
  receive_wait_time_seconds  = 20 # Long polling
  
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.tust_dlq.arn
    maxReceiveCount     = var.dlq_max_receive_count
  })
  
  tags = {
    Name     = "${var.project_name}-tasks-queue"
    Consumer = "TUST-Robot-Workers"
  }
}
