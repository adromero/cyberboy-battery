"""
Battery Learning Module - Hybrid SOC using coulomb counting + voltage calibration.
Tracks discharge patterns and estimates time remaining.
Learns from actual usage to improve accuracy over time.
"""

import csv
import json
import subprocess
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Lock

# Data storage location
DATA_DIR = Path.home() / ".local" / "share" / "cyberboy-battery"
LEARNED_FILE = DATA_DIR / "learned_data.json"
CSV_LOG_DIR = DATA_DIR / "logs"

# Battery configuration (3S Li-ion default)
NOMINAL_CAPACITY_MAH = 3400  # Adjust for your battery
SHUNT_OHMS = 0.1
I2C_ADDRESS = 0x41
I2C_BUS = 1

# 3S Li-ion discharge curve (voltage -> percent)
# More data points in the flat middle region for better accuracy
DISCHARGE_CURVE = [
    (12.60, 100),
    (12.50, 95),
    (12.40, 90),
    (12.30, 85),
    (12.20, 80),
    (12.00, 75),
    (11.90, 70),
    (11.80, 65),
    (11.70, 60),
    (11.60, 55),
    (11.50, 50),
    (11.40, 45),
    (11.30, 40),
    (11.20, 35),
    (11.10, 30),
    (11.00, 25),
    (10.80, 20),
    (10.60, 15),
    (10.40, 10),
    (10.20, 7),
    (10.00, 5),
    (9.80, 3),
    (9.60, 2),
    (9.40, 1),
    (9.00, 0),
]

# Voltage thresholds
VOLT_MIN = 9.0
VOLT_MAX = 12.6

# Warning thresholds
LOW_VOLTAGE_WARN = 10.2  # ~7%
CRITICAL_VOLTAGE = 9.6  # ~2%

# Notification thresholds (percent)
WARN_THRESHOLDS = [20, 10, 5]
CRITICAL_THRESHOLD = 5

# Charging detection
CHARGE_CURRENT_THRESHOLD = 10  # mA - above this = charging
CHARGE_VOLTAGE_SETTLED_TIME = 30  # seconds after unplug before trusting voltage


def voltage_to_percent(voltage: float) -> float:
    """Convert voltage to percentage using Li-ion discharge curve."""
    if voltage >= DISCHARGE_CURVE[0][0]:
        return 100.0
    if voltage <= DISCHARGE_CURVE[-1][0]:
        return 0.0

    for i in range(len(DISCHARGE_CURVE) - 1):
        v_high, p_high = DISCHARGE_CURVE[i]
        v_low, p_low = DISCHARGE_CURVE[i + 1]
        if v_low <= voltage <= v_high:
            ratio = (voltage - v_low) / (v_high - v_low)
            return p_low + ratio * (p_high - p_low)
    return 0.0


def percent_to_voltage(percent: float) -> float:
    """Convert percentage to expected voltage (for calibration)."""
    if percent >= 100:
        return DISCHARGE_CURVE[0][0]
    if percent <= 0:
        return DISCHARGE_CURVE[-1][0]

    for i in range(len(DISCHARGE_CURVE) - 1):
        v_high, p_high = DISCHARGE_CURVE[i]
        v_low, p_low = DISCHARGE_CURVE[i + 1]
        if p_low <= percent <= p_high:
            ratio = (percent - p_low) / (p_high - p_low)
            return v_low + ratio * (v_high - v_low)
    return VOLT_MIN


class BatteryLearning:
    """
    Hybrid SOC estimation using coulomb counting with voltage calibration.

    - Uses coulomb counting for smooth, accurate tracking during operation
    - Uses voltage to calibrate/reset SOC at known points (full charge, empty)
    - Learns actual capacity from discharge cycles
    """

    def __init__(self):
        self._lock = Lock()
        self._ensure_data_dir()

        # Recent samples for averaging (last 60 samples = ~5 min at 5s intervals)
        self._recent_current = deque(maxlen=60)
        self._recent_power = deque(maxlen=60)

        # Hybrid SOC tracking
        self._coulomb_soc = None  # Coulomb-counted SOC (0-100)
        self._voltage_soc = None  # Voltage-based SOC for reference
        self._last_sample_time = None
        self._last_voltage = None
        self._last_current = None

        # Charge state tracking
        self._is_charging = False
        self._charge_state_changed_time = None
        self._voltage_settled = False

        # Notification tracking (don't repeat warnings)
        self._warnings_sent = set()
        self._last_warning_time = 0

        # Session tracking for capacity learning
        self._session_start_time = time.time()
        self._session_start_soc = None
        self._session_discharge_mah = 0.0

        # CSV logging
        self._csv_file = None
        self._csv_writer = None
        self._init_csv_logging()

        # Load learned data
        self._learned = self._load_learned_data()

        # Initialize coulomb SOC from learned data if available
        if self._learned.get("last_soc") is not None:
            self._coulomb_soc = self._learned["last_soc"]

    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CSV_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _init_csv_logging(self):
        """Initialize CSV logging for the current session."""
        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            csv_path = CSV_LOG_DIR / f"battery_{date_str}.csv"
            file_exists = csv_path.exists()

            self._csv_file = open(csv_path, "a", newline="")
            self._csv_writer = csv.writer(self._csv_file)

            if not file_exists:
                self._csv_writer.writerow(
                    [
                        "timestamp",
                        "voltage",
                        "current_ma",
                        "power_mw",
                        "voltage_soc",
                        "coulomb_soc",
                        "hybrid_soc",
                        "charging",
                        "capacity_mah",
                    ]
                )
                self._csv_file.flush()
        except Exception as e:
            print(f"CSV logging init error: {e}")
            self._csv_writer = None

    def _log_csv(self, voltage, current, power, v_soc, c_soc, h_soc, charging):
        """Log a sample to CSV."""
        if self._csv_writer:
            try:
                self._csv_writer.writerow(
                    [
                        datetime.now().isoformat(),
                        f"{voltage:.3f}",
                        f"{current:.1f}",
                        f"{power:.1f}",
                        f"{v_soc:.1f}",
                        f"{c_soc:.1f}" if c_soc is not None else "",
                        f"{h_soc:.1f}",
                        "1" if charging else "0",
                        f"{self._learned['effective_capacity_mah']:.0f}",
                    ]
                )
                self._csv_file.flush()
            except Exception:
                pass

    def _load_learned_data(self):
        """Load learned capacity and patterns from disk."""
        default = {
            "effective_capacity_mah": NOMINAL_CAPACITY_MAH,
            "cycle_count": 0,
            "total_discharge_mah": 0,
            "avg_power_mw": 9000,
            "typical_draw_ma": 850,
            "last_full_charge_time": None,
            "capacity_samples": [],
            "last_soc": None,
            "last_soc_time": None,
        }
        try:
            if LEARNED_FILE.exists():
                with open(LEARNED_FILE, "r") as f:
                    data = json.load(f)
                    for key in default:
                        if key not in data:
                            data[key] = default[key]
                    return data
        except Exception:
            pass
        return default

    def _save_learned_data(self):
        """Save learned data to disk."""
        try:
            if self._coulomb_soc is not None:
                self._learned["last_soc"] = self._coulomb_soc
                self._learned["last_soc_time"] = time.time()

            with open(LEARNED_FILE, "w") as f:
                json.dump(self._learned, f, indent=2)
        except Exception:
            pass

    def _send_notification(self, title, message, urgency="normal"):
        """Send a notification via notify-send (works with mako, dunst, etc.)."""
        try:
            cmd = ["notify-send", "-u", urgency, title, message]
            subprocess.run(cmd, timeout=5, capture_output=True)
        except Exception:
            pass

    def _check_warnings(self, percent, charging):
        """Check if we need to send low battery warnings."""
        if charging:
            self._warnings_sent.clear()
            return

        now = time.time()
        if now - self._last_warning_time < 60:
            return

        for threshold in WARN_THRESHOLDS:
            if percent <= threshold and threshold not in self._warnings_sent:
                self._warnings_sent.add(threshold)
                self._last_warning_time = now

                if threshold <= CRITICAL_THRESHOLD:
                    self._send_notification(
                        "CRITICAL BATTERY",
                        f"Battery at {percent:.0f}%! Shutdown imminent.",
                        urgency="critical",
                    )
                elif threshold <= 10:
                    self._send_notification(
                        "Low Battery",
                        f"Battery at {percent:.0f}%. Please connect charger.",
                        urgency="critical",
                    )
                else:
                    self._send_notification(
                        "Battery Warning",
                        f"Battery at {percent:.0f}%.",
                        urgency="normal",
                    )
                break

    def record_sample(self, voltage: float, current_ma: float, power_mw: float) -> float:
        """
        Record a battery sample and update hybrid SOC.

        Args:
            voltage: Battery voltage in volts
            current_ma: Current in milliamps (positive = charging)
            power_mw: Power in milliwatts

        Returns:
            Current hybrid SOC percentage (0-100)
        """
        with self._lock:
            now = time.time()

            # Determine charge state
            was_charging = self._is_charging
            self._is_charging = current_ma > CHARGE_CURRENT_THRESHOLD

            # Track charge state changes for voltage settling
            if was_charging != self._is_charging:
                self._charge_state_changed_time = now
                self._voltage_settled = False
            elif self._charge_state_changed_time:
                if now - self._charge_state_changed_time > CHARGE_VOLTAGE_SETTLED_TIME:
                    self._voltage_settled = True

            # Calculate voltage-based SOC
            self._voltage_soc = voltage_to_percent(voltage)

            # Track current and power for averaging
            self._recent_current.append(abs(current_ma))
            self._recent_power.append(power_mw)

            # Update average power
            if self._recent_power:
                self._learned["avg_power_mw"] = sum(self._recent_power) / len(self._recent_power)

            # === HYBRID SOC CALCULATION ===

            # Initialize coulomb SOC if needed
            if self._coulomb_soc is None:
                self._coulomb_soc = self._voltage_soc
                self._session_start_soc = self._coulomb_soc

            # Coulomb counting: integrate current over time
            if self._last_sample_time is not None:
                dt_hours = (now - self._last_sample_time) / 3600.0
                capacity = self._learned["effective_capacity_mah"]

                if self._is_charging:
                    charge_mah = abs(current_ma) * dt_hours
                    delta_soc = (charge_mah / capacity) * 100.0
                    self._coulomb_soc = min(100.0, self._coulomb_soc + delta_soc)
                else:
                    discharge_mah = abs(current_ma) * dt_hours
                    delta_soc = (discharge_mah / capacity) * 100.0
                    self._coulomb_soc = max(0.0, self._coulomb_soc - delta_soc)

                    self._session_discharge_mah += discharge_mah
                    self._learned["total_discharge_mah"] += discharge_mah

            # === VOLTAGE CALIBRATION POINTS ===

            # Calibrate at full charge
            if (
                voltage >= 12.5
                and abs(current_ma) < 100
                and self._voltage_settled
                and not self._is_charging
            ):
                if self._coulomb_soc < 95:
                    self._on_full_charge()
                self._coulomb_soc = min(100.0, self._voltage_soc)

            # Calibrate at empty
            if voltage <= CRITICAL_VOLTAGE and not self._is_charging:
                self._coulomb_soc = max(0.0, self._voltage_soc)

            # Gradual drift correction
            if self._voltage_settled and not self._is_charging:
                blend_factor = 0.01
                self._coulomb_soc = (
                    self._coulomb_soc * (1 - blend_factor) + self._voltage_soc * blend_factor
                )

            # Clamp SOC based on voltage reality
            if self._is_charging or not self._voltage_settled:
                if voltage < 12.4:
                    self._coulomb_soc = min(self._coulomb_soc, 90.0)
                if voltage < 12.0:
                    self._coulomb_soc = min(self._coulomb_soc, 80.0)

            # Update tracking
            self._last_sample_time = now
            self._last_voltage = voltage
            self._last_current = current_ma

            hybrid_soc = max(0.0, min(100.0, self._coulomb_soc))

            # Check for low battery warnings
            self._check_warnings(hybrid_soc, self._is_charging)

            # Log to CSV
            self._log_csv(
                voltage,
                current_ma,
                power_mw,
                self._voltage_soc,
                self._coulomb_soc,
                hybrid_soc,
                self._is_charging,
            )

            # Periodically save
            if int(now) % 30 == 0:
                self._save_learned_data()

            return hybrid_soc

    def _on_full_charge(self):
        """Called when battery reaches full charge - learn from this cycle."""
        if self._session_discharge_mah > 500:
            if self._session_start_soc and self._session_start_soc > 20:
                soc_used = self._session_start_soc
                observed_capacity = self._session_discharge_mah / (soc_used / 100.0)

                if 1000 < observed_capacity < 5000:
                    self._learned["capacity_samples"].append(observed_capacity)
                    self._learned["capacity_samples"] = self._learned["capacity_samples"][-10:]

                    if self._learned["capacity_samples"]:
                        weights = [
                            1 + i * 0.2 for i in range(len(self._learned["capacity_samples"]))
                        ]
                        weighted_sum = sum(
                            c * w for c, w in zip(self._learned["capacity_samples"], weights)
                        )
                        self._learned["effective_capacity_mah"] = weighted_sum / sum(weights)

            self._learned["cycle_count"] += 1
            self._learned["last_full_charge_time"] = time.time()
            self._save_learned_data()

        self._session_discharge_mah = 0.0
        self._session_start_soc = 100.0

    def get_hybrid_soc(self) -> float:
        """Get the current hybrid SOC."""
        with self._lock:
            if self._coulomb_soc is not None:
                return max(0.0, min(100.0, self._coulomb_soc))
            return self._voltage_soc or 0.0

    def get_time_remaining(self, percent: float, current_ma: float):
        """
        Estimate time remaining based on current draw and learned capacity.

        Returns:
            Tuple of (hours, minutes) or None if cannot estimate
        """
        with self._lock:
            if self._is_charging:
                return None

            if self._recent_current and len(self._recent_current) >= 3:
                avg_current = sum(self._recent_current) / len(self._recent_current)
            else:
                avg_current = abs(current_ma)

            if avg_current < 30:
                return None

            effective_capacity = self._learned["effective_capacity_mah"]
            remaining_mah = (percent / 100.0) * effective_capacity
            hours_remaining = remaining_mah / avg_current

            if hours_remaining < 0 or hours_remaining > 50:
                return None

            hours = int(hours_remaining)
            minutes = int((hours_remaining - hours) * 60)

            return (hours, minutes)

    def get_time_to_full(self, percent: float, current_ma: float):
        """
        Estimate time to full charge.

        Returns:
            Tuple of (hours, minutes) or None if not charging
        """
        with self._lock:
            if not self._is_charging:
                return None

            if self._recent_current and len(self._recent_current) >= 3:
                avg_current = sum(self._recent_current) / len(self._recent_current)
            else:
                avg_current = abs(current_ma)

            if avg_current < 30:
                return None

            effective_capacity = self._learned["effective_capacity_mah"]
            needed_mah = ((100.0 - percent) / 100.0) * effective_capacity
            hours_to_full = needed_mah / avg_current

            if hours_to_full < 0 or hours_to_full > 50:
                return None

            hours = int(hours_to_full)
            minutes = int((hours_to_full - hours) * 60)

            return (hours, minutes)

    def format_time_remaining(self, percent: float, current_ma: float) -> str:
        """Get formatted string for time remaining/to full."""
        if self._is_charging:
            result = self.get_time_to_full(percent, current_ma)
            if result:
                h, m = result
                if h > 0:
                    return f"{h}h {m}m to full"
                return f"{m}m to full"
            return "Charging..."
        else:
            result = self.get_time_remaining(percent, abs(current_ma))
            if result:
                h, m = result
                if h > 0:
                    return f"{h}h {m}m remaining"
                return f"{m}m remaining"
            return ""

    def get_stats(self) -> dict:
        """Get learned statistics."""
        with self._lock:
            return {
                "effective_capacity_mah": self._learned["effective_capacity_mah"],
                "cycle_count": self._learned["cycle_count"],
                "avg_power_mw": self._learned["avg_power_mw"],
                "nominal_capacity_mah": NOMINAL_CAPACITY_MAH,
                "voltage_soc": self._voltage_soc,
                "coulomb_soc": self._coulomb_soc,
            }

    def is_charging(self) -> bool:
        """Return current charging state."""
        return self._is_charging

    def get_voltage_soc(self) -> float:
        """Get voltage-based SOC for comparison."""
        return self._voltage_soc

    def close(self):
        """Clean up resources."""
        self._save_learned_data()
        if self._csv_file:
            try:
                self._csv_file.close()
            except Exception:
                pass


# Singleton instances
_battery_learning = None
_battery_learning_lock = Lock()


def get_battery_learning() -> BatteryLearning:
    """Get the singleton BatteryLearning instance."""
    global _battery_learning
    with _battery_learning_lock:
        if _battery_learning is None:
            _battery_learning = BatteryLearning()
        return _battery_learning


def get_hybrid_soc(voltage: float, current: float, power: float) -> float:
    """
    Get hybrid SOC using coulomb counting + voltage calibration.

    This is the recommended function for getting battery percentage.

    Args:
        voltage: Battery voltage in volts
        current: Current in milliamps (positive = charging)
        power: Power in milliwatts

    Returns:
        Battery percentage (0-100)
    """
    bl = get_battery_learning()
    return bl.record_sample(voltage, current, power)
