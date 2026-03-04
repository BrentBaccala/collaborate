#!/bin/bash -e

dconf update

# Disable release upgrade prompts (BBB requires Ubuntu 22.04)
sed -i 's/^Prompt=.*/Prompt=never/' /etc/update-manager/release-upgrades
