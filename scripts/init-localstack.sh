#!/bin/bash
# =============================================================================
# LocalStack Initialization - SQS Queues
# =============================================================================

set -e

echo "Initializing SQS queues..."

# Create Dead Letter Queues
awslocal sqs create-queue --queue-name training-dlq \
    --attributes '{"MessageRetentionPeriod": "1209600"}'

awslocal sqs create-queue --queue-name prediction-dlq \
    --attributes '{"MessageRetentionPeriod": "1209600"}'

# Get DLQ ARNs
TRAINING_DLQ_ARN=$(awslocal sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/training-dlq \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' --output text)

PREDICTION_DLQ_ARN=$(awslocal sqs get-queue-attributes \
    --queue-url http://localhost:4566/000000000000/prediction-dlq \
    --attribute-names QueueArn \
    --query 'Attributes.QueueArn' --output text)

# Create main queues with redrive policy
awslocal sqs create-queue --queue-name training-queue \
    --attributes '{
        "VisibilityTimeout": "900",
        "MessageRetentionPeriod": "345600",
        "ReceiveMessageWaitTimeSeconds": "20",
        "RedrivePolicy": "{\"deadLetterTargetArn\":\"'$TRAINING_DLQ_ARN'\",\"maxReceiveCount\":\"3\"}"
    }'

awslocal sqs create-queue --queue-name prediction-queue \
    --attributes '{
        "VisibilityTimeout": "60",
        "MessageRetentionPeriod": "86400",
        "ReceiveMessageWaitTimeSeconds": "10",
        "RedrivePolicy": "{\"deadLetterTargetArn\":\"'$PREDICTION_DLQ_ARN'\",\"maxReceiveCount\":\"5\"}"
    }'

echo "SQS queues created:"
awslocal sqs list-queues
