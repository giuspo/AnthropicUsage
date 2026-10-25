"""Convenience entry point for local execution."""

import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from claude_usage.main import main

if __name__ == "__main__":
    main()
