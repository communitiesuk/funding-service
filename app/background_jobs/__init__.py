from flask import Blueprint

background_jobs_blueprint = Blueprint(
    name="background_jobs",
    import_name=__name__,
    cli_group="background-jobs",
)


from app.background_jobs import commands as commands  # noqa: E402, F401
