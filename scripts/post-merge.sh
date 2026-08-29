#!/usr/bin/env bash
set -e
echo "Post-merge setup: installing Python dependencies..."
pip install -r requirements.txt --quiet
echo "Post-merge setup complete."
