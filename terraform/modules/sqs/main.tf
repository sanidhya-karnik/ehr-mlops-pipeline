# =============================================================================
# SQS Module - Message Queues for ML Pipeline
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Training Queue DLQ
resource "aws_sqs_queue" "training_dlq" {
  name                      = "${var.project}-${var.environment}-training-dlq"
  message_retention_seconds = 1209600
  tags                      = var.tags
}

# Training Queue
resource "aws_sqs_queue" "training" {
  name                       = "${var.project}-${var.environment}-training"
  visibility_timeout_seconds = 900  # 15 min for training jobs
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.training_dlq.arn
    maxReceiveCount     = 3
  })

  tags = var.tags
}

# Prediction Queue DLQ
resource "aws_sqs_queue" "prediction_dlq" {
  name                      = "${var.project}-${var.environment}-prediction-dlq"
  message_retention_seconds = 1209600
  tags                      = var.tags
}

# Prediction Queue
resource "aws_sqs_queue" "prediction" {
  name                       = "${var.project}-${var.environment}-prediction"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 10

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.prediction_dlq.arn
    maxReceiveCount     = 5
  })

  tags = var.tags
}

# CloudWatch Alarm for DLQ
resource "aws_cloudwatch_metric_alarm" "dlq_alarm" {
  alarm_name          = "${var.project}-${var.environment}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "DLQ has failed messages"

  dimensions = {
    QueueName = aws_sqs_queue.training_dlq.name
  }

  tags = var.tags
}
