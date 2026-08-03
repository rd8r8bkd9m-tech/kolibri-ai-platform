"""Lightweight MCP (Model Context Protocol) stdio server base.

Implements JSON-RPC 2.0 over stdin/stdout for MCP tool servers.
Compatible with Codex CLI and MiMo Code MCP client support.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class MCPTool:
    """Definition of an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class MCPServer:
    """Simple MCP stdio server."""

    name: str
    version: str = "1.0.0"
    tools: list[MCPTool] = field(default_factory=list)
    _handlers: dict[str, Callable[..., Any]] = field(default_factory=dict)

    def tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
    ) -> Callable[..., Any]:
        """Decorator to register a tool handler."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools.append(
                MCPTool(
                    name=name,
                    description=description,
                    input_schema=input_schema,
                )
            )
            self._handlers[name] = fn
            return fn

        return decorator

    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a single JSON-RPC request."""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version,
                    },
                },
            }

        if method == "notifications/initialized":
            # Notification, no response needed
            return {}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": t.input_schema,
                        }
                        for t in self.tools
                    ]
                },
            }

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            handler = self._handlers.get(tool_name)
            if handler is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}",
                    },
                }
            try:
                result = handler(**arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    json.dumps(result, ensure_ascii=False)
                                    if isinstance(result, dict | list)
                                    else str(result)
                                ),
                            }
                        ]
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error: {exc}",
                            }
                        ],
                        "isError": True,
                    },
                }

        if method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {},
            }

        # Unknown method
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Unknown method: {method}",
            },
        }

    def run(self) -> None:
        """Run the server, reading JSON-RPC from stdin and writing to stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue

            response = self._handle_request(request)

            # Notifications (no id) don't get responses
            if response:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
