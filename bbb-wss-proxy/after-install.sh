#!/bin/bash -e

startService bbb-wss-proxy || echo "bbb-wss-proxy service could not be registered or started"

reloadService nginx
