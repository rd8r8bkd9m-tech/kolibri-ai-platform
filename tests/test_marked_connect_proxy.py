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
