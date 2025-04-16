import boto3
import time
import argparse

# Parse script arguments
parser = argparse.ArgumentParser(description='Run ECS task and fetch logs.')
parser.add_argument('--subnets', required=True, help='Comma-separated list of subnet IDs')
parser.add_argument('--security-groups', required=True, help='Comma-separated list of security group IDs')
args = parser.parse_args()

subnets = args.subnets.split(',')
security_groups = args.security_groups.split(',')

ecs_client = boto3.client('ecs')
logs_client = boto3.client('logs')

cluster = 'task-runner-cluster'
task_definition = 'ad-hoc-ecs-task'
log_group_name = '/ecs/ad-hoc-task'
log_stream_prefix = 'ecs'

# Run the ECS task
response = ecs_client.run_task(
    cluster=cluster,
    taskDefinition=task_definition,
    launchType='FARGATE',
    networkConfiguration={
        'awsvpcConfiguration': {
            'subnets': subnets,
            'securityGroups': security_groups,
            'assignPublicIp': 'DISABLED'
        }
    }
    overrides={
        "containerOverrides":[{
            "command":["flask", "db", "current"],
            "name": "task-runner-container"}]
    }
)

task_arn = response['tasks'][0]['taskArn']
print(f'Task ARN: {task_arn}')

# Wait for the task to complete
while True:
    response = ecs_client.describe_tasks(cluster=cluster, tasks=[task_arn])
    task = response['tasks'][0]
    last_status = task['lastStatus']
    print(f'Task status: {last_status}')
    if last_status == 'STOPPED':
        break
    time.sleep(10)

# Get the exit code
exit_code = task['containers'][0]['exitCode']
print(f'Exit code: {exit_code}')

# Fetch logs
log_stream_name = f'{log_stream_prefix}/{task_arn.split("/")[-1]}'
response = logs_client.get_log_events(
    logGroupName=log_group_name,
    logStreamName=log_stream_name,
    startFromHead=True
)

print('Logs:')
for event in response['events']:
    print(event['message'])

# Reflect the exit code
exit(exit_code)