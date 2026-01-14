#!/usr/bin/env python3
"""
Battery Safe Shutdown Daemon.
Monitors battery voltage and initiates safe shutdown at critical level.
"""

import os
import signal
import subprocess
import sys
import time

from .learning import (
    get_battery_learning,
    get_hybrid_soc,
    get_ina219_reader,
    CRITICAL_VOLTAGE,
)

# Configuration
CHECK_INTERVAL = 10  # seconds between checks
SHUTDOWN_VOLTAGE = 9.6  # Voltage threshold for shutdown
SHUTDOWN_PERCENT = 3  # Percent threshold for shutdown
CONSECUTIVE_LOW = 3  # Number of consecutive low readings before shutdown
WARN_BEFORE_SHUTDOWN = True

PID_FILE = "/tmp/battery_shutdown.pid"


def send_notification(title: str, message: str, urgency: str = "critical"):
    """Send notification via notify-send."""
    try:
        subprocess.run(
            ["notify-send", "-u", urgency, title, message],
            timeout=5,
            capture_output=True,
        )
    except Exception:
        pass


def safe_shutdown():
    """Initiate safe system shutdown."""
    print("Initiating safe shutdown due to low battery...")

    send_notification(
        "SHUTTING DOWN",
        "Battery critically low. System shutting down now.",
        urgency="critical",
    )

    time.sleep(2)

    try:
        subprocess.run(["sync"], timeout=10)
    except Exception:
        pass

    try:
        subprocess.run(["systemctl", "poweroff"], timeout=10)
    except Exception:
        try:
            subprocess.run(["sudo", "poweroff"], timeout=10)
        except Exception:
            pass


def is_running() -> bool:
    """Check if another instance is running."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
    return False


def write_pid():
    """Write PID file."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup(*args):
    """Clean up on exit."""
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    sys.exit(0)


def main():
    """Entry point for the shutdown daemon."""
    if is_running():
        print("Battery shutdown daemon already running", file=sys.stderr)
        sys.exit(1)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    write_pid()
    print(f"Battery shutdown daemon started (PID {os.getpid()})")
    print(f"Shutdown thresholds: {SHUTDOWN_VOLTAGE}V / {SHUTDOWN_PERCENT}%")

    try:
        ina = get_ina219_reader()
    except Exception as e:
        print(f"Error initializing INA219: {e}", file=sys.stderr)
        cleanup()

    learning = get_battery_learning()

    low_count = 0
    warned = False

    while True:
        try:
            voltage = ina.voltage()
            current = ina.current()
            power = ina.power()

            percent = get_hybrid_soc(voltage, current, power)
            charging = learning.is_charging()

            if not charging:
                if voltage <= SHUTDOWN_VOLTAGE or percent <= SHUTDOWN_PERCENT:
                    low_count += 1
                    print(
                        f"Low battery detected: {voltage:.2f}V / {percent:.0f}% "
                        f"(count: {low_count}/{CONSECUTIVE_LOW})"
                    )

                    if low_count == 1 and WARN_BEFORE_SHUTDOWN and not warned:
                        send_notification(
                            "CRITICAL BATTERY",
                            f"Battery at {percent:.0f}%! "
                            f"Shutdown in ~{CONSECUTIVE_LOW * CHECK_INTERVAL}s",
                            urgency="critical",
                        )
                        warned = True

                    if low_count >= CONSECUTIVE_LOW:
                        safe_shutdown()
                        break
                else:
                    if low_count > 0:
                        print(f"Battery recovered: {voltage:.2f}V / {percent:.0f}%")
                    low_count = 0
                    warned = False
            else:
                low_count = 0
                warned = False

        except Exception as e:
            print(f"Error reading battery: {e}", file=sys.stderr)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
