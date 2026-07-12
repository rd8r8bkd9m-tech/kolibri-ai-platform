#!/usr/bin/env python3
"""Loopback-only, allowlisted HTTPS CONNECT proxy for provider traffic.

The primary route is an ``SO_MARK`` socket through Home's already-managed
AmneziaWG policy table.  A signed, dynamic SSH SOCKS tunnel may be configured
as a bounded fallback.  The proxy never changes the host's default route and
rejects plain HTTP forwarding, non-provider destinations, and non-loopback
SOCKS upstreams.
"""

from __future__ import annotations

import argparse
import ipaddress
import selectors
import socket
import socketserver
import threading
import time
from dataclasses import dataclass
from typing import Iterable


SO_MARK = getattr(socket, "SO_MARK", 36)
MAX_HEADER_BYTES = 64 * 1024
DEFAULT_ALLOWED_SUFFIXES = (
    "chatgpt.com",
    "mimo.xiaomi.com",
    "openai.com",
    "oaistatic.com",
    "oaiusercontent.com",
    "xiaomimimo.com",
)


class ProxyPolicyError(ValueError):
    pass


def normalize_host(value: str) -> str:
    host = value.strip().rstrip(".").lower()
    if not host or len(host) > 253 or any(char.isspace() for char in host):
        raise ProxyPolicyError("invalid_host")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ProxyPolicyError("invalid_host") from exc


def host_allowed(host: str, suffixes: Iterable[str] = DEFAULT_ALLOWED_SUFFIXES) -> bool:
    normalized = normalize_host(host)
    for raw_suffix in suffixes:
        suffix = normalize_host(raw_suffix)
        if normalized == suffix or normalized.endswith(f".{suffix}"):
            return True
    return False


def public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def parse_connect_target(request_line: bytes) -> tuple[str, int]:
    try:
        method, authority, version = request_line.decode("ascii").split()
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProxyPolicyError("invalid_request_line") from exc
    if method.upper() != "CONNECT" or not version.startswith("HTTP/1."):
        raise ProxyPolicyError("connect_only")
    host, separator, port_text = authority.rpartition(":")
    if not separator or not host:
        raise ProxyPolicyError("invalid_authority")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ProxyPolicyError("invalid_port") from exc
    if port != 443:
        raise ProxyPolicyError("tls_port_only")
    return normalize_host(host.strip("[]")), port


def resolve_public(host: str, port: int) -> list[tuple[int, int, int, tuple]]:
    resolved: list[tuple[int, int, int, tuple]] = []
    for family, socktype, proto, _canonname, sockaddr in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    ):
        ip_value = sockaddr[0]
        if public_ip(ip_value):
            resolved.append((family, socktype, proto, sockaddr))
    if not resolved:
        raise ProxyPolicyError("no_public_destination")
    return resolved


@dataclass(frozen=True)
class ProxyConfig:
    mark: int
    allowed_suffixes: tuple[str, ...] = DEFAULT_ALLOWED_SUFFIXES
    connect_timeout: float = 10.0
    idle_timeout: float = 120.0
    fallback_socks_host: str | None = None
    fallback_socks_port: int | None = None

    def __post_init__(self) -> None:
        if self.mark < 0 or self.mark > 0xFFFFFFFF:
            raise ProxyPolicyError("mark_invalid")
        if (self.fallback_socks_host is None) != (self.fallback_socks_port is None):
            raise ProxyPolicyError("fallback_socks_contract_invalid")
        if self.fallback_socks_host is not None:
            try:
                address = ipaddress.ip_address(self.fallback_socks_host)
            except ValueError as exc:
                raise ProxyPolicyError("fallback_socks_must_be_loopback") from exc
            if (
                not address.is_loopback
                or not 1 <= int(self.fallback_socks_port or 0) <= 65535
            ):
                raise ProxyPolicyError("fallback_socks_must_be_loopback")


def _recv_exact(connection: socket.socket, length: int) -> bytes:
    payload = bytearray()
    while len(payload) < length:
        chunk = connection.recv(length - len(payload))
        if not chunk:
            raise OSError("socks_upstream_closed")
        payload.extend(chunk)
    return bytes(payload)


def open_socks_connection(host: str, port: int, config: ProxyConfig) -> socket.socket:
    """Open one domain-bound SOCKS5 stream through the optional local fallback."""

    if config.fallback_socks_host is None or config.fallback_socks_port is None:
        raise ProxyPolicyError("fallback_socks_unconfigured")
    if not host_allowed(host, config.allowed_suffixes) or port != 443:
        raise ProxyPolicyError("destination_not_allowed")
    encoded_host = normalize_host(host).encode("ascii")
    if len(encoded_host) > 255:
        raise ProxyPolicyError("invalid_host")
    connection = socket.create_connection(
        (config.fallback_socks_host, config.fallback_socks_port),
        timeout=config.connect_timeout,
    )
    try:
        connection.sendall(b"\x05\x01\x00")
        if _recv_exact(connection, 2) != b"\x05\x00":
            raise OSError("socks_auth_method_rejected")
        connection.sendall(
            b"\x05\x01\x00\x03"
            + bytes((len(encoded_host),))
            + encoded_host
            + port.to_bytes(2, "big")
        )
        header = _recv_exact(connection, 4)
        if header[:2] != b"\x05\x00" or header[2] != 0:
            raise OSError("socks_connect_rejected")
        address_type = header[3]
        if address_type == 1:
            _recv_exact(connection, 4)
        elif address_type == 3:
            _recv_exact(connection, _recv_exact(connection, 1)[0])
        elif address_type == 4:
            _recv_exact(connection, 16)
        else:
            raise OSError("socks_reply_invalid")
        _recv_exact(connection, 2)
        connection.setblocking(False)
        return connection
    except Exception:
        connection.close()
        raise


def open_primary_connection(host: str, port: int, config: ProxyConfig) -> socket.socket:
    """Open through Home's direct/marked lane without consulting a fallback."""

    last_error: OSError | None = None
    for family, socktype, proto, sockaddr in resolve_public(host, port):
        outbound = socket.socket(family, socktype, proto)
        outbound.settimeout(config.connect_timeout)
        try:
            if config.mark:
                outbound.setsockopt(socket.SOL_SOCKET, SO_MARK, config.mark)
            outbound.connect(sockaddr)
            outbound.setblocking(False)
            return outbound
        except OSError as exc:
            last_error = exc
            outbound.close()
    raise OSError("marked_connect_failed") from last_error


def open_marked_connection(host: str, port: int, config: ProxyConfig) -> socket.socket:
    if not host_allowed(host, config.allowed_suffixes) or port != 443:
        raise ProxyPolicyError("destination_not_allowed")
    try:
        return open_primary_connection(host, port, config)
    except OSError:
        if config.fallback_socks_host is None:
            raise
        try:
            return open_socks_connection(host, port, config)
        except OSError as fallback_error:
            raise OSError("provider_egress_primary_and_fallback_failed") from fallback_error


def relay(left: socket.socket, right: socket.socket, idle_timeout: float) -> None:
    selector = selectors.DefaultSelector()
    for source, target in ((left, right), (right, left)):
        source.setblocking(False)
        selector.register(source, selectors.EVENT_READ, target)
    last_activity = time.monotonic()
    try:
        while time.monotonic() - last_activity < idle_timeout:
            events = selector.select(timeout=1.0)
            if not events:
                continue
            for key, _mask in events:
                source = key.fileobj
                target = key.data
                try:
                    data = source.recv(64 * 1024)
                except (BlockingIOError, InterruptedError):
                    continue
                if not data:
                    return
                target.sendall(data)
                last_activity = time.monotonic()
    finally:
        selector.close()


class ConnectHandler(socketserver.BaseRequestHandler):
    server: "ConnectProxyServer"

    def handle(self) -> None:
        self.request.settimeout(10.0)
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            buffer += chunk
            if len(buffer) > MAX_HEADER_BYTES:
                self.request.sendall(b"HTTP/1.1 431 Request Header Fields Too Large\r\n\r\n")
                return
        request_line = buffer.split(b"\r\n", 1)[0]
        try:
            host, port = parse_connect_target(request_line)
            outbound = open_marked_connection(host, port, self.server.config)
        except ProxyPolicyError:
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            return
        except OSError:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            return
        try:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            relay(self.request, outbound, self.server.config.idle_timeout)
        finally:
            outbound.close()


class ConnectProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], config: ProxyConfig):
        if not ipaddress.ip_address(address[0]).is_loopback:
            raise ProxyPolicyError("loopback_listener_required")
        self.config = config
        super().__init__(address, ConnectHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--mark", type=lambda value: int(value, 0), default=0x66)
    parser.add_argument("--allow-suffix", action="append", dest="allowed_suffixes")
    parser.add_argument("--fallback-socks-host")
    parser.add_argument("--fallback-socks-port", type=int)
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args(argv)
    config = ProxyConfig(
        mark=args.mark,
        allowed_suffixes=tuple(args.allowed_suffixes or DEFAULT_ALLOWED_SUFFIXES),
        fallback_socks_host=args.fallback_socks_host,
        fallback_socks_port=args.fallback_socks_port,
    )
    if args.check_config:
        return 0
    with ConnectProxyServer((args.listen, args.port), config) as server:
        server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
