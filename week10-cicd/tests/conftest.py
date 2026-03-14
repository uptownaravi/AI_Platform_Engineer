"""
conftest.py — Adds project root to sys.path so 'agents' is importable
from the tests/ directory without a package install.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
