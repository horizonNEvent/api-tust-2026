output "sqs_tust_queue_url" {
  value = aws_sqs_queue.tust_queue.url
}

output "sqs_tust_dlq_url" {
  value = aws_sqs_queue.tust_dlq.url
}

output "dynamodb_idempotency_table_name" {
  value = aws_dynamodb_table.idempotency.name
}

output "s3_datalake_raw_bucket" {
  value = aws_s3_bucket.datalake_raw.bucket
}

output "api_role_arn" {
  value = aws_iam_role.api_role.arn
}

output "worker_role_arn" {
  value = aws_iam_role.worker_role.arn
}
