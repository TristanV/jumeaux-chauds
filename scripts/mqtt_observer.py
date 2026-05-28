#!/usr/bin/env python3
"""
MQTT Observer — Console viewer for Jumeaux Chauds MQTT messages.

Lightweight alternative to MQTT Explorer for terminal monitoring.
Displays real-time message payload with timestamps and topic filtering.

Usage:
    python scripts/mqtt_observer.py --host localhost --port 1883 --topic "dt/#"
    python scripts/mqtt_observer.py --host mosquitto --topics "dt/+/+/telemetry" "dt/+/summary"
"""

import asyncio
import json
import sys
from argparse import ArgumentParser
from datetime import datetime
from typing import Optional

try:
    import aiomqtt
except ImportError:
    print("Error: aiomqtt not installed. Run: pip install aiomqtt")
    sys.exit(1)


class MQTTObserver:
    """MQTT message observer with JSON pretty-printing and filtering."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        topics: list[str] | None = None,
        verbose: bool = False,
        max_payload_lines: int = 20,
    ):
        self.host = host
        self.port = port
        self.topics = topics or ["dt/#"]
        self.verbose = verbose
        self.max_payload_lines = max_payload_lines
        self.message_count = 0

    async def run(self) -> None:
        """Subscribe to MQTT topics and display messages."""
        try:
            async with aiomqtt.Client(self.host, self.port) as client:
                print(f"✓ Connected to {self.host}:{self.port}")
                print(f"✓ Subscribing to: {', '.join(self.topics)}")
                print("-" * 80)

                for topic in self.topics:
                    await client.subscribe(topic)

                async for message in client.messages:
                    await self._display_message(message)

        except aiomqtt.MqttError as e:
            print(f"✗ MQTT Connection Error: {e}", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print(f"\n✓ Stopped. {self.message_count} messages received.")
            sys.exit(0)

    async def _display_message(self, message: aiomqtt.Message) -> None:
        """Format and display a single MQTT message."""
        self.message_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Topic and QoS
        print(f"\n[{timestamp}] Topic: {message.topic} (QoS {message.qos})")

        # Payload
        payload_str = message.payload.decode("utf-8", errors="replace")

        try:
            # Try to parse as JSON and pretty-print
            payload_json = json.loads(payload_str)
            payload_lines = json.dumps(payload_json, indent=2).split("\n")

            if len(payload_lines) > self.max_payload_lines:
                # Truncate very large payloads
                for line in payload_lines[: self.max_payload_lines]:
                    print(f"  {line}")
                print(f"  ... ({len(payload_lines) - self.max_payload_lines} more lines)")
            else:
                for line in payload_lines:
                    print(f"  {line}")

        except json.JSONDecodeError:
            # Not JSON, display as-is
            if len(payload_str) > 500:
                print(f"  {payload_str[:500]}...")
            else:
                print(f"  {payload_str}")

        # Extra info in verbose mode
        if self.verbose:
            print(f"  [size: {len(message.payload)} bytes]")


def main() -> None:
    """CLI entry point."""
    parser = ArgumentParser(
        description="MQTT Observer — Real-time MQTT message viewer"
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="MQTT broker host (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=1883,
        help="MQTT broker port (default: 1883)",
    )
    parser.add_argument(
        "--topics",
        nargs="+",
        default=["dt/#"],
        help="MQTT topics to subscribe to (default: dt/#)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (show payload size, etc)",
    )

    args = parser.parse_args()

    observer = MQTTObserver(
        host=args.host,
        port=args.port,
        topics=args.topics,
        verbose=args.verbose,
    )

    try:
        asyncio.run(observer.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
