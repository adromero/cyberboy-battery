#!/usr/bin/env python3
"""
Battery Percentage Overlay - Layer shell overlay showing battery %.
Toggle with keybinding. Reads state from tray daemon via shared file.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell, Gdk, GLib, Pango
import atexit
import os
import signal
import sys
import json

# Shared state file written by tray daemon
BATTERY_STATE_FILE = "/tmp/cyberboy_battery_state.json"
PID_FILE = "/tmp/battery_overlay.pid"

# Overlay styling
MARGIN_TOP = 10
MARGIN_RIGHT = 10


class BatteryOverlay(Gtk.Window):
    """Transparent overlay window showing battery percentage."""

    def __init__(self):
        super().__init__()

        # Set up layer shell
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, MARGIN_TOP)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, MARGIN_RIGHT)
        GtkLayerShell.set_exclusive_zone(self, 0)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)

        # Transparent background
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.connect("draw", self.on_draw)

        # Container
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.box.set_halign(Gtk.Align.END)
        self.add(self.box)

        # Battery percentage label
        self.label = Gtk.Label()
        self.label.set_markup('<span font="18" weight="bold" foreground="#00ff00">--%</span>')
        self.label.set_halign(Gtk.Align.END)
        self.box.pack_start(self.label, False, False, 0)

        # Time remaining label (smaller)
        self.time_label = Gtk.Label()
        self.time_label.set_markup('<span font="9" foreground="#888888"></span>')
        self.time_label.set_halign(Gtk.Align.END)
        self.box.pack_start(self.time_label, False, False, 0)

        # Update immediately and every 5 seconds
        self.update()
        GLib.timeout_add_seconds(5, self.update)

        self.show_all()

    def on_draw(self, widget, cr):
        """Draw transparent background."""
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(1)  # CAIRO_OPERATOR_SOURCE
        cr.paint()
        return False

    def get_color(self, percent: float, charging: bool) -> str:
        """Get color based on battery level."""
        if charging:
            return "#00ffff"  # Cyan when charging
        elif percent > 50:
            return "#00ff00"  # Green
        elif percent > 20:
            return "#ffff00"  # Yellow
        else:
            return "#ff0000"  # Red

    def update(self):
        """Update display from shared state file."""
        try:
            with open(BATTERY_STATE_FILE, "r") as f:
                state = json.load(f)

            percent = state.get("percent", 0)
            charging = state.get("charging", False)
            time_str = state.get("time_str", "")

            color = self.get_color(percent, charging)
            charge_indicator = " ⚡" if charging else ""

            self.label.set_markup(
                f'<span font="18" weight="bold" foreground="{color}">'
                f'{percent:.0f}%{charge_indicator}</span>'
            )

            if time_str:
                time_color = "#00ffff" if charging else "#888888"
                self.time_label.set_markup(
                    f'<span font="9" foreground="{time_color}">{time_str}</span>'
                )
            else:
                self.time_label.set_markup("")

        except FileNotFoundError:
            self.label.set_markup(
                '<span font="18" weight="bold" foreground="#888888">--%</span>'
            )
            self.time_label.set_markup(
                '<span font="9" foreground="#666666">No battery daemon</span>'
            )
        except Exception:
            self.label.set_markup(
                '<span font="18" weight="bold" foreground="#ff0000">ERR</span>'
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
