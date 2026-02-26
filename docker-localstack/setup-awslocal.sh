#!/bin/bash

if ! awslocal s3 ls | grep -q "$AWS_S3_BUCKET_NAME"; then
    awslocal s3api create-bucket --bucket $AWS_S3_BUCKET_NAME \
        --create-bucket-configuration LocationConstraint=$AWS_REGION
    echo "Created bucket $AWS_S3_BUCKET_NAME"
fi
