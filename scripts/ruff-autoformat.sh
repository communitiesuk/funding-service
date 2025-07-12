#!/usr/bin/env bash

uv run ruff check --fix $1 && uv run ruff format $1
