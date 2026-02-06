output "raw_bucket_name" { value = aws_s3_bucket.raw.id }
output "raw_bucket_arn" { value = aws_s3_bucket.raw.arn }
output "processed_bucket_name" { value = aws_s3_bucket.processed.id }
output "processed_bucket_arn" { value = aws_s3_bucket.processed.arn }
output "models_bucket_name" { value = aws_s3_bucket.models.id }
output "models_bucket_arn" { value = aws_s3_bucket.models.arn }
