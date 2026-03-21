"""
warrantyAI — Week 11
tests/conftest.py

Ensures the week11-observability root is on sys.path so that
`from agents.classifier import ...` and `from observability.xxx import ...`
resolve correctly when running pytest from the project root.
"""

import sys
import os

# Add the week11 root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
