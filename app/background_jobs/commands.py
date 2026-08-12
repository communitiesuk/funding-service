import signal
import time

import click
from flask import current_app

from app.background_jobs import background_jobs_blueprint
from app.common.data.interfaces.background_jobs import (
    claim_next_due_background_job,
    mark_background_job_completed,
    mark_background_job_failed,
    open_collection_for_submissions,
)
from app.common.data.types import BackgroundJobTypeEnum
from app.extensions import db

_should_stop = False


def _handle_stop_signal(signum: int, frame: object) -> None:
    del signum, frame
    global _should_stop
    _should_stop = True


def _process_one_job() -> bool:
    with db.session.begin():
        job = claim_next_due_background_job()
        if not job:
            return False

        current_app.logger.info(
            "Claimed background job %(job_id)s of type %(job_type)s",
            {"job_id": job.id, "job_type": job.job_type.name},
        )

        try:
            match job.job_type:
                case BackgroundJobTypeEnum.OPEN_COLLECTION_FOR_SUBMISSIONS:
                    open_collection_for_submissions(job)
                case _:
                    raise ValueError(f"Unsupported background job type: {job.job_type}")
        except Exception as e:
            mark_background_job_failed(job, error=e)
            current_app.logger.exception(
                "Background job %(job_id)s failed",
                {"job_id": job.id},
            )
            return True

        mark_background_job_completed(job)
        current_app.logger.info(
            "Completed background job %(job_id)s",
            {"job_id": job.id},
        )
        return True


@background_jobs_blueprint.cli.command("worker", help="Run the background job worker")
@click.option("--once", is_flag=True, help="Process currently due jobs once, then exit")
@click.option("--sleep-seconds", default=5, show_default=True, help="Seconds to sleep when no due jobs are found")
def worker(once: bool, sleep_seconds: int) -> None:
    """Run the background job worker.

    This command is intended to run permanently in ECS. Use --once for local checks or tests.
    """
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    current_app.logger.info("Starting background job worker")

    while not _should_stop:
        processed_job = _process_one_job()

        if once and not processed_job:
            break

        if not processed_job:
            time.sleep(sleep_seconds)

    current_app.logger.info("Stopping background job worker")
