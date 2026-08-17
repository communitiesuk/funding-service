#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "boto3>=1.43",
#   "click",
# ]
# ///
"""Deploy an image to the environment's ECS Express service and wait for the rollout.

Exits non-zero if the rollout doesn't complete.
"""

import time

import boto3
import click

POLL_INTERVAL_SECONDS = 15


def settled_configuration(ecs, service_arn, deadline, target_image=None):
    """Wait until the service has exactly one active configuration, then return it.

    A rollout in progress shows two active configurations (steady + canary);
    a settled service shows one - whichever revision won. Updates to ECS can
    take a bit of time to show up (ie they're not "consistent" for all subsequent
    API calls) so we can optionally pass a 'target_image' to explicitly wait for.
    """
    rollout_seen = False
    while time.time() < deadline:
        service = ecs.describe_express_gateway_service(serviceArn=service_arn)["service"]
        configurations = service["activeConfigurations"]
        if len(configurations) == 1:
            image = configurations[0]["primaryContainer"]["image"]
            if target_image is None or image == target_image or rollout_seen:
                return configurations[0]
            click.echo("Rollout not yet visible - waiting...")
        else:
            rollout_seen = True
            click.echo(f"Rollout in progress ({len(configurations)} active configurations) - waiting...")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise click.ClickException("timed out waiting for the rollout to settle.")


@click.command()
@click.argument("image")
@click.option("--environment", required=True, type=click.Choice(["dev", "test", "prod"]))
@click.option("--timeout-seconds", default=900, show_default=True, help="Max seconds to wait for the rollout.")
def main(image, environment, timeout_seconds):
    """Update the ECS Express service to IMAGE and wait for the rollout."""
    # The Express service, its cluster and the underlying ECS service all share this name.
    name = f"{environment}-funding-service"

    ecs = boto3.client("ecs")

    # An Express service *is* an ECS service (resourceManagementType ECS), so
    # the standard service ARN doubles as the Express service ARN - the
    # Express API has no list operation of its own.
    services = ecs.describe_services(cluster=name, services=[name])["services"]
    if not services:
        raise click.ClickException(f"no ECS Express service '{name}' in cluster '{name}'.")
    service_arn = services[0]["serviceArn"]

    deadline = time.time() + timeout_seconds

    # Let any in-flight rollout settle before basing an update on the live config.
    current = settled_configuration(ecs, service_arn, deadline)

    if current["primaryContainer"]["image"] == image:
        click.echo(f"ECS Express service is already running {image} - nothing to do.")
        return

    # Send the whole live container config back with only the image
    # swapped, so env vars and secrets can't be clobbered if the API treats
    # primaryContainer as a whole-value replacement rather than a merge.
    container = current["primaryContainer"]
    click.echo(f"Updating image from {container['image']} to {image}")
    container["image"] = image

    updated = ecs.update_express_gateway_service(serviceArn=service_arn, primaryContainer=container)
    revision = updated["service"].get("targetConfiguration", {}).get("serviceRevisionArn", "pending")
    click.echo(f"Rollout started; target service revision: {revision}")

    final_image = settled_configuration(ecs, service_arn, deadline, target_image=image)["primaryContainer"]["image"]
    if final_image != image:
        raise click.ClickException(
            f"service settled on {final_image}, expected {image} - "
            "the rollout was rolled back (canary failure / deployment alarm)."
        )
    click.echo("ECS Express rollout complete.")


if __name__ == "__main__":
    main()
