# escpaws

A daemon that bridges ESC/POS to a GB01/GB02-style Bluetooth thermal printer. It watches a named pipe for `GS v 0` raster bitmap commands and forwards the image data to the printer over BLE using the [catprinter](https://github.com/rbaron/catprinter) protocol.

Intended for use with the [omgmog/mgba](https://github.com/omgmog/mgba/tree/devterm-thermal-printer) fork, which adds a configurable thermal printer output to mGBA's Game Boy Printer emulation.

## Requirements

- Linux with BlueZ (tested on Ubuntu 22.04)
- Python 3.10+
- A paired GB01 or GB02 Bluetooth printer

## Pairing the printer

```bash
bluetoothctl
> power on
> scan on
# wait for the printer to appear, note its address
> pair E0:C0:08:D2:34:1D
> trust E0:C0:08:D2:34:1D
> scan off
> exit
```

## Installation

Clone the repo and run the install script, passing the printer's Bluetooth address:

```bash
git clone https://github.com/omgmog/escpaws.git
cd escpaws
./install.sh E0:C0:08:D2:34:1D
```

The script installs the Python dependencies, writes a systemd service file, and starts the service. If no address is given it will prompt and list paired devices.

## Manual usage

Without the service, run directly:

```bash
python3 escpaws.py E0:C0:08:D2:34:1D
```

Options (all can be set via environment variable or CLI flag):

| Flag | Env var | Default | Description |
|------|---------|---------|-------------|
| `--fifo PATH` | `ESCPAWS_FIFO` | `/tmp/ESCPAWS_IN` | Named pipe to watch |
| `--energy VALUE` | `ESCPAWS_ENERGY` | `0x8000` | Print darkness; useful range 16000–50000 |
| `--retry-delay N` | `ESCPAWS_RETRY_DELAY` | `5` | Seconds between connection retries |
| `--max-retries N` | `ESCPAWS_MAX_RETRIES` | `6` | Attempts before giving up (~30s at defaults) |

## Using with mGBA

In the mGBA fork's Thermal Printer settings, set the pipe path to `/tmp/ESCPAWS_IN` (or whatever `--fifo` is set to). The printer needs to be on before a print job arrives. If it isn't, the bridge retries and sends a desktop notification via `notify-send` if available.

## Service management

```bash
systemctl status escpaws
systemctl restart escpaws
journalctl -u escpaws -f
```
