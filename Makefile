SHELL := bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

.PHONY: bootstrap
bootstrap: certs pre-commit vite clean-build

.PHONY: certs
certs:
	mkdir -p certs
	CAROOT=certs mkcert -install
	CAROOT=certs mkcert -cert-file certs/cert.pem -key-file certs/key.pem "funding.communities.gov.localhost"

.PHONY: pre-commit
pre-commit:
	uv run pre-commit install

.PHONY: vite
vite:
	# uv run flask vite install
	# uv run flask vite build

.PHONY: build
build:
	docker compose build

.PHONY: clean-build
clean-build:
	docker compose build --no-cache


.PHONY: up
up:
	docker compose up

.PHONY: down
down:
	docker compose down
