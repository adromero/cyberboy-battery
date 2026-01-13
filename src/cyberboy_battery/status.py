#!/usr/bin/env python3
"""
Battery status helper for conky and other scripts.
Outputs battery info with time remaining.
Reads state from tray daemon via shared file.
"""

import sys
import json

# Shared state file written by tray daemon
BATTERY_STATE_FILE = "/tmp/cyberboy_battery_state.json"


def main():
    """Entry point for battery status output."""
    try:
        with open(BATTERY_STATE_FILE, "r") as f:
            state = json.load(f)

        percent = state.get("percent", 0)
        charging = state.get("charging", False)
        time_str = state.get("time_str", "")

        status = " CHG" if charging else ""

        # Output formatted for conky
        print(f"> {percent:.0f}%{status}")
        if time_str:
            print(f"${{color4}}  {time_str}")

    except FileNotFoundError:
        print("> N/A")
        print("${color4}  No battery daemon")
    except Exception:
        print("> ERR")


if __name__ == "__main__":
    main()
