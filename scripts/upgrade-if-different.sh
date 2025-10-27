#!/usr/bin/env bash
set -Eeuo pipefail

# EXPECTED should be provided as an environment variable
if [[ -z "${EXPECTED:-}" ]]; then
  echo "ERROR: EXPECTED env var is not set."
  exit 1
fi

echo "EXPECTED revision: $EXPECTED"

# Get the current revision from the database using Flask-Migrate
REMOTE_CURRENT="$(flask db current | awk '/^[0-9a-f]{10,}/{print $1; exit}')"

if [[ -z "${REMOTE_CURRENT:-}" ]]; then
  echo "ERROR: Could not determine remote current revision."
  exit 1
fi

echo "REMOTE_CURRENT revision: $REMOTE_CURRENT"

# Compare and act
if [[ "$REMOTE_CURRENT" == "$EXPECTED" ]]; then
  echo "Revisions match; no upgrade needed."
  exit 0
else
  echo "Revisions differ; running flask db upgrade..."
  flask db upgrade
  echo "Upgrade complete."
fi
