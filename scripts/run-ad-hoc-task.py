#!/usr/bin/env python3
import argparse
import time

import boto3

parser = argparse.ArgumentParser(description="Run ECS task with optional command.")
parser.add_argument(
    "--command",
    type=str,
    default="flask db upgrade",
    help="Command to run in the ECS task (default: 'flask db upgrade').",
)
parser.add_argument(
    "--print-logs",
    action="store_true",
    default=False,
    help="Print logs from CloudWatch (default: False).",
)
args = parser.parse_args()
print(f"Starting script to run command: {args.command}")

command = args.command.split()

cluster = "task-runner-cluster"
task_definition = "ad-hoc-ecs-task"
log_group_name = "/ecs/ad-hoc-task"
log_stream_prefix = "ecs/task-runner-container"

ec2_client = boto3.client("ec2")
ecs_client = boto3.client("ecs")
logs_client = boto3.client("logs")


# Fetch subnets and security groups with the specified tags
describe_subnets_response = ec2_client.describe_subnets(Filters=[{"Name": "tag:Tier", "Values": ["private"]}])

subnets = [subnet["SubnetId"] for subnet in describe_subnets_response["Subnets"]]
if not subnets:
    raise ValueError("No subnets found with the specified tag.")

security_group_response = ec2_client.describe_security_groups(
    Filters=[{"Name": "tag:Name", "Values": ["*-fs-default-sg"]}]
)
security_groups = [sg["GroupId"] for sg in security_group_response["SecurityGroups"]]
if not security_groups:
    raise ValueError("No security groups found with the specified tag.")


# Run the ECS task
run_task_response = ecs_client.run_task(
    cluster=cluster,
    taskDefinition=task_definition,
    launchType="FARGATE",
    networkConfiguration={
        "awsvpcConfiguration": {"subnets": subnets, "securityGroups": security_groups, "assignPublicIp": "DISABLED"}
    },
    overrides={"containerOverrides": [{"command": command, "name": "task-runner-container"}]},
)

task_arn = run_task_response["tasks"][0]["taskArn"]

# Wait for the task to complete
while True:
    run_task_response = ecs_client.describe_tasks(cluster=cluster, tasks=[task_arn])
    task = run_task_response["tasks"][0]
    last_status = task["lastStatus"]
    print(f"Task status: {last_status}")
    if last_status == "STOPPED":
        break
    time.sleep(10)

exit_code = task["containers"][0]["exitCode"]
print(f"Exit code: {exit_code}")

log_stream_name = f"{log_stream_prefix}/{task_arn.split('/')[-1]}"
if args.print_logs:
    log_events_response = logs_client.get_log_events(
        logGroupName=log_group_name, logStreamName=log_stream_name, startFromHead=True
    )
    print("Logs:")
    for event in log_events_response["events"]:
        print(event["message"])
else:
    print(f"""Check Cloudwatch for Logs:
    Log Group: {log_group_name}
    Log Stream: {log_stream_name}""")


# Reflect the exit code
exit(exit_code)
