#!/bin/sh
set -eu
for brand in a b c; do
    queue="brand-$brand-orders"
    dlq_url=$(awslocal sqs create-queue --queue-name "$queue-dlq" --query QueueUrl --output text)
    dlq_arn=$(awslocal sqs get-queue-attributes --queue-url "$dlq_url" \
        --attribute-names QueueArn --query Attributes.QueueArn --output text)
    attributes=$(printf '{"VisibilityTimeout":"%s","RedrivePolicy":"{\\"deadLetterTargetArn\\":\\"%s\\",\\"maxReceiveCount\\":\\"%s\\"}"}' \
        "$SQS_VISIBILITY_TIMEOUT" "$dlq_arn" "$SQS_MAX_RECEIVE_COUNT")
    awslocal sqs create-queue --queue-name "$queue" --attributes "$attributes"
done
