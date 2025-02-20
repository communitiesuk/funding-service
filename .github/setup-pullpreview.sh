#!/bin/bash

docker-compose -f docker-compose.pullpreview.yml run funding-service bash -c "nvm use && uv run flask vite install && uv run flask vite build"
