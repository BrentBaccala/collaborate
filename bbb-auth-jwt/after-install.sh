#!/bin/bash -e

startService bbb-auth-jwt || echo "bbb-auth-jwt service could not be registered or started"

reloadService nginx
