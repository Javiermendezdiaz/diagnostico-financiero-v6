#!/bin/bash
set -e

echo "Installing dependencies from requirements.txt..."
echo "Python version:"
python --version
echo "Pip version:"
pip --version
echo ""
echo "Upgrading pip and setuptools..."
pip install --upgrade pip setuptools wheel
echo ""
echo "Installing packages..."
pip install --prefer-binary --no-cache-dir -r requirements.txt
echo "Installation complete."
echo ""
echo "Verifying installation..."
python -c "import fastapi; print('FastAPI version:', fastapi.__version__)"
python -c "import uvicorn; print('Uvicorn available')"
echo ""
echo "Build complete. Application ready to start."
