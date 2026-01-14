# Cyberboy Battery

Battery monitoring suite for Raspberry Pi with INA219 current/voltage sensor. Designed for the **Waveshare UPS Module 3S** and other DIY UPS builds using 3S Li-ion battery packs.

## Safety Warning

**WORKING WITH LITHIUM-ION BATTERIES IS DANGEROUS.**

Li-ion batteries can cause fire, explosion, burns, and property damage if mishandled, improperly charged, short-circuited, or damaged. Before building any battery-powered project:

- Understand the risks of lithium-ion batteries
- Use proper battery management systems (BMS)
- Never exceed voltage/current ratings
- Use appropriate fuses and protection circuits
- Never leave charging batteries unattended
- Have a fire extinguisher rated for electrical/lithium fires nearby

**THE AUTHOR ASSUMES NO RESPONSIBILITY FOR ANY DAMAGE, INJURY, FIRE, EXPLOSION, OR OTHER HARM RESULTING FROM THE USE OF THIS SOFTWARE OR ANY ASSOCIATED HARDWARE. USE AT YOUR OWN RISK.**

This software provides battery monitoring only. It does not replace proper hardware protection circuits.

## Features

- **Hybrid SOC Estimation**: Combines coulomb counting with voltage calibration for accurate state-of-charge readings
- **System Tray Indicator**: Shows battery percentage, time remaining, and detailed stats
- **Screen Overlay**: Toggleable on-screen battery percentage display
- **Safe Shutdown Daemon**: Automatically shuts down at critical battery levels
- **Low Battery Notifications**: Warns at 20%, 10%, and 5% via desktop notifications
- **Capacity Learning**: Learns your battery's actual capacity over charge cycles
- **CSV Logging**: Records battery data for analysis and debugging

## Hardware Requirements

- Raspberry Pi (tested on Pi 5)
- **Waveshare UPS Module 3S** (recommended) or compatible INA219-based UPS
- 3x 18650 Li-ion batteries (3S configuration, 9.0V-12.6V)

### Waveshare UPS Module 3S

This software is optimized for the [Waveshare UPS Module 3S](https://www.waveshare.com/wiki/UPS_Module_3S):

| Parameter | Value |
|-----------|-------|
| I2C Address | 0x41 |
| I2C Bus | 1 |
| Battery Config | 3S (9V-12.6V) |
| Max Output | 5V 5A |

**Important:** This software reads the INA219 current register directly using the factory calibration. The `pi-ina219` library is **not required** and should not be used, as it reconfigures the INA219 and produces incorrect readings.

## Installation

### From Source

```bash
git clone https://github.com/yourusername/cyberboy-battery.git
cd cyberboy-battery
pip install -e .
```

### Dependencies

```bash
# System packages (Debian/Raspberry Pi OS)
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    gir1.2-ayatanaappindicator3-0.1 gir1.2-gtk-layer-shell-0.1

# Python packages
pip install smbus2
```

Note: The `pi-ina219` library is **not required**. This software reads INA219 registers directly to preserve the Waveshare factory calibration.

## Usage

### System Tray Indicator

```bash
cyberboy-battery-tray
```

Or add to your window manager's autostart:
```bash
# ~/.config/labwc/autostart
sleep 2 && python3 -m cyberboy_battery.tray &
```

### Screen Overlay (Toggle)

```bash
cyberboy-battery-overlay
```

Bind to a key in your window manager config (e.g., `Super+b`).

### Safe Shutdown Daemon

```bash
cyberboy-battery-shutdown
```

Add to autostart to run at boot:
```bash
# ~/.config/labwc/autostart
python3 -m cyberboy_battery.shutdown &
```

### Battery Status (for scripts/conky)

```bash
cyberboy-battery-status
```

Output format:
```
> 75%
  3h 45m remaining
```

## Configuration

Edit `src/cyberboy_battery/learning.py` to customize:

```python
# Battery configuration
NOMINAL_CAPACITY_MAH = 3400  # Your battery capacity (mAh)
I2C_ADDRESS = 0x41           # Your INA219 address
I2C_BUS = 1                  # Your I2C bus

# Voltage thresholds (for 3S Li-ion)
VOLT_MIN = 9.0               # Empty voltage
VOLT_MAX = 12.6              # Full voltage
CRITICAL_VOLTAGE = 9.6       # Shutdown threshold

# INA219 calibration (Waveshare UPS 3S default)
INA219_CURRENT_LSB_MA = 0.1  # Current register LSB in mA
```

## Data Storage

All data is stored in `~/.local/share/cyberboy-battery/`:

- `learned_data.json` - Learned capacity and SOC state
- `logs/battery_YYYY-MM-DD.csv` - Daily CSV logs

## How Hybrid SOC Works

Traditional voltage-based SOC has issues:
- Voltage sags under load
- Voltage jumps when charger connects/disconnects
- Flat discharge curve in the middle makes it inaccurate

This implementation uses a hybrid approach:
1. **Coulomb counting** tracks charge/discharge by integrating current over time
2. **Voltage calibration** resets the coulomb counter at known points (full charge, empty)
3. **Drift correction** slowly blends toward voltage SOC to prevent long-term drift
4. **Charge state awareness** doesn't trust voltage readings during/after charging until settled

## Troubleshooting

### "Battery drops from 100% to 60% instantly after unplugging"

This was a known issue that has been fixed. The software now:
- Waits 5 minutes after unplugging before blending toward voltage SOC (grace period)
- Uses gentler drift correction (0.2% per sample instead of 1%)
- Applies load compensation to voltage readings for full-charge calibration

### INA219 Not Found

Check your I2C connection:
```bash
i2cdetect -y 1
```

Your INA219 should appear at the configured address (default 0x41).

### Low Current/Power Readings (showing ~70mA instead of ~500mA)

If you see unrealistically low current readings, you may be using the `pi-ina219` library which reconfigures the INA219 with incorrect calibration. This software reads registers directly - ensure you're using the latest version and not importing from `ina219`.

### Other UPS Modules

If using a different INA219-based UPS module, you may need to adjust `INA219_CURRENT_LSB_MA` in `learning.py` to match your module's calibration. Check your module's documentation or experiment with values until current readings match expected consumption (~500-1000mA for Pi 5 with display).

## License

CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike)

See LICENSE file for full terms.
