# Funding Service

## Local development setup

### Pre-requisites

- Node (version defined in  `.nvmrc`). We recommend using [nvm](https://github.com/nvm-sh/nvm) to manage node versions.
- [uv](https://github.com/astral-sh/uv) installed globally
- Copy .env.example to fresh .env file and leave values as is, or use [direnv](https://direnv.net/)/.envrc for these variables.
- [mkcert](https://github.com/FiloSottile/mkcert) installed

### Quickstart

1. `nvm use`
2. `make bootstrap`
3. `make up`
4. Access at https://funding.communities.gov.localhost:8080/

## Troubleshooting

### Permission errors

If you see permission errors around certs (eg.
`ERROR: failed to read the CA key: open certs/rootCA-key.pem: permission denied`) follow these instructions instead of step 2. above.

Assumes your are on an MHCLG-managed macbook and you have 2 accounts. Your ADMIN_USER is the account with full admin permissions, and your STANDARD_USER is the normal account you use for day to day work.

1. `su <ADMIN_USER>`
2. `sudo make certs`  Read the output - should be no apparent errors.
3. `chown -R <STANDARD_USER>:staff certs`
4. `exit` to return to your standard user shell.
5. `make pre-commit`
6. `make vite`
7. `make clean-build`
8. Continue with step 3. above

* If you hit the error
  `SecTrustSettingsSetTrustSettings: The authorization was denied since no user interaction was possible.` when doing the above
  `su -` steps, then you may need to actually logout and login as your admin user instead of using `su`
* If you subsequently hit git errors that mention
  `dubious ownership in repository` this is to do with changing the directory permissions above. A terminal restart should fix this.

### Weird Docker Errors

If docker gives weird errors despite multiple rebuilds, try deleting all containers, images and volumes with
`make clean-down`.

> [!WARNING]
> This will remove ALL docker containers, images, networks and volumes, not just those relating to the Funding Service.

## Instructions

We use [uv](https://github.com/astral-sh/uv) for managing the local Python environment. Install this tool globally and then run
`uv sync` in this repository to install the correct python version and python dependencies.

Developers are expected to run the app locally using [docker-compose](https://docs.docker.com/compose/). There are some helper commands in a Makefile to help bring up the service.

* `make bootstrap` will create a local self-signed certificate for HTTPS during development, and set up flask-vite/vite
  to compile GOV.UK Frontend/our frontend assets.
* `make up` /
  `docker compose up` will start the Funding Service app and expose it on https://funding.communities.gov.localhost:8080
* `make down` / `docker compose down` will stop the Funding Service.
* `make build` / `docker compose build` will rebuild the Funding Service image.
* `make clean-build` /
  `docker compose build --no-cache` will rebuild the Funding Service image, bypassing caching. This should rarely be needed.
* `make check-html` /
  `make format-html` will check or format Jinja HTML templates with Prettier. This is also run as part of the pre-commit checks.
* `make clean-down` will run `make down` then delete all images, containers, networks and volumes from docker

### SSO

By default, local development and locally-run end to end tests use a [stub server](./stubs/sso/) to implement the same interface as Microsoft SSO flow. This is so we can reliably run e2e tests locally without hitting the real SSO endpoints, and so devs don't need test Azure AD credentials to be able to use the app, making initial setup easier.

If you need to allow real SSO login locally, update the environment variables for `AZURE_AD_CLIENT_ID`,
`AZURE_AD_CLIENT_SECRET` and `AZURE_AD_TENANT_ID` to those used by the test Azure AD and add an environment variable of
`AZURE_AD_BASE_URL=https://login.microsoftonline.com/` in your .env file, or comment out the LocalConfig version of this variable in the config so it falls back to the BaseConfig default. Be aware that the SSO e2e test will fail while this is enabled - don't forget to switch back to check this passes.

# Tests

## E2E Tests

All E2E (browser) tests should live inside [/tests/e2e](./tests/e2e).

As a one-off setup step, run `uv run playwright install` to download and configure the browsers needed for these tests.

To run any E2E tests include the `e2e` option in the pytest command:

```shell
uv run pytest --e2e
```

This will, by default, run the browser tests headless - i.e. you won't see a browser appear.

To display the browser so you can visually inspect the test journey, add the `--headed` flag.

To slow the test down, add
`--slowmo 1000` to have Playwright insert 1 second pauses between each step so that you can follow what the test is doing more easily.

[This function](./tests/conftest.py#L22) skips e2e or non-e2e tests depending on if they are in the `e2e` module under
`tests`, so no individual tests need to be marked with the `e2e` marker.

### Pre-requisites for E2E tests in deployed environments

In order for the E2E tests to run against deployed environments (either kicked off locally or as part of the deployment pipeline) we mock session cookies for specific user types (currently a Platform Admin and a Grant Team Member on Deliver Grant Funding). These require us to have users with specific email addresses created in the database, and in the case of the Platform Admin they need the Platform Admin role. The IDs of these pre-existing users are stored in the AWS Parameter Store for each environment.

If the database is reset and wiped, these two users and the role will need to be manually added to the databases online -
`svc-Preaward-Funds@test.communities.gov.uk` as the Platform Admin user and role, and
`svc-Preaward-Funds@communities.gov.uk` as a normal user without any role.

If adding them to an empty database (either via the ad-hoc script or via the Query editor in AWS), be sure to use the correct IDs from the Parameter Store as the IDs of these users.

### Run E2E tests against an AWS environment

Additional flags must be passed to the `pytest` command:

* dev: `--e2e-env dev --e2e-aws-vault-profile <your_dev_aws_profile_name>`
* test: `--e2e-env test --e2e-aws-vault-profile <your_test_aws_profile_name>`

### Run E2E tests against a local environment with SSO

By default the e2e test config assumes that locally you are running with the stub SSO server, and this is the default for docker compose.

However, if you have enabled SSO locally as per [the instructions above](#sso), you can still run the e2e tests against your local environment as follows:

- PreRequisites:
    - Login locally using the SSO stub server with the email address
      `svc-Preaward-Funds@test.communities.gov.uk`, and tick the "Platform admin type login" option.
    - Add
      `svc-Preaward-Funds@communities.gov.uk` to a local grant as a grant team member, and login locally through the SSO stub service using that email address, unticking the "Platform admin type login" option.
- Update your local `.env` file with the UUIDs that match these users, `svc-Preaward-Funds@test.communities.gov.uk` and
  `svc-Preaward-Funds@communities.gov.uk`, in your local database:
  `SELECT * from "user" where email in ('svc-Preaward-Funds@test.communities.gov.uk','svc-Preaward-Funds@communities.gov.uk');`
- Edit [authenticated_browser_sso()](./tests/e2e/conftest.py) to use 'login_with_session_cookie()' for the local env.

## Seed data

We have some sample grant configuration exported at
`app/developers/data/grants.json`. This data will be loaded automatically into your developer environment during docker-compose startup.

To run a manual load:

```bash
uv run flask developers seed-grants
```

### Refreshing grant exports

If you make an update to the grant that you want to be persisted and synced for all other developers, run:

```bash
uv run flask developers export-grants
```

Then commit the change, create a PR and get it merged. Developer environments will sync the changes automatically when their app starts up again.

### Seeding for performance testing

If you need a large amount of submissions in a grant to test performance, you can use the
`seed-grants-many-submissions` command:

```bash
uv run flask developers seed-grants-many-submissions
```

This creates 2 grants with 100 submissions each - one with conditional questions, one with one question of each existing type in the database. The responses use the
`Faker` module to generate random answers.

Using this in conjunction with the flask debug toolbar allows you to see the number and timing of queries for operations in the tool.

For routes that don't result in a template render, eg Export to CSV, hack that route to return any template after generating the csv, and then the flask debug toolbar still shows you the performance data.

The following tests are skipped, but were also developed to help test performance. They are skipped at the moment because the factory setup caches the data, so there are actually no wueries executed when generating the CSV file. TODO: See if we can clear out the session between factory creation and CSV export to stop this happening.

- tests.integration.common.helpers.test_collections::test_multiple_submission_export_non_conditional
- tests.integration.common.helpers.test_collections::test_multiple_submission_export_conditional

# IDE setup

## PyCharm

- If you need a license for PyCharm Pro, contact your line manager.

### Ruff

To enable ruff format on save and linting in PyCharm, you need to install the [Ruff plugin](https://plugins.jetbrains.com/plugin/20574-ruff).

The ruff config file is committed to git at
`.idea/ruff.xml` so should be picked up automatically once you install the plugin.

### Unit Tests

The configuration for running unit tests is also committed to git. You should just be able to right click a test file or directory, or use the little green triangle icons on a source file, to run and debug tests.
