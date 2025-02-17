# Funding Service

## Local development setup

### Quickstart

1. `uv sync`
2. `make certs`
3. `make up`

### Instructions

We use [uv](https://github.com/astral-sh/uv) for managing the local Python environment. Install this tool globally and then run `uv sync` in this repository to install the correct python version and python dependencies.

Developers are expected to run the app locally using [docker-compose](https://docs.docker.com/compose/). There are some helper commands in a Makefile to help bring up the service.

* `make certs` will create a local self-signed certificate for HTTPS during development.
* `make up` / `docker compose up` will start the Funding Service app and expose it on https://funding.communities.gov.localhost:8080
* `make down` / `docker compose down` will stop the Funding Service.
* `make build` / `docker compose build` will rebuild the Funding Service image.
* `make clean-build` / `docker compose build --no-cache` will rebuild the Funding Service image, bypassing caching. This should rarely be needed.
