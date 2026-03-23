#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="escpaws"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# --- Required commands ---
MISSING=()
for cmd in python3 git bluetoothctl sudo systemctl; do
    command -v "$cmd" &>/dev/null || MISSING+=("$cmd")
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Error: missing required commands: ${MISSING[*]}" >&2
    echo "On Debian/Ubuntu: sudo apt install python3 git bluez" >&2
    exit 1
fi

# --- Argument / prompt for printer address ---
PRINTER_ADDRESS="${1:-}"
if [ -z "$PRINTER_ADDRESS" ]; then
    echo "Paired Bluetooth devices:"
    bluetoothctl devices 2>/dev/null || true
    echo
    read -rp "Enter printer Bluetooth address (e.g. E0:C0:08:D2:34:1D): " PRINTER_ADDRESS
fi

if [[ ! "$PRINTER_ADDRESS" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
    echo "Error: '$PRINTER_ADDRESS' doesn't look like a Bluetooth address." >&2
    exit 1
fi

# --- Python virtualenv + dependencies ---
echo "Creating virtualenv..."
python3 -m venv "${SCRIPT_DIR}/.venv"
echo "Installing Python dependencies..."
"${SCRIPT_DIR}/.venv/bin/pip" install bleak numpy

echo "Cloning catprinter..."
if [ -d "${SCRIPT_DIR}/catprinter" ]; then
    git -C "${SCRIPT_DIR}/catprinter" pull --quiet
else
    git clone --quiet https://github.com/rbaron/catprinter.git "${SCRIPT_DIR}/catprinter"
fi

# --- Systemd service ---
CURRENT_USER="$(whoami)"
CURRENT_UID="$(id -u)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python3"

echo "Installing systemd service as user '${CURRENT_USER}' (uid ${CURRENT_UID})..."

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=escpaws: ESC/POS to catprinter BLE bridge
After=bluetooth.target

[Service]
User=${CURRENT_USER}
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${CURRENT_UID}/bus
Environment=PYTHONPATH=${SCRIPT_DIR}/catprinter
Environment=ESCPAWS_FIFO=/tmp/ESCPAWS_IN
Environment=ESCPAWS_ENERGY=0x8000
Environment=ESCPAWS_RETRY_DELAY=5
Environment=ESCPAWS_MAX_RETRIES=6
ExecStart=${PYTHON} ${SCRIPT_DIR}/escpaws.py ${PRINTER_ADDRESS}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo
echo "Done. Service status:"
systemctl status "$SERVICE_NAME" --no-pager
