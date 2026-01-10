"""
Battery Percentage Overlay - Layer shell overlay showing battery %.
Toggle with keybinding. Uses hybrid SOC (coulomb counting + voltage calibration).
"""

import atexit
import os
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell, GLib

try:
    from ina219 import INA219
    HAS_INA219 = True
except ImportError:
    HAS_INA219 = False

from .learning import (
    get_battery_learning,
    get_hybrid_soc,
    SHUNT_OHMS,
    I2C_ADDRESS,
    I2C_BUS,
)

PID_FILE = "/tmp/battery_overlay.pid"
MARGIN_TOP = 10
MARGIN_RIGHT = 10


class BatteryOverlay(Gtk.Window):
    """Transparent overlay window showing battery percentage."""

    def __init__(self):
        super().__init__()

        self.ina = None
        if HAS_INA219:
            try:
                self.ina = INA219(SHUNT_OHMS, address=I2C_ADDRESS, busnum=I2C_BUS)
                self.ina.configure()
            except Exception as e:
                print(f"INA219 error: {e}", file=sys.stderr)

        self.learning = get_battery_learning()

        # Set up layer shell
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, MARGIN_TOP)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, MARGIN_RIGHT)
        GtkLayerShell.set_exclusive_zone(self, 0)

        # Transparent background
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Container for stacked labels
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.box.set_halign(Gtk.Align.END)
        self.add(self.box)

        # Main percentage label
        self.label = Gtk.Label()
        self.label.set_markup('<span font="14" weight="bold" foreground="#00FF00">--%</span>')
        self.label.set_halign(Gtk.Align.END)
        self.box.pack_start(self.label, False, False, 0)

        # Time remaining label
        self.time_label = Gtk.Label()
        self.time_label.set_markup('<span font="9" foreground="#888888"></span>')
        self.time_label.set_halign(Gtk.Align.END)
        self.box.pack_start(self.time_label, False, False, 0)

        self.update_battery()
        GLib.timeout_add_seconds(5, self.update_battery)
        self.show_all()

    def get_color(self, percent: float, charging: bool) -> str:
        """Get color based on battery level."""
        if charging:
            return "#00BFFF"
        elif percent >= 50:
            return "#00FF00"
        elif percent >= 20:
            return "#FFD700"
        else:
            return "#FF4444"

    def update_battery(self) -> bool:
        """Update the overlay with current battery status."""
        if not self.ina:
            self.label.set_markup(
                '<span font="14" weight="bold" foreground="#888888">N/A</span>'
            )
            self.time_label.set_markup("")
            return True

        try:
            voltage = self.ina.voltage()
            current = self.ina.current()
            power = self.ina.power()

            percent = get_hybrid_soc(voltage, current, power)
            charging = self.learning.is_charging()
            color = self.get_color(percent, charging)

            charge_icon = " +" if charging else ""
            self.label.set_markup(
                f'<span font="14" weight="bold" foreground="{color}">'
                f"{percent:.0f}%{charge_icon}</span>"
            )

            time_str = self.learning.format_time_remaining(percent, current)
            if time_str:
                time_color = "#00BFFF" if charging else "#AAAAAA"
                self.time_label.set_markup(
                    f'<span font="9" foreground="{time_color}">{time_str}</span>'
                )
            else:
                self.time_label.set_markup("")

        except Exception:
            self.label.set_markup(
                '<span font="14" weight="bold" foreground="#FF4444">ERR</span>'
            )
            self.time_label.set_markup("")

        return True


def is_running():
    """Check if another instance is running."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, ProcessLookupError, PermissionError):
            os.remove(PID_FILE)
    return None


def write_pid():
    """Write current PID to file."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup(*args):
    """Clean up on exit."""
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    try:
        get_battery_learning().close()
    except Exception:
        pass
    Gtk.main_quit()


def main():
    """Entry point for the overlay (toggles on/off)."""
    other_pid = is_running()

    if other_pid:
        try:
            os.kill(other_pid, signal.SIGTERM)
            print("Battery overlay closed")
        except Exception:
            pass
        return

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    write_pid()

    win = BatteryOverlay()
    win.connect("destroy", Gtk.main_quit)

    atexit.register(cleanup)
    Gtk.main()


if __name__ == "__main__":
    main()
