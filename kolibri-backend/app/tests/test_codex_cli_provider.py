from __future__ import annotations

import asyncio
import json
import os
import stat
import textwrap
from pathlib import Path

import pytest

from app import codex_cli_provider
from app.codex_cli_provider import (
    CodexCLICancelled,
    CodexCLIError,
    CodexCLIInvalidOutput,
    CodexCLIProvider,
    CodexCLISettings,
    CodexCLITimeout,
    _normalise_messages,
    _resolve_binary,
    _safe_environment,
)


def _fake_codex(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "codex-fake"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, signal, sys, time\n"
        "if '--version' in sys.argv:\n"
        "    print('codex-cli 9.9.9')\n"
        "    raise SystemExit(0)\n"
        "if len(sys.argv) >= 3 and sys.argv[1:3] == ['login', 'status']:\n"
        "    print('Logged in')\n"
        "    raise SystemExit(0)\n"
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _settings(binary: Path, tmp_path: Path, **overrides) -> CodexCLISettings:
    values = {
        "enabled": True,
        "binary": str(binary),
        "cwd": tmp_path,
        "model": "",
        "max_concurrency": 2,
        # The full shared-runner suite can add brief subprocess startup
        # jitter. Dedicated timeout tests override this with 150 ms.
        "queue_timeout_seconds": 3.0,
        "attempt_timeout_seconds": 5.0,
        "terminate_grace_seconds": 0.1,
        "health_timeout_seconds": 3.0,
        "web_search": "disabled",
    }
    values.update(overrides)
    return CodexCLISettings(**values)


def _collect(provider: CodexCLIProvider, prompt: str, *, run_id: str = "run-test"):
    async def collect():
        return [
            event
            async for event in provider.stream(
                [{"role": "user", "content": prompt}],
                run_id=run_id,
            )
        ]

    return asyncio.run(collect())


def test_project_json_policy_uses_strict_project_prompt():
    prompt = _normalise_messages(
        [
            {"role": "system", "content": "Верни ровно один JSON-объект без Markdown."},
            {"role": "user", "content": "Создай минимальный рабочий site P7."},
        ],
        policy={"output_contract": "kolibri.project.v1"},
    )

    assert "Единственный допустимый финальный ответ: один JSON-объект UTF-8." in prompt
    assert "Контракт проекта:" in prompt
    assert "Контекст диалога:" not in prompt
    assert "Верни ровно один JSON-объект без Markdown." in prompt
    assert prompt.rstrip().endswith("Верни только JSON по контракту выше. Никакого текста вне JSON.")


def test_success_uses_stdin_fixed_argv_and_sanitized_agent_message(tmp_path):
    capture = tmp_path / "capture.json"
    binary = _fake_codex(
        tmp_path,
        f"""
        prompt = sys.stdin.read()
        with open({str(capture)!r}, 'w', encoding='utf-8') as handle:
            json.dump({{'argv': sys.argv, 'stdin': prompt}}, handle)
        print(json.dumps({{'type':'thread.started','thread_id':'private-thread'}}))
        print(json.dumps({{'type':'turn.started'}}))
        print(json.dumps({{'type':'item.completed','item':{{'id':'a','type':'agent_message','text':'Готово sk-proj-THISISASECRETVALUE'}}}}))
        print(json.dumps({{'type':'turn.completed','usage':{{'input_tokens':1}}}}))
        """,
    )
    provider = CodexCLIProvider(_settings(binary, tmp_path))

    events = _collect(provider, "привет; touch SHOULD_NOT_EXIST")
    data = json.loads(capture.read_text(encoding="utf-8"))
    argv = data["argv"]
    assert data["stdin"].endswith("привет; touch SHOULD_NOT_EXIST\n")
    assert "привет; touch SHOULD_NOT_EXIST" not in argv
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()
    assert ["--ephemeral", "--sandbox", "read-only"] == argv[argv.index("--ephemeral"):argv.index("--ephemeral") + 3]
    assert "--skip-git-repo-check" in argv
    assert "--ignore-user-config" in argv
    content = "".join(str(event.get("content") or "") for event in events)
    assert content == "Готово [REDACTED]"
    assert "private-thread" not in json.dumps(events)


def test_streams_only_safe_agent_deltas_and_tool_lifecycle(tmp_path, capsys):
    binary = _fake_codex(
        tmp_path,
        """
        _ = sys.stdin.read()
        print(json.dumps({'type':'thread.started','thread_id':'thread-secret'}), flush=True)
        print(json.dumps({'type':'item.started','item':{'id':'cmd','type':'command_execution','command':'cat /secret','status':'in_progress'}}), flush=True)
        print(json.dumps({'type':'item.completed','item':{'id':'r','type':'reasoning','text':'PRIVATE CHAIN'}}), flush=True)
        print(json.dumps({'type':'item.updated','item':{'id':'a','type':'agent_message','text':'При'}}), flush=True)
        print(json.dumps({'type':'item.completed','item':{'id':'a','type':'agent_message','text':'Привет'}}), flush=True)
        print(json.dumps({'type':'item.completed','item':{'id':'cmd','type':'command_execution','command':'cat /secret','aggregated_output':'SECRET'}}), flush=True)
        print(json.dumps({'type':'turn.completed'}), flush=True)
        print('RAW-STDERR-SECRET', file=sys.stderr, flush=True)
        """,
    )
    provider = CodexCLIProvider(_settings(binary, tmp_path))

    events = _collect(provider, "Ответь")

    assert [event["content"] for event in events if event.get("content")] == ["При", "вет"]
    tools = [event["tool_event"] for event in events if event.get("tool_event")]
    assert [(tool["type"], tool["tool"]) for tool in tools] == [
        ("tool.started", "codex.readonly_command"),
        ("tool.completed", "codex.readonly_command"),
    ]
    serialized = json.dumps(events, ensure_ascii=False)
    assert "PRIVATE CHAIN" not in serialized
    assert "cat /secret" not in serialized
    assert "RAW-STDERR-SECRET" not in serialized
    captured = capsys.readouterr()
    assert "RAW-STDERR-SECRET" not in captured.out + captured.err


def test_recoverable_top_level_error_does_not_discard_completed_text(tmp_path):
    binary = _fake_codex(
        tmp_path,
        """
        _ = sys.stdin.read()
        print(json.dumps({'type':'error','message':'under-development feature warning'}), flush=True)
        print(json.dumps({'type':'item.completed','item':{'id':'a','type':'agent_message','text':'Проверенный ответ'}}), flush=True)
        print(json.dumps({'type':'turn.completed'}), flush=True)
        """,
    )
    provider = CodexCLIProvider(_settings(binary, tmp_path))

    events = _collect(provider, "Ответь")

    assert "".join(str(event.get("content") or "") for event in events) == "Проверенный ответ"


def test_text_without_completed_turn_is_rejected(tmp_path):
    binary = _fake_codex(
        tmp_path,
        """
        _ = sys.stdin.read()
        print(json.dumps({'type':'item.completed','item':{'id':'a','type':'agent_message','text':'Частичный ответ'}}), flush=True)
        """,
    )
    provider = CodexCLIProvider(_settings(binary, tmp_path))

    with pytest.raises(CodexCLIInvalidOutput) as error:
        _collect(provider, "Ответь")

    assert str(error.value) == "codex_cli_incomplete_turn"


def test_non_json_stdout_is_rejected_not_rendered(tmp_path):
    binary = _fake_codex(
        tmp_path,
        """
        _ = sys.stdin.read()
        print('not-json')
        """,
    )
    provider = CodexCLIProvider(_settings(binary, tmp_path))

    with pytest.raises(CodexCLIInvalidOutput) as error:
        _collect(provider, "Ответь")
    assert str(error.value) == "codex_cli_invalid_jsonl"


def test_failure_never_exposes_stderr(tmp_path):
    binary = _fake_codex(
        tmp_path,
        """
        _ = sys.stdin.read()
        print('TOKEN=super-secret', file=sys.stderr, flush=True)
        raise SystemExit(7)
        """,
    )
    provider = CodexCLIProvider(_settings(binary, tmp_path))

    with pytest.raises(CodexCLIError) as error:
        _collect(provider, "Ответь")
    assert str(error.value) == "codex_cli_failed"
    assert "super-secret" not in str(error.value)


def test_timeout_terminates_attempt_process(tmp_path):
    marker = tmp_path / "finished"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        print(json.dumps({{'type':'thread.started','thread_id':'x'}}), flush=True)
        time.sleep(2)
        open({str(marker)!r}, 'w').write('late')
        """,
    )
    provider = CodexCLIProvider(
        _settings(binary, tmp_path, attempt_timeout_seconds=0.15)
    )

    with pytest.raises(CodexCLITimeout):
        _collect(provider, "Ответь")
    assert not marker.exists()


def test_explicit_cancel_terminates_process_group(tmp_path):
    marker = tmp_path / "finished"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        print(json.dumps({{'type':'thread.started','thread_id':'x'}}), flush=True)
        time.sleep(3)
        open({str(marker)!r}, 'w').write('late')
        """,
    )
    provider = CodexCLIProvider(
        _settings(binary, tmp_path, attempt_timeout_seconds=5.0)
    )

    async def scenario():
        started = asyncio.Event()

        async def consume():
            async for event in provider.stream(
                [{"role": "user", "content": "Ответь"}], run_id="cancel-me"
            ):
                if event.get("response_meta"):
                    started.set()

        task = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), timeout=3)
        assert await provider.cancel("cancel-me") is True
        with pytest.raises(CodexCLICancelled):
            await task

    asyncio.run(scenario())
    assert not marker.exists()


def test_health_probe_checks_version_and_login_without_returning_login_text(tmp_path):
    binary = _fake_codex(tmp_path, "raise SystemExit(2)\n")
    provider = CodexCLIProvider(_settings(binary, tmp_path))

    result = asyncio.run(provider.probe_health())

    assert result["status"] == "live"
    assert result["entitlement"] == "granted"
    assert result["tests"]["version"] == {"ok": True}
    assert result["tests"]["login"] == {"ok": True}
    assert result["secret_exposed"] is False
    assert "Logged in" not in json.dumps(result)


def test_model_and_prompt_metacharacters_never_use_a_shell(tmp_path):
    capture = tmp_path / "capture.json"
    sentinel = tmp_path / "owned"
    model = f"model;touch {sentinel}"
    binary = _fake_codex(
        tmp_path,
        f"""
        prompt = sys.stdin.read()
        with open({str(capture)!r}, 'w', encoding='utf-8') as handle:
            json.dump({{'argv': sys.argv, 'stdin': prompt}}, handle)
        print(json.dumps({{'type':'item.completed','item':{{'id':'a','type':'agent_message','text':'OK'}}}}))
        print(json.dumps({{'type':'turn.completed'}}))
        """,
    )
    provider = CodexCLIProvider(_settings(binary, tmp_path, model=model))

    _collect(provider, f"$(touch {sentinel})")

    argv = json.loads(capture.read_text(encoding="utf-8"))["argv"]
    assert argv[argv.index("--model") + 1] == model
    assert not sentinel.exists()


def test_home_defaults_and_legacy_model_oss_aliases(monkeypatch, tmp_path):
    for name in (
        "CODEX_CLI_BINARY",
        "KOLIBRI_CODEX_CLI_BINARY",
        "CODEX_CLI_MODEL",
        "CODEX_CLI_OSS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(codex_cli_provider.sys, "platform", "darwin")
    monkeypatch.setenv("CODEX_CLI_CWD", str(tmp_path))
    monkeypatch.setenv("KOLIBRI_CODEX_MODEL", "account-model")
    monkeypatch.setenv("KOLIBRI_CODEX_OSS", "true")

    settings = CodexCLISettings.from_env()
    argv = CodexCLIProvider(settings)._argv(settings.binary)

    assert settings.binary == "codex"
    assert settings.model == "account-model"
    assert settings.oss is True
    assert "--oss" in argv
    assert argv[argv.index("--model") + 1] == "account-model"
    assert argv[argv.index("--enable") + 1] == "respect_system_proxy"


def test_production_pool_can_be_sized_to_one_hundred(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_CLI_CWD", str(tmp_path))
    monkeypatch.setenv("CODEX_CLI_MAX_CONCURRENCY", "100")

    settings = CodexCLISettings.from_env()

    assert settings.max_concurrency == 100


def test_linux_home_default_prefers_existing_wrapper(monkeypatch, tmp_path):
    wrapper_dir = tmp_path / "usr-local-bin"
    wrapper_dir.mkdir()
    wrapper = _fake_codex(wrapper_dir, "raise SystemExit(2)\n")
    path_dir = tmp_path / "path-bin"
    path_dir.mkdir()
    _fake_codex(path_dir, "raise SystemExit(2)\n").rename(path_dir / "codex")
    monkeypatch.delenv("CODEX_CLI_BINARY", raising=False)
    monkeypatch.delenv("KOLIBRI_CODEX_CLI_BINARY", raising=False)
    monkeypatch.setattr(codex_cli_provider.sys, "platform", "linux")
    monkeypatch.setattr(codex_cli_provider, "_LINUX_HOME_CODEX_WRAPPER", wrapper)
    monkeypatch.setenv("CODEX_CLI_CWD", str(tmp_path))
    monkeypatch.setenv("PATH", f"{path_dir}{os.pathsep}/usr/bin:/bin")

    settings = CodexCLISettings.from_env()
    direct_default = CodexCLISettings(cwd=tmp_path)
    resolved = _resolve_binary(settings, _safe_environment(settings))

    assert settings.binary == str(wrapper)
    assert direct_default.binary == str(wrapper)
    assert resolved == str(wrapper.resolve())
    assert CodexCLIProvider(settings).configuration_snapshot()["configured"] is True


def test_explicit_codex_cli_binary_wins_over_linux_home_wrapper(monkeypatch, tmp_path):
    wrapper_dir = tmp_path / "usr-local-bin"
    wrapper_dir.mkdir()
    wrapper = _fake_codex(wrapper_dir, "raise SystemExit(2)\n")
    explicit_dir = tmp_path / "explicit-bin"
    explicit_dir.mkdir()
    explicit = _fake_codex(explicit_dir, "raise SystemExit(2)\n")
    monkeypatch.setattr(codex_cli_provider.sys, "platform", "linux")
    monkeypatch.setattr(codex_cli_provider, "_LINUX_HOME_CODEX_WRAPPER", wrapper)
    monkeypatch.setenv("CODEX_CLI_BINARY", str(explicit))
    monkeypatch.setenv("KOLIBRI_CODEX_CLI_BINARY", str(wrapper))
    monkeypatch.setenv("CODEX_CLI_CWD", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    settings = CodexCLISettings.from_env()
    resolved = _resolve_binary(settings, _safe_environment(settings))

    assert settings.binary == str(explicit)
    assert resolved == str(explicit.resolve())


def test_explicit_codex_name_resolves_path_even_when_linux_wrapper_exists(monkeypatch, tmp_path):
    wrapper_dir = tmp_path / "usr-local-bin"
    wrapper_dir.mkdir()
    wrapper = _fake_codex(wrapper_dir, "raise SystemExit(2)\n")
    path_dir = tmp_path / "path-bin"
    path_dir.mkdir()
    raw_codex = _fake_codex(path_dir, "raise SystemExit(2)\n").rename(path_dir / "codex")
    monkeypatch.setattr(codex_cli_provider.sys, "platform", "linux")
    monkeypatch.setattr(codex_cli_provider, "_LINUX_HOME_CODEX_WRAPPER", wrapper)
    monkeypatch.setenv("CODEX_CLI_BINARY", "codex")
    monkeypatch.setenv("CODEX_CLI_CWD", str(tmp_path))
    monkeypatch.setenv("PATH", f"{path_dir}{os.pathsep}/usr/bin:/bin")

    settings = CodexCLISettings.from_env()
    resolved = _resolve_binary(settings, _safe_environment(settings))

    assert settings.binary == "codex"
    assert resolved == str(raw_codex.resolve())


def test_non_linux_default_resolves_portably_from_process_path(monkeypatch, tmp_path):
    path_dir = tmp_path / "path-bin"
    path_dir.mkdir()
    binary = _fake_codex(path_dir, "raise SystemExit(2)\n")
    portable_binary = binary.rename(path_dir / "codex")
    wrapper_dir = tmp_path / "usr-local-bin"
    wrapper_dir.mkdir()
    wrapper = _fake_codex(wrapper_dir, "raise SystemExit(2)\n")
    monkeypatch.delenv("CODEX_CLI_BINARY", raising=False)
    monkeypatch.delenv("KOLIBRI_CODEX_CLI_BINARY", raising=False)
    monkeypatch.setattr(codex_cli_provider.sys, "platform", "darwin")
    monkeypatch.setattr(codex_cli_provider, "_LINUX_HOME_CODEX_WRAPPER", wrapper)
    monkeypatch.setenv("CODEX_CLI_CWD", str(tmp_path))
    monkeypatch.setenv("PATH", f"{path_dir}{os.pathsep}/usr/bin:/bin")

    settings = CodexCLISettings.from_env()
    resolved = _resolve_binary(settings, _safe_environment(settings))

    assert settings.binary == "codex"
    assert resolved == str(portable_binary.resolve())
    assert CodexCLIProvider(settings).configuration_snapshot()["configured"] is True


def test_explicit_absolute_binary_remains_fail_closed(monkeypatch, tmp_path):
    missing = tmp_path / "missing-codex"
    monkeypatch.setenv("CODEX_CLI_BINARY", str(missing))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}/usr/bin:/bin")
    _fake_codex(tmp_path, "raise SystemExit(2)\n")

    settings = CodexCLISettings.from_env()

    assert _resolve_binary(settings, _safe_environment(settings)) is None
    assert CodexCLIProvider(settings).configuration_snapshot()["configured"] is False


def test_proxy_precedence_and_process_proxy_inheritance(monkeypatch, tmp_path):
    for name in (
        "CODEX_CLI_HTTP_PROXY",
        "CODEX_CLI_HTTPS_PROXY",
        "CODEX_CLI_ALL_PROXY",
        "CODEX_CLI_NO_PROXY",
        "KOLIBRI_CODEX_CLI_HTTP_PROXY",
        "KOLIBRI_CODEX_CLI_HTTPS_PROXY",
        "KOLIBRI_CODEX_CLI_ALL_PROXY",
        "KOLIBRI_CODEX_CLI_NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CODEX_CLI_CWD", str(tmp_path))
    monkeypatch.setenv("HTTP_PROXY", "http://process-http:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://process-https:8443")
    monkeypatch.setenv("ALL_PROXY", "socks5://process-all:1080")
    monkeypatch.setenv("NO_PROXY", "localhost,10.99.0.0/24")

    inherited = CodexCLISettings.from_env()
    inherited_env = _safe_environment(inherited)
    assert inherited.http_proxy == "http://process-http:8080"
    assert inherited.https_proxy == "http://process-https:8443"
    assert inherited_env["HTTP_PROXY"] == inherited_env["http_proxy"]
    assert inherited_env["HTTPS_PROXY"] == inherited_env["https_proxy"]
    assert inherited_env["ALL_PROXY"] == inherited_env["all_proxy"]
    assert inherited_env["NO_PROXY"] == inherited_env["no_proxy"]

    monkeypatch.setenv("KOLIBRI_CODEX_CLI_HTTP_PROXY", "http://amnezia-home:11081")
    monkeypatch.setenv("CODEX_CLI_HTTPS_PROXY", "http://explicit:11081")
    explicit = CodexCLISettings.from_env()
    assert explicit.http_proxy == "http://amnezia-home:11081"
    assert explicit.https_proxy == "http://explicit:11081"
    assert explicit.all_proxy == ""
