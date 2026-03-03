output "sqs_inbound_url" {
  value = aws_sqs_queue.tust_queue.url
}

output "sqs_dlq_url" {
  value = aws_sqs_queue.tust_dlq.url
}

output "dynamodb_idempotency_table" {
  value = aws_dynamodb_table.tust_idempotency.name
}

output "s3_datalake_raw" {
  value = aws_s3_bucket.tust_datalake.bucket
}

output "least_privilege_policy_arn" {
  value = aws_iam_policy.tust_worker_policy.arn
}
