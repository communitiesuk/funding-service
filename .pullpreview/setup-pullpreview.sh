#!/bin/bash

envsubst < .pullpreview/Caddyfile.template > .pullpreview/Caddyfile
docker-compose -f docker-compose.pullpreview.yml run web bash -c "nvm use && npm i && npm run build"
