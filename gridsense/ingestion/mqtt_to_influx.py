#!/usr/bin/env python3
"""
GridSense - Bridge Entrypoint
Redirects to mqtt_to_mysql.py per project architecture configuration (MySQL storage).
"""
import runpy
from pathlib import Path

if __name__ == "__main__":
    bridge_script = Path(__file__).parent / "mqtt_to_mysql.py"
    runpy.run_path(str(bridge_script), run_name="__main__")
