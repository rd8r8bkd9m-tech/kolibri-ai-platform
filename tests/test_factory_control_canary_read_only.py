from __future__ import annotations

from ops import factory_control as factory


def test_canary_rejects_post_before_body_or_in_memory_mutation(monkeypatch):
    monkeypatch.setattr(factory, "CANARY_READ_ONLY", True)
    monkeypatch.setattr(
        factory,
        "read_body",
        lambda _handler: (_ for _ in ()).throw(AssertionError("body must not be read")),
    )
    responses = []
    monkeypatch.setattr(
        factory,
        "response",
        lambda _handler, status, payload: responses.append((status, payload)),
    )
    handler = object.__new__(factory.Handler)
    handler.path = "/v1/truth/claim"

    handler.do_POST()

    assert responses == [(405, {
        "error": "factory_canary_read_only",
        "path": "/v1/truth/claim",
    })]


def test_canary_redis_guard_blocks_write_before_socket_connection(monkeypatch):
    monkeypatch.setattr(factory, "CANARY_READ_ONLY", True)
    client = factory.Redis(host="127.0.0.1", port=1)
    monkeypatch.setattr(
        client,
        "_connect",
        lambda: (_ for _ in ()).throw(AssertionError("write must not connect")),
    )

    try:
        client.command("SET", "key", "value")
    except factory.RedisError as exc:
        assert str(exc) == "factory_canary_read_only_command_forbidden"
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError("canary Redis write was accepted")
