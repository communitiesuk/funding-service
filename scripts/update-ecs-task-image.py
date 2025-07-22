#!/usr/bin/env python3
import sys

import boto3


def update_repository_url(cluster_name, service_name, container_name, new_repository_url):
    """
    Update the repository URL of an existing ECS task definition and update the service.

    Args:
        cluster_name (str): The name of the ECS cluster
        service_name (str): The name of the ECS service
        container_name (str): The name of the container to update
        new_repository_url (str): The new repository URL with tag
    """
    try:
        ecs_client = boto3.client("ecs")

        print(f"Retrieving current task definition for service {service_name} in cluster {cluster_name}...")

        # Get the current task definition ARN from the service
        service_response = ecs_client.describe_services(cluster=cluster_name, services=[service_name])

        if not service_response["services"]:
            raise Exception(f"Service {service_name} not found in cluster {cluster_name}")

        current_task_definition = service_response["services"][0]["taskDefinition"]

        task_definition_response = ecs_client.describe_task_definition(taskDefinition=current_task_definition)

        task_definition = task_definition_response["taskDefinition"]

        # Find and update the container image
        container_found = False
        for container in task_definition["containerDefinitions"]:
            if container["name"] == container_name:
                old_image = container["image"]
                container["image"] = new_repository_url
                container_found = True
                print(f"Updating container {container_name} image from {old_image} to {new_repository_url}")
                break

        if not container_found:
            raise Exception(f"Container {container_name} not found in task definition")

        # Remove fields that cannot be included when registering a new task definition
        for field in [
            "taskDefinitionArn",
            "revision",
            "status",
            "requiresAttributes",
            "compatibilities",
            "registeredAt",
            "registeredBy",
        ]:
            task_definition.pop(field, None)

        # Register the new task definition
        print("Registering new task definition...")
        register_response = ecs_client.register_task_definition(**task_definition)

        new_task_definition_arn = register_response["taskDefinition"]["taskDefinitionArn"]
        print(f"New task definition registered: {new_task_definition_arn}")

        # Update the service to use the new task definition
        print(f"Updating service {service_name} to use the new task definition...")
        ecs_client.update_service(cluster=cluster_name, service=service_name, taskDefinition=new_task_definition_arn)

        print(f"Service {service_name} updated successfully!")
        return True

    except Exception as e:
        print(f"Error: {str(e)}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update-task-v2.py <new_repository_url>")
        sys.exit(1)

    cluster_name = "task-runner-cluster"
    service_name = "task-runner"
    container_name = "task-runner-container"

    new_repository_url = sys.argv[1]

    print(f"  Cluster: {cluster_name}")
    print(f"  Service: {service_name}")
    print(f"  Container: {container_name}")
    print(f"  New Repository URL: {new_repository_url}")

    success = update_repository_url(cluster_name, service_name, container_name, new_repository_url)
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
