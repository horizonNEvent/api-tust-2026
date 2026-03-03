# ========================================
# Data Lake Raw Bucket
# ========================================

resource "aws_s3_bucket" "datalake_raw" {
  bucket = "${var.project_name}-${var.s3_bucket_name}-${var.environment}-${random_string.suffix.result}"
  
  tags = {
    Name = "${var.project_name}-datalake-raw"
  }
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}
