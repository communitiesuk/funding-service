#!/bin/bash

if ! command -v awslocal; then
    # the s3-latest image of localstack does not bundle awslocal but is ~800MB smaller
    pip install awscli-local[ver1] --quiet
    echo "Installed awslocal"
fi

if ! awslocal s3 ls | grep -q "$AWS_S3_BUCKET_NAME"; then
    awslocal s3api create-bucket --bucket $AWS_S3_BUCKET_NAME \
        --create-bucket-configuration LocationConstraint=$AWS_REGION
    echo "Created bucket $AWS_S3_BUCKET_NAME"
fi
