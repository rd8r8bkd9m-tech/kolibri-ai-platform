import importlib.util
import socket
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "ops" / "marked_connect_proxy.py"
    spec = importlib.util.spec_from_file_location("marked_connect_proxy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_connect_parser_accepts_only_tls_connect():
    proxy = load_module()
    assert proxy.parse_connect_target(b"CONNECT chatgpt.com:443 HTTP/1.1") == (
        "chatgpt.com",
        443,
    )
    with pytest.raises(proxy.ProxyPolicyError, match="connect_only"):
        proxy.parse_connect_target(b"GET https://chatgpt.com/ HTTP/1.1")
    with pytest.raises(proxy.ProxyPolicyError, match="tls_port_only"):
        proxy.parse_connect_target(b"CONNECT chatgpt.com:80 HTTP/1.1")


def test_domain_allowlist_is_suffix_safe():
    proxy = load_module()
    assert proxy.host_allowed("chatgpt.com")
    assert proxy.host_allowed("api.openai.com")
    assert proxy.host_allowed("platform.xiaomimimo.com")
    assert proxy.host_allowed("mimo.xiaomi.com")
    assert not proxy.host_allowed("chatgpt.com.attacker.example")
    assert not proxy.host_allowed("notopenai.com")


def test_private_and_special_destinations_are_rejected():
    proxy = load_module()
    for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "224.0.0.1"):
        assert proxy.public_ip(address) is False
    assert proxy.public_ip("1.1.1.1") is True


def test_listener_must_be_loopback():
    proxy = load_module()
    with pytest.raises(proxy.ProxyPolicyError, match="loopback_listener_required"):
        proxy.ConnectProxyServer(("0.0.0.0", 0), proxy.ProxyConfig(mark=0x66))


def test_mark_is_applied_before_connect(monkeypatch):
    proxy = load_module()
    calls = []

    class FakeSocket:
        def settimeout(self, value):
            calls.append(("timeout", value))

        def setsockopt(self, level, option, value):
            calls.append(("setsockopt", level, option, value))

        def connect(self, address):
            calls.append(("connect", address))

        def setblocking(self, value):
            calls.append(("blocking", value))

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(proxy, "resolve_public", lambda *_args: [(socket.AF_INET, socket.SOCK_STREAM, 6, ("1.1.1.1", 443))])
    monkeypatch.setattr(proxy.socket, "socket", lambda *_args: FakeSocket())
    outbound = proxy.open_marked_connection("chatgpt.com", 443, proxy.ProxyConfig(mark=0x66))

    assert isinstance(outbound, FakeSocket)
    assert ("setsockopt", socket.SOL_SOCKET, proxy.SO_MARK, 0x66) in calls
    assert calls.index(("setsockopt", socket.SOL_SOCKET, proxy.SO_MARK, 0x66)) < calls.index(("connect", ("1.1.1.1", 443)))


def test_zero_mark_uses_remote_hosts_default_route(monkeypatch):
    proxy = load_module()
    calls = []

    class FakeSocket:
        def settimeout(self, value):
            calls.append(("timeout", value))

        def setsockopt(self, *values):
            calls.append(("setsockopt", *values))

        def connect(self, address):
            calls.append(("connect", address))

        def setblocking(self, value):
            calls.append(("blocking", value))

        def close(self):
            pass

    monkeypatch.setattr(proxy, "resolve_public", lambda *_args: [(socket.AF_INET, socket.SOCK_STREAM, 6, ("1.1.1.1", 443))])
    monkeypatch.setattr(proxy.socket, "socket", lambda *_args: FakeSocket())
    proxy.open_marked_connection("chatgpt.com", 443, proxy.ProxyConfig(mark=0))

    assert not any(call[0] == "setsockopt" for call in calls)
    assert ("connect", ("1.1.1.1", 443)) in calls


def test_provider_egress_unit_is_loopback_only_and_does_not_capture_telegram():
    unit = (
        ROOT / "ops" / "systemd" / "kolibri-provider-egress-proxy.service"
    ).read_text(encoding="utf-8")
    telegram_unit = (
        ROOT / "ops" / "systemd" / "kolibri-telegram-gateway.service"
    ).read_text(encoding="utf-8")

    assert "--listen 127.0.0.1" in unit
    assert "--port 18080" in unit
    assert "--allow-suffix api.telegram.org" not in unit
    assert "--allow-suffix openai.com" in unit
    assert "--check-config" in unit
    assert "ExecStart=/usr/bin/python3 -B" in unit
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in unit
    assert "py_compile" not in unit
    assert "provider_egress_preflight.py --interface wg-awg-out --mark 0x66 --table 1066" in unit
    assert "--fallback-socks-host 127.0.0.1" in unit
    assert "Requires=kolibri-provider-egress-tunnel.service" not in unit
    assert "Wants=network-online.target kolibri-provider-egress-tunnel.service" in unit
    assert "AmbientCapabilities=CAP_NET_RAW" in unit
    assert "CapabilityBoundingSet=CAP_NET_RAW" in unit
    assert "IPAddressDeny=any" not in unit
    assert "HTTPS_PROXY=" not in telegram_unit


def test_allowlisted_connect_uses_mark_primary_then_local_socks_fallback(monkeypatch):
    proxy = load_module()
    sent = []

    class Socks:
        def __init__(self):
            self.buffer = bytearray(
                b"\x05\x00"
                b"\x05\x00\x00\x01"
                b"\x7f\x00\x00\x01"
                b"\x01\xbb"
            )
            self.blocking = True
            self.closed = False

        def sendall(self, payload):
            sent.append(payload)

        def recv(self, length):
            payload = bytes(self.buffer[:length])
            del self.buffer[:length]
            return payload

        def setblocking(self, value):
            self.blocking = value

        def close(self):
            self.closed = True

    connection = Socks()
    primary = []
    monkeypatch.setattr(proxy.socket, "create_connection", lambda *args, **kwargs: connection)
    monkeypatch.setattr(
        proxy,
        "open_primary_connection",
        lambda *args: primary.append(args) or (_ for _ in ()).throw(OSError("blocked")),
    )
    config = proxy.ProxyConfig(
        mark=0x66,
        fallback_socks_host="127.0.0.1",
        fallback_socks_port=19090,
    )

    result = proxy.open_marked_connection("api.openai.com", 443, config)

    assert result is connection
    assert primary
    assert sent[0] == b"\x05\x01\x00"
    assert b"api.openai.com" in sent[1]
    assert connection.blocking is False


def test_socks_upstream_must_be_loopback():
    proxy = load_module()
    with pytest.raises(proxy.ProxyPolicyError, match="must_be_loopback"):
        proxy.ProxyConfig(
            mark=0x66,
            fallback_socks_host="203.0.113.9",
            fallback_socks_port=1080,
        )


def test_successful_marked_primary_never_touches_socks(monkeypatch):
    proxy = load_module()
    primary = object()
    monkeypatch.setattr(proxy, "open_primary_connection", lambda *_args: primary)
    monkeypatch.setattr(
        proxy,
        "open_socks_connection",
        lambda *_args: pytest.fail("fallback must not run after marked success"),
    )

    result = proxy.open_marked_connection(
        "api.openai.com",
        443,
        proxy.ProxyConfig(
            mark=0x66,
            fallback_socks_host="127.0.0.1",
            fallback_socks_port=19090,
        ),
    )

    assert result is primary
