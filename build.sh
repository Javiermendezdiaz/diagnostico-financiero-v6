#!/bin/bash
set -e

echo "Building dependencies..."
python --version
pip install --upgrade pip setuptools wheel --quiet
pip install --prefer-binary --no-cache-dir --only-binary :all: -r requirements.txt
echo "Build complete."
