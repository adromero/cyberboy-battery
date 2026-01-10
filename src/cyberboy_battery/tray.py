"""
UPS Battery Tray Indicator for Raspberry Pi.
Uses hybrid SOC (coulomb counting + voltage calibration).
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, AyatanaAppIndicator3, GLib

from ina219 import INA219, DeviceRangeError

from .learning import (
    get_battery_learning,
    get_hybrid_soc,
    SHUNT_OHMS,
    I2C_ADDRESS,
    I2C_BUS,
    NOMINAL_CAPACITY_MAH,
    LOW_VOLTAGE_WARN,
    CRITICAL_VOLTAGE,
)


class UPSIndicator:
    """System tray indicator showing battery status."""

    def __init__(self):
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "ups-battery", "battery-full", AyatanaAppIndicator3.IndicatorCategory.HARDWARE
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        self.learning = get_battery_learning()
        self._build_menu()
        self._init_ina219()

        GLib.timeout_add_seconds(5, self.update)
        self.update()

    def _build_menu(self):
        """Build the indicator menu."""
        self.menu = Gtk.Menu()

        self.percent_item = Gtk.MenuItem(label="Battery: --%")
        self.percent_item.set_sensitive(False)
        self.menu.append(self.percent_item)

        self.time_item = Gtk.MenuItem(label="Time: --")
        self.time_item.set_sensitive(False)
        self.menu.append(self.time_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.voltage_item = Gtk.MenuItem(label="Voltage: --")
        self.voltage_item.set_sensitive(False)
        self.menu.append(self.voltage_item)

        self.current_item = Gtk.MenuItem(label="Current: --")
        self.current_item.set_sensitive(False)
        self.menu.append(self.current_item)

        self.power_item = Gtk.MenuItem(label="Power: --")
        self.power_item.set_sensitive(False)
        self.menu.append(self.power_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.vsoc_item = Gtk.MenuItem(label="Voltage SOC: --")
        self.vsoc_item.set_sensitive(False)
        self.menu.append(self.vsoc_item)

        self.csoc_item = Gtk.MenuItem(label="Coulomb SOC: --")
        self.csoc_item.set_sensitive(False)
        self.menu.append(self.csoc_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        self.capacity_item = Gtk.MenuItem(label="Capacity: --")
        self.capacity_item.set_sensitive(False)
        self.menu.append(self.capacity_item)

        self.cycles_item = Gtk.MenuItem(label="Cycles: --")
        self.cycles_item.set_sensitive(False)
        self.menu.append(self.cycles_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def _init_ina219(self):
        """Initialize the INA219 sensor."""
        try:
            self.ina = INA219(SHUNT_OHMS, address=I2C_ADDRESS, busnum=I2C_BUS)
            self.ina.configure()
            self.ina_ok = True
        except Exception as e:
            print(f"INA219 init error: {e}")
            self.ina_ok = False

    def get_battery_icon(self, percent: float, charging: bool) -> str:
        """Get appropriate battery icon name."""
        if percent >= 80:
            level = "full"
        elif percent >= 50:
            level = "good"
        elif percent >= 20:
            level = "low"
        else:
            level = "empty"

        if charging:
            return f"battery-{level}-charging"
        return f"battery-{level}"

    def update(self) -> bool:
        """Update the indicator with current battery status."""
        if not self.ina_ok:
            self.indicator.set_label("ERR", "")
            return True

        try:
            voltage = self.ina.voltage()
            current = self.ina.current()
            power = self.ina.power()

            percent = get_hybrid_soc(voltage, current, power)
            charging = self.learning.is_charging()

            # Update icon
            if voltage <= CRITICAL_VOLTAGE and not charging:
                icon = "battery-empty"
            elif voltage <= LOW_VOLTAGE_WARN and not charging:
                icon = "battery-caution" if percent > 10 else "battery-empty"
            else:
                icon = self.get_battery_icon(percent, charging)

            self.indicator.set_icon_full(icon, f"Battery {percent:.0f}%")
            self.indicator.set_label(f"{percent:.0f}%", "")
            self.indicator.set_title(f"Battery {percent:.0f}%")

            # Update menu items
            self.percent_item.set_label(f"Battery: {percent:.0f}%")
            self.voltage_item.set_label(f"Voltage: {voltage:.2f} V")
            self.current_item.set_label(f"Current: {current:.1f} mA")
            self.power_item.set_label(f"Power: {power:.1f} mW")

            # Update SOC comparison
            stats = self.learning.get_stats()
            v_soc = stats.get("voltage_soc")
            c_soc = stats.get("coulomb_soc")
            if v_soc is not None:
                self.vsoc_item.set_label(f"Voltage SOC: {v_soc:.1f}%")
            if c_soc is not None:
                self.csoc_item.set_label(f"Coulomb SOC: {c_soc:.1f}%")

            # Update time remaining
            time_str = self.learning.format_time_remaining(percent, current)
            if time_str:
                self.time_item.set_label(f"Time: {time_str}")
            elif charging:
                self.time_item.set_label("Time: Charging...")
            else:
                self.time_item.set_label("Time: Calculating...")

            # Update learned stats
            self.capacity_item.set_label(
                f"Capacity: {stats['effective_capacity_mah']:.0f} mAh "
                f"(nom: {stats['nominal_capacity_mah']})"
            )
            self.cycles_item.set_label(f"Cycles tracked: {stats['cycle_count']}")

        except DeviceRangeError:
            self.indicator.set_label("OVR", "")
        except Exception as e:
            print(f"Update error: {e}")
            self.indicator.set_label("ERR", "")

        return True

    def quit(self, widget):
        """Clean up and quit."""
        self.learning.close()
        Gtk.main_quit()


def main():
    """Entry point for the tray indicator."""
    indicator = UPSIndicator()
    Gtk.main()


if __name__ == "__main__":
    main()
