"""
Battery status helper for conky and other scripts.
Outputs battery info with time remaining.
"""

import sys

try:
    from ina219 import INA219
except ImportError:
    print("> N/A")
    sys.exit(0)

from .learning import (
    get_battery_learning,
    get_hybrid_soc,
    SHUNT_OHMS,
    I2C_ADDRESS,
    I2C_BUS,
)


def main():
    """Entry point for battery status output."""
    try:
        ina = INA219(SHUNT_OHMS, address=I2C_ADDRESS, busnum=I2C_BUS)
        ina.configure()
        voltage = ina.voltage()
        current = ina.current()
        power = ina.power()

        percent = get_hybrid_soc(voltage, current, power)

        bl = get_battery_learning()
        charging = bl.is_charging()

        status = " CHG" if charging else ""
        time_str = bl.format_time_remaining(percent, current)

        # Output formatted for conky
        print(f"> {percent:.0f}%{status}")
        if time_str:
            print(f"${{color4}}  {time_str}")

    except Exception:
        print("> ERR")


if __name__ == "__main__":
    main()
