"""
Simple hardware simulator - sends fake sensor readings to the backend over
the device websocket, so you can test the whole pipeline without real hardware.

Usage:
    python scripts/simulate_device.py --device-id dev-test-1 --secret <device_secret>

Secret Maps
    device_001 - hojRy9vSXkORQsQoMumBfO-X6aytYiGjHSu_hW46AxM

Requires the `websockets` package (already in requirements.txt).
"""
import argparse
import asyncio
import json
import random

import websockets


async def run(url: str, device_id: str, secret: str, interval: float, count: int):
    uri = f"{url}/ws/device/{device_id}?secret={secret}"
    async with websockets.connect(uri) as ws:
        print(f"Connected as device '{device_id}'")
        i = 0
        while count == 0 or i < count:
            reading = {
                "body_temperature": round(random.uniform(36.0, 37.5), 2),
                "heart_rate": round(random.uniform(60, 100), 1),
                # Occasionally simulate a desaturation event
                "spo2": round(random.uniform(85, 100) if random.random() > 0.05 else random.uniform(80, 89), 1),
                "heart_beat_height": round(random.uniform(0.2, 0.8), 3),
            }
            await ws.send(json.dumps(reading))
            response = await ws.recv()
            print("sent:", reading, "-> server:", response)
            i += 1
            await asyncio.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate a hardware device sending sensor data.")
    parser.add_argument("--url", default="ws://localhost:8000/api/v1", help="Base websocket URL of the API")
    parser.add_argument("--device-id", required=True, help="Registered device_id")
    parser.add_argument("--secret", required=True, help="device_secret returned at registration")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between samples")
    parser.add_argument("--count", type=int, default=0, help="Number of samples to send (0 = infinite)")
    args = parser.parse_args()

    asyncio.run(run(args.url, args.device_id, args.secret, args.interval, args.count))
