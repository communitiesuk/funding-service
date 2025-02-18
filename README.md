# Funding Service

## Local development setup

### Pre-requisites

- Node (version defined in  `./app/vite/.nvmrc`). We recommend using [nvm](https://github.com/nvm-sh/nvm) to manage node versions.
- [uv](https://github.com/astral-sh/uv) installed globally

### Quickstart

1. `make bootstrap`
2. `make up`

### Instructions

We use [uv](https://github.com/astral-sh/uv) for managing the local Python environment. Install this tool globally and then run `uv sync` in this repository to install the correct python version and python dependencies.

Developers are expected to run the app locally using [docker-compose](https://docs.docker.com/compose/). There are some helper commands in a Makefile to help bring up the service.

* `make bootstrap` will create a local self-signed certificate for HTTPS during development, and set up flask-vite/vite to compile GOV.UK Frontend/our frontend assets.
* `make up` / `docker compose up` will start the Funding Service app and expose it on https://funding.communities.gov.localhost:8080
* `make down` / `docker compose down` will stop the Funding Service.
* `make build` / `docker compose build` will rebuild the Funding Service image.
* `make clean-build` / `docker compose build --no-cache` will rebuild the Funding Service image, bypassing caching. This should rarely be needed.
