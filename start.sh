#!/bin/bash
# Install missing packages at runtime if not in Docker image
pip install --no-cache-dir ccxt==4.5.75 "cryptography>=42.0.0" 2>/dev/null

# Start the bot
exec python -O main.py
