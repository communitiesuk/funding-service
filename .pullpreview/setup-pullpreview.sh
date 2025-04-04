#!/bin/bash

envsubst < .pullpreview/Caddyfile.template > .pullpreview/Caddyfile
docker-compose -f docker-compose.pullpreview.yml run web bash -c "nvm use && uv run flask vite install && uv run flask vite build"
