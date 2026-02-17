#!/bin/bash

# AWS_REGION is being overwritten by localstack on startup, the other environment vars passed in are respected
# This should be addressed in a future release https://github.com/localstack/localstack/issues/11387
AWS_REGION=eu-west-2
AWS_DEFAULT_REGION=eu-west-2

function create_aws_bucket {
  if awslocal s3 ls | grep -q "$1"; then
    echo "Bucket $1 already exists!"
  else
    awslocal s3api \
      create-bucket --bucket "$1" \
      --create-bucket-configuration LocationConstraint=$AWS_REGION \
      --region $AWS_REGION
    echo "Created bucket $1!"

    awslocal s3api \
      put-bucket-cors --bucket "$1" \
      --cors-configuration '{
        "CORSRules": [
          {
            "AllowedOrigins": ["*"],
            "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
            "AllowedHeaders": ["*"]
          }
        ]
      }'
    echo "Created CORS rule for $1!"
  fi
}

create_aws_bucket "$AWS_BUCKET_NAME"
