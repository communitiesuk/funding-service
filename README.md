# Funding Service

## Local development setup

### Pre-requisites

- Node (version defined in  `./app/vite/.nvmrc`). We recommend using [nvm](https://github.com/nvm-sh/nvm) to manage node versions.
- [uv](https://github.com/astral-sh/uv) installed globally
- Copy .env.example to fresh .env file and leave values as is or use [direnv](https://direnv.net/)/.envrc for these variables

### Quickstart

1. `nvm use`
2. `make bootstrap`
3. `make up`

If you see permission errors around certs (eg. `ERROR: failed to read the CA key: open certs/rootCA-key.pem: permission denied`) follow these instructions instead of step 2. above.

Assumes your are on an MHCLG-managed macbook and you have 2 accounts. Your ADMIN_USER is the account with full admin permissions, and your STANDARD_USER is the normal account you use for day to day work.
1. `su <ADMIN_USER>`
2. `sudo make certs`  Read the output - should be no apparent errors.
3. `chown -R <STANDARD_USER>:staff certs`
4. `exit` to return to your standard user shell.
5. `make pre-commit`
6. `make vite`
7. `make clean-build`
8. Continue with step 3. above

* If you hit the error `SecTrustSettingsSetTrustSettings: The authorization was denied since no user interaction was possible.` when doing the above `su -` steps, then you may need to actually logout and login as your admin user instead of using `su`
* If you subsequently hit git errors that mention `dubious ownership in repository` this is to do with changing the directory permissions above. A terminal restart should fix this.

### Instructions

We use [uv](https://github.com/astral-sh/uv) for managing the local Python environment. Install this tool globally and then run `uv sync` in this repository to install the correct python version and python dependencies.

Developers are expected to run the app locally using [docker-compose](https://docs.docker.com/compose/). There are some helper commands in a Makefile to help bring up the service.

* `make bootstrap` will create a local self-signed certificate for HTTPS during development, and set up flask-vite/vite to compile GOV.UK Frontend/our frontend assets.
* `make up` / `docker compose up` will start the Funding Service app and expose it on https://funding.communities.gov.localhost:8080
* `make down` / `docker compose down` will stop the Funding Service.
* `make build` / `docker compose build` will rebuild the Funding Service image.
* `make clean-build` / `docker compose build --no-cache` will rebuild the Funding Service image, bypassing caching. This should rarely be needed.
