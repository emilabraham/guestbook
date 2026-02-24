#!/bin/bash
# Copies frontend files to the web root.
# Run with sudo: sudo ./deploy.sh
set -e
cp /home/emil/guestbook/static/index.html /var/www/guestbook/index.html
echo "Deployed."
