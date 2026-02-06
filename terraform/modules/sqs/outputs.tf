output "training_queue_url" { value = aws_sqs_queue.training.url }
output "training_queue_arn" { value = aws_sqs_queue.training.arn }
output "prediction_queue_url" { value = aws_sqs_queue.prediction.url }
output "prediction_queue_arn" { value = aws_sqs_queue.prediction.arn }
output "training_dlq_url" { value = aws_sqs_queue.training_dlq.url }
output "prediction_dlq_url" { value = aws_sqs_queue.prediction_dlq.url }
