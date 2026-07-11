#!/usr/bin/env python3
"""Loopback-only HTTPS CONNECT proxy with policy-routed outbound sockets.

Kolibri uses this adapter to send only approved provider traffic through an
existing Amnezia/WireGuard policy-routing table.  It never changes the host's
default route and it deliberately rejects plain HTTP forwarding and private
destinations.
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
    "openai.com",
    "oaistatic.com",
    "oaiusercontent.com",
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


def open_marked_connection(host: str, port: int, config: ProxyConfig) -> socket.socket:
    if not host_allowed(host, config.allowed_suffixes):
        raise ProxyPolicyError("destination_not_allowed")
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
    args = parser.parse_args(argv)
    config = ProxyConfig(
        mark=args.mark,
        allowed_suffixes=tuple(args.allowed_suffixes or DEFAULT_ALLOWED_SUFFIXES),
    )
    with ConnectProxyServer((args.listen, args.port), config) as server:
        server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
