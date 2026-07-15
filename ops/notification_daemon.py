#!/usr/bin/env python3
"""Notification Daemon — alert system for fleet events."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

CONTROL_PLANE = "http://192.168.88.210:9101"

CHANNELS = ["telegram", "email", "webhook", "ui"]


@dataclass
class Notification:
    notification_id: str
    title: str
    body: str
    channel: str
    severity: str  # "info" | "warning" | "critical"
    created_at: str
    sent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


_notifications: list[Notification] = []
_subscriptions: dict[str, list[str]] = {}


def _request(method: str, url: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def send_notification(title: str, body: str, channel: str = "ui", severity: str = "info") -> Notification:
    notif = Notification(
        notification_id=f"NOTIF-{int(datetime.now(timezone.utc).timestamp())}",
        title=title,
        body=body,
        channel=channel,
        severity=severity,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _notifications.append(notif)
    if len(_notifications) > 500:
        _notifications.pop(0)
    return notif


def subscribe(event: str, channel: str) -> None:
    if event not in _subscriptions:
        _subscriptions[event] = []
    if channel not in _subscriptions[event]:
        _subscriptions[event].append(channel)


def get_history(limit: int = 50) -> list[Notification]:
    return _notifications[-limit:]


def notify_event(event: str, data: dict) -> list[Notification]:
    channels = _subscriptions.get(event, ["ui"])
    notifs = []
    for ch in channels:
        notif = send_notification(
            title=event,
            body=json.dumps(data),
            channel=ch,
            severity="warning" if "error" in event.lower() else "info",
        )
        notifs.append(notif)
    return notifs


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: notification_daemon.py <send|history|subscribe> [args]")
        sys.exit(1)

    action = sys.argv[1]
    if action == "send" and len(sys.argv) > 3:
        notif = send_notification(sys.argv[2], sys.argv[3])
        print(f"  Sent: {notif.to_dict()}")
    elif action == "history":
        for n in get_history():
            print(f"  [{n.severity}] {n.title}: {n.body[:80]}")
    elif action == "subscribe" and len(sys.argv) > 3:
        subscribe(sys.argv[2], sys.argv[3])
        print(f"  Subscribed to {sys.argv[2]} on {sys.argv[3]}")
