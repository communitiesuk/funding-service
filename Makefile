SHELL := bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

.PHONY: bootstrap
bootstrap: certs pre-commit vite clean-build

.PHONY: certs
certs:
	mkdir -p certs
	CAROOT=certs mkcert -install
	CAROOT=certs mkcert -cert-file certs/cert.pem -key-file certs/key.pem "*.communities.gov.localhost"

.PHONY: pre-commit
pre-commit:
	uv run pre-commit install

.PHONY: vite
vite:
	npm install
	npm run build

.PHONY: check-html
check-html:
	npx prettier --check **/*.html

.PHONY: format-html
format-html:
	npx prettier --write **/*.html

.PHONY: format-css-js
format-css-js:
	npx prettier --write "**/*.{js,css,sass,scss}"

.PHONY: format-frontend
format-frontend: format-css-js format-html


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

.PHONY: clean-down
clean-down:
	docker compose down --remove-orphans --rmi all --volumes
