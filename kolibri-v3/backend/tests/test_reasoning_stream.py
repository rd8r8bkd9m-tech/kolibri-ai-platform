from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.direct_model_runtime import _custom_model_response


class _FakeStream:
    def __init__(self, chunks: list[dict]) -> None:
        self._chunks = chunks

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def iter_lines(self):
        for chunk in self._chunks:
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}"
        yield "data: [DONE]"


class _FakeResponse:
    def __init__(self, chunks: list[dict]) -> None:
        self._chunks = chunks

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    @property
    def status_code(self) -> int:
        return 200

    def iter_lines(self):
        for chunk in self._chunks:
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}"
        yield "data: [DONE]"

    def close(self) -> None:
        return None


class _FakeRuntime:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def stream(self, *_args: object, **_kwargs: object) -> _FakeResponse:
        return self._response


def test_custom_model_response_collects_reasoning_content(monkeypatch) -> None:
    settings = Settings.for_testing(database_url=Path("/tmp/reasoning-test.db"))
    fake_runtime = _FakeRuntime(
        _FakeResponse(
            [
                {
                    "choices": [
                        {
                            "delta": {
                                "role": "assistant",
                                "reasoning_content": "Сначала сложу 2 и 3:",
                                "content": "",
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "reasoning_content": " получается 5.",
                                "content": "Ответ: 5",
                            }
                        }
                    ]
                },
            ]
        )
    )
    monkeypatch.setattr(
        "app.direct_model_runtime.MimoClientRuntime",
        lambda **_kwargs: fake_runtime,
    )
    deltas: list[str] = []
    reasoning: list[str] = []

    turn = _custom_model_response(
        settings,
        api_key="test-key",
        base_url="https://example.invalid",
        api_model="deepseek-v4-flash",
        messages=[{"role": "user", "content": "2+3?"}],
        instructions="Отвечай кратко.",
        on_delta=deltas.append,
        on_reasoning=reasoning.append,
        output_schema=None,
    )

    assert turn.text == "Ответ: 5"
    assert turn.reasoning == "Сначала сложу 2 и 3: получается 5."
    assert deltas == ["Ответ: 5"]
    assert reasoning == [
        "Сначала сложу 2 и 3:",
        " получается 5.",
    ]
