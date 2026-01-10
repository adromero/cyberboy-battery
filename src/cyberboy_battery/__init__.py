"""
Cyberboy Battery - Battery monitoring suite for Raspberry Pi with INA219 sensor.

This package provides:
- Hybrid SOC estimation (coulomb counting + voltage calibration)
- System tray indicator
- Screen overlay widget
- Safe shutdown daemon
- CSV logging for battery analysis
"""

__version__ = "1.0.0"
__author__ = "Alfonso"

from .learning import (
    BatteryLearning,
    get_battery_learning,
    get_hybrid_soc,
    voltage_to_percent,
    DISCHARGE_CURVE,
    VOLT_MIN,
    VOLT_MAX,
    CRITICAL_VOLTAGE,
    LOW_VOLTAGE_WARN,
    NOMINAL_CAPACITY_MAH,
    SHUNT_OHMS,
    I2C_ADDRESS,
    I2C_BUS,
)

__all__ = [
    "BatteryLearning",
    "get_battery_learning",
    "get_hybrid_soc",
    "voltage_to_percent",
    "DISCHARGE_CURVE",
    "VOLT_MIN",
    "VOLT_MAX",
    "CRITICAL_VOLTAGE",
    "LOW_VOLTAGE_WARN",
    "NOMINAL_CAPACITY_MAH",
    "SHUNT_OHMS",
    "I2C_ADDRESS",
    "I2C_BUS",
]
