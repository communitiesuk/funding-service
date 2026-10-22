```
Title: Use AppRunner
Owner: Gideon Goldberg
Collaborator(s): Platform Team
Created on: 2025-04-25
Status: Approved
Finalised on: 2025-04-28
```

## Overview

We will continue to use AWS AppRunner until we hit a technical constraint, in which case we will switch to AWS ECS Fargate.

## What is the current state?

We currently use [AWS AppRunner](https://aws.amazon.com/apprunner/) to deploy our application container. This provides a simple way to deploy a container and provide a public secure URL, but is feature limited.


## Why should we change?

The proposal is not to change and that we will keep the current AWS AppRunner setup until we hit a technical constraint which makes it unviable.

[ECS Fargate](https://aws.amazon.com/fargate/) offers a range of advanced features not available in AppRunner such as:
* Sidecars
* Ability to run ad-hoc tasks
* Ability to make an SSH connection to the container
* Ability to use ARM architecture containers
* Additional networking features such as ECS Connect and full control over the associated load balancer


## How should we address this?

We have added an ECS cluster and associated script purely to run ad-hoc tasks such as database migrations.

We should continue to monitor if AppRunner meets our needs for the main application container.

## What alternatives are we discarding?

Switching immediately to ECS Fargate.

Since we have a working pipeline we have decided to continue with the current setup and prioritise application functionality over continuing to iterate our deployment pipeline.

## Who will be affected?

Developers on the team.

## Who will benefit?

More time will be freed up for developers to work on application functionality over continuing to work on the deployment pipeline

## What are the key risks to manage or mitigate?

We plan to make a Cloudfront Distribution the DNS entrypoint to the application. This provides a stable entrypoint we can use to switch the origin to ECS in future without involving IT to make DNS changes.

There is a risk we require functionality not offered by AppRunner at which point we would need to implement the switch to ECS Fargate

There is a risk a security issue is identified in a Pen Test which we are unable to mitigate due to limitations of AppRunner.

The mitigation is to keep requirements under review, so we can plan to switch to ECS Fargate in due course if required.
