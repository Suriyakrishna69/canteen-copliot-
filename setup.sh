#!/bin/bash
set -e
echo "=== Installing Canteen Copilot Dependencies ==="
pip install -r requirements.txt

echo "=== Running Unit Tests ==="
python3 -m pytest tests/ -v

echo "=== Verifying Planted Operational Patterns ==="
python3 verify_patterns.py

echo "=== Ready! Run 'streamlit run app.py' to launch the web app ==="
