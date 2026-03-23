#!/usr/bin/env python3
"""
Bridge: reads ESC/POS from a FIFO, extracts bitmap images, sends to a catprinter via BLE.

Listens on a named pipe for ESC/POS GS v 0 raster bitmap commands and forwards
the image data to a GB01/GB02-style Bluetooth thermal printer using the catprinter
protocol (https://github.com/rbaron/catprinter).
"""
import argparse
import asyncio
import os
import subprocess
import sys
import time
import numpy as np

from catprinter.cmds import cmds_print_img
from bleak import BleakClient, BleakError
from bleak.backends.bluezdbus.client import BleakClientBlueZDBus

TX_CHAR     = "0000ae01-0000-1000-8000-00805f9b34fb"
CHUNK_DELAY = 0.02


def notify(summary, body="", urgency="normal"):
    try:
        subprocess.run(["notify-send", "-u", urgency, summary, body], check=False)
    except FileNotFoundError:
        pass


async def send_to_printer(data, address):
    async with BleakClient(address) as client:
        if isinstance(client, BleakClientBlueZDBus):
            await client._acquire_mtu()
        chunk_size = client.mtu_size - 3
        chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
        for chunk in chunks:
            await client.write_gatt_char(TX_CHAR, chunk)
            await asyncio.sleep(CHUNK_DELAY)


def send_with_retry(data, address, retry_delay, max_retries):
    for attempt in range(1, max_retries + 1):
        try:
            asyncio.run(send_to_printer(data, address))
            notify("Cat Printer", "Print complete.")
            return True
        except (BleakError, Exception) as e:
            if attempt == 1:
                notify("Cat Printer", "Printer not found - is it switched on?", urgency="critical")
                print(f"Connection failed: {e}", flush=True)
            if attempt < max_retries:
                print(f"Retrying in {retry_delay}s (attempt {attempt}/{max_retries})...", flush=True)
                time.sleep(retry_delay)
    print("Gave up after retries.", flush=True)
    notify("Cat Printer", "Print failed after retries.", urgency="critical")
    return False


def bitmap_to_rows(raw, width_bytes, height):
    """Unpack MSB-first ESC/POS bitmap bytes to a list of 0/1 pixel rows."""
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(height, width_bytes)
    unpacked = np.unpackbits(arr, axis=1, bitorder='big')
    return unpacked[:, :width_bytes * 8].tolist()


def read_byte(f):
    b = f.read(1)
    if not b:
        raise EOFError
    return b[0]


def parse_for_image(f):
    """Scan ESC/POS stream, return pixel rows when a GS v 0 image command arrives."""
    buf = []
    while True:
        b = read_byte(f)
        buf.append(b)

        # DC2 # n  (density setting) - consume
        if len(buf) >= 3 and buf[-3] == 0x12 and buf[-2] == 0x23:
            buf = []
            continue

        # ESC d n  (feed lines) - consume
        if len(buf) >= 3 and buf[-3] == 0x1b and buf[-2] == 0x64:
            buf = []
            continue

        # GS v 0   (raster bitmap): 1d 76 30 p wL wH hL hH [data...]
        if len(buf) >= 8 and buf[-8] == 0x1d and buf[-7] == 0x76 and buf[-6] == 0x30:
            wL, wH = buf[-4], buf[-3]
            hL, hH = buf[-2], buf[-1]
            width_bytes = wL + wH * 256
            height      = hL + hH * 256
            raw = f.read(width_bytes * height)
            buf = []
            if len(raw) < width_bytes * height:
                print(f"Short read ({len(raw)}/{width_bytes * height}), skipping", flush=True)
                continue
            return bitmap_to_rows(raw, width_bytes, height)


def main():
    parser = argparse.ArgumentParser(description="ESC/POS to catprinter BLE bridge")
    parser.add_argument("address", help="Bluetooth address of the printer (e.g. E0:C0:08:D2:34:1D)")
    parser.add_argument("--fifo",        default=os.environ.get("ESCPAWS_FIFO", "/tmp/ESCPAWS_IN"), help="Path to the named pipe to watch (default: /tmp/ESCPAWS_IN, or ESCPAWS_FIFO)")
    parser.add_argument("--energy",      type=lambda x: int(x, 0), default=int(os.environ.get("ESCPAWS_ENERGY", "0x8000"), 0), help="Print energy/darkness, useful range 16000-50000 (default: 0x8000, or ESCPAWS_ENERGY)")
    parser.add_argument("--retry-delay", type=int, default=int(os.environ.get("ESCPAWS_RETRY_DELAY", "5")),  help="Seconds between connection retries (default: 5, or ESCPAWS_RETRY_DELAY)")
    parser.add_argument("--max-retries", type=int, default=int(os.environ.get("ESCPAWS_MAX_RETRIES", "6")),  help="Max connection attempts before giving up (default: 6, or ESCPAWS_MAX_RETRIES)")
    args = parser.parse_args()

    if not os.path.exists(args.fifo):
        os.mkfifo(args.fifo)
        print(f"Created FIFO at {args.fifo}", flush=True)

    print(f"Watching {args.fifo}  →  {args.address}  (energy {args.energy:#06x})", flush=True)

    while True:
        try:
            with open(args.fifo, 'rb') as f:
                while True:
                    rows = parse_for_image(f)
                    if rows:
                        print(f"Image received: {len(rows[0])}x{len(rows)} px, printing...", flush=True)
                        send_with_retry(cmds_print_img(rows, energy=args.energy), args.address, args.retry_delay, args.max_retries)
        except EOFError:
            pass  # writer closed the pipe end, loop back and reopen
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
