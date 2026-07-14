from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import stat
import textwrap
import uuid
from pathlib import Path

import pytest

from app import image_artifacts
from app.codex_cli_image_provider import (
    CodexCLIImageCancelled,
    CodexCLIImageInvalidArtifact,
    CodexCLIImageProvider,
    CodexCLIImageSettings,
    CodexCLIImageTimeout,
)
from app.codex_cli_provider import CodexCLISettings


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _fake_codex(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "codex-image-fake"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import base64, json, os, signal, sys, time\n"
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _settings(binary: Path, tmp_path: Path, **overrides) -> CodexCLIImageSettings:
    cli = CodexCLISettings(
        enabled=True,
        binary=str(binary),
        cwd=tmp_path,
        model="",
        max_concurrency=2,
        queue_timeout_seconds=3.0,
        attempt_timeout_seconds=5.0,
        terminate_grace_seconds=0.1,
        health_timeout_seconds=3.0,
        web_search="disabled",
    )
    values = {
        "enabled": True,
        "cli": cli,
        "model": "",
        "max_concurrency": 2,
        "queue_timeout_seconds": 3.0,
        "attempt_timeout_seconds": 5.0,
        "terminate_grace_seconds": 0.1,
        "max_line_bytes": 1024 * 1024,
        "max_output_bytes": 4 * 1024 * 1024,
        "max_image_bytes": 1024 * 1024,
        "max_workspace_entries": 16,
        "temp_root": tmp_path,
    }
    values.update(overrides)
    return CodexCLIImageSettings(**values)


@pytest.fixture(autouse=True)
def _isolated_codex_home(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))


def test_success_uses_shell_free_image_tool_and_materializes_verified_artifact(
    tmp_path, monkeypatch
):
    capture = tmp_path / "capture.json"
    binary = _fake_codex(
        tmp_path,
        f"""
        prompt = sys.stdin.read()
        workspace = os.getcwd()
        generated = os.path.join(os.environ['CODEX_HOME'], 'generated_images', 'output.png')
        os.makedirs(os.path.dirname(generated), exist_ok=True)
        with open(generated, 'wb') as handle:
            handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        with open({str(capture)!r}, 'w', encoding='utf-8') as handle:
            json.dump({{'argv': sys.argv, 'stdin': prompt, 'cwd': workspace}}, handle)
        print(json.dumps({{'type':'thread.started','thread_id':'private-thread'}}), flush=True)
        print(json.dumps({{'type':'item.completed','item':{{'type':'reasoning','text':'PRIVATE'}}}}), flush=True)
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':generated}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )
    provider = CodexCLIImageProvider(_settings(binary, tmp_path))

    result = asyncio.run(provider.generate("сгенерируй цветы; touch OUTSIDE"))
    captured = json.loads(capture.read_text(encoding="utf-8"))

    assert result.data == _PNG_1X1
    assert result.mime_type == "image/png"
    assert (result.width, result.height) == (1, 1)
    assert result.sha256 == hashlib.sha256(_PNG_1X1).hexdigest()
    assert result.model == "codex-cli:account-default"
    assert captured["stdin"].splitlines()[0] == "$imagegen"
    assert "Вызови встроенный skill $imagegen" in captured["stdin"]
    assert "сгенерируй цветы; touch OUTSIDE" in captured["stdin"]
    assert "сгенерируй цветы; touch OUTSIDE" not in captured["argv"]
    assert ["--sandbox", "read-only"] == captured["argv"][
        captured["argv"].index("--sandbox") : captured["argv"].index("--sandbox") + 2
    ]
    assert "shell_tool" in captured["argv"]
    assert captured["argv"][captured["argv"].index("-C") + 1] == captured["cwd"]
    assert "image_generation" in captured["argv"]

    monkeypatch.setenv("KOLIBRI_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    artifact = image_artifacts._store_image(
        result.data,
        prompt="сгенерируй цветы",
        model=result.model,
    )
    verified = image_artifacts.verify_image_artifact(artifact)
    assert str(uuid.UUID(verified["id"])) == verified["id"]
    assert verified["mime_type"] == "image/png"
    assert verified["size_bytes"] == len(_PNG_1X1)
    assert verified["sha256"] == result.sha256
    assert "PRIVATE" not in json.dumps(verified, ensure_ascii=False)
    assert captured["cwd"] not in json.dumps(verified, ensure_ascii=False)


def test_edit_materializes_verified_new_image_from_host_bound_source(tmp_path):
    capture = tmp_path / "edit-capture.json"
    binary = _fake_codex(
        tmp_path,
        f"""
        prompt = sys.stdin.read()
        match = __import__('re').search(r'<kolibri_source_image_path>\\n([^\\n]+)', prompt)
        assert match
        source = match.group(1)
        with open(source, 'rb') as handle:
            source_bytes = handle.read()
        generated = os.path.join(os.environ['CODEX_HOME'], 'generated_images', 'edited.png')
        os.makedirs(os.path.dirname(generated), exist_ok=True)
        with open(generated, 'wb') as handle:
            handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        with open({str(capture)!r}, 'w', encoding='utf-8') as handle:
            json.dump({{'prompt': prompt, 'source_sha256': __import__('hashlib').sha256(source_bytes).hexdigest(), 'source': source}}, handle)
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':generated}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )
    provider = CodexCLIImageProvider(_settings(binary, tmp_path))

    result = asyncio.run(
        provider.generate(
            "Сделай фон тёплым",
            source_image=_PNG_1X1,
        )
    )
    captured = json.loads(capture.read_text(encoding="utf-8"))

    assert result.data == _PNG_1X1
    assert captured["source_sha256"] == hashlib.sha256(_PNG_1X1).hexdigest()
    assert "referenced_image_path" in captured["prompt"]
    assert "Сделай фон тёплым" in captured["prompt"]
    assert not Path(captured["source"]).exists()


def test_runtime_scratch_is_separate_and_never_scanned_as_an_artifact(tmp_path):
    capture = tmp_path / "scratch-capture.json"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        workspace = os.getcwd()
        scratch = os.environ['TMPDIR']
        os.makedirs(os.path.join(scratch, 'codex-bwrap-synthetic-mount-targets-1000'))
        with open(os.path.join(scratch, 'codex-bwrap-synthetic-mount-targets-1000', 'lock'), 'wb') as handle:
            handle.write(b'')
        with open(os.path.join(scratch, 'partial.png'), 'wb') as handle:
            handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        generated = os.path.join(os.environ['CODEX_HOME'], 'generated_images', 'output.png')
        os.makedirs(os.path.dirname(generated), exist_ok=True)
        with open(generated, 'wb') as handle:
            handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        with open({str(capture)!r}, 'w', encoding='utf-8') as handle:
            json.dump({{'cwd': workspace, 'tmpdir': scratch, 'tmp': os.environ['TMP'], 'temp': os.environ['TEMP']}}, handle)
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':generated}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )
    provider = CodexCLIImageProvider(_settings(binary, tmp_path))

    result = asyncio.run(provider.generate("сгенерируй цветы"))
    captured = json.loads(capture.read_text(encoding="utf-8"))

    assert result.data == _PNG_1X1
    assert Path(captured["cwd"]).name == "final"
    assert Path(captured["tmpdir"]).name == "scratch"
    assert captured["tmpdir"] == captured["tmp"] == captured["temp"]
    assert Path(captured["cwd"]).parent == Path(captured["tmpdir"]).parent
    assert captured["cwd"] != captured["tmpdir"]


def test_recoverable_error_event_before_completed_turn_keeps_verified_file(tmp_path):
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        generated = os.path.join(os.environ['CODEX_HOME'], 'generated_images', 'output.png')
        os.makedirs(os.path.dirname(generated), exist_ok=True)
        with open(generated, 'wb') as handle:
            handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        print(json.dumps({{'type':'error','message':'optional capability unavailable'}}), flush=True)
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':generated}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )
    provider = CodexCLIImageProvider(_settings(binary, tmp_path))

    result = asyncio.run(provider.generate("сгенерируй цветы"))

    assert result.data == _PNG_1X1
    assert result.sha256 == hashlib.sha256(_PNG_1X1).hexdigest()


def test_completed_message_may_wrap_one_trusted_root_path_in_prose(tmp_path):
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        generated = os.path.join(os.environ['CODEX_HOME'], 'generated_images', 'output.png')
        os.makedirs(os.path.dirname(generated), exist_ok=True)
        with open(generated, 'wb') as handle:
            handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':'Готово: ' + generated + '.'}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )

    result = asyncio.run(
        CodexCLIImageProvider(_settings(binary, tmp_path)).generate("сгенерируй цветы")
    )

    assert result.data == _PNG_1X1


def test_multiple_trusted_root_paths_are_rejected(tmp_path):
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        root = os.path.join(os.environ['CODEX_HOME'], 'generated_images')
        os.makedirs(root, exist_ok=True)
        first = os.path.join(root, 'first.png')
        second = os.path.join(root, 'second.png')
        for path in (first, second):
            with open(path, 'wb') as handle:
                handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':first + '\\n' + second}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )

    with pytest.raises(CodexCLIImageInvalidArtifact):
        asyncio.run(
            CodexCLIImageProvider(_settings(binary, tmp_path)).generate("сгенерируй цветы")
        )


def test_multiple_variants_bound_to_one_codex_thread_return_one_verified_image(tmp_path):
    thread_id = "019f60f2-6a0b-79a0-bb3f-76725f465251"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        root = os.path.join(os.environ['CODEX_HOME'], 'generated_images', {thread_id!r})
        os.makedirs(root, exist_ok=True)
        first = os.path.join(root, 'ig_first.png')
        second = os.path.join(root, 'ig_second.png')
        for path in (first, second):
            with open(path, 'wb') as handle:
                handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        print(json.dumps({{'type':'thread.started','thread_id':{thread_id!r}}}), flush=True)
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':first + '\\n' + second}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )

    result = asyncio.run(
        CodexCLIImageProvider(_settings(binary, tmp_path)).generate("сгенерируй один цветок")
    )

    assert result.data == _PNG_1X1
    assert result.sha256 == hashlib.sha256(_PNG_1X1).hexdigest()


def test_valid_image_outside_generated_root_is_rejected(tmp_path):
    outside = tmp_path / "outside.png"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        with open({str(outside)!r}, 'wb') as handle:
            handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':{str(outside)!r}}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )

    with pytest.raises(CodexCLIImageInvalidArtifact):
        asyncio.run(
            CodexCLIImageProvider(_settings(binary, tmp_path)).generate("сгенерируй цветы")
        )


def test_thread_bound_image_is_used_when_agent_claims_workspace_path(tmp_path):
    thread_id = "019f5ffa-dc92-7f33-b1cb-80d996a5af92"
    other_thread_id = "019f5ff9-a2b0-7a01-b062-73cc49c94fc0"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        root = os.path.join(os.environ['CODEX_HOME'], 'generated_images')
        generated = os.path.join(root, {thread_id!r}, 'ig_result.png')
        unrelated = os.path.join(root, {other_thread_id!r}, 'ig_other.png')
        os.makedirs(os.path.dirname(generated), exist_ok=True)
        os.makedirs(os.path.dirname(unrelated), exist_ok=True)
        for path in (generated, unrelated):
            with open(path, 'wb') as handle:
                handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        claimed = os.path.join(os.getcwd(), 'generated_image.png')
        print(json.dumps({{'type':'thread.started','thread_id':{thread_id!r}}}), flush=True)
        print(json.dumps({{'type':'item.completed','item':{{'type':'agent_message','text':claimed}}}}), flush=True)
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )

    result = asyncio.run(
        CodexCLIImageProvider(_settings(binary, tmp_path)).generate("сгенерируй цветы")
    )

    assert result.data == _PNG_1X1


def test_scratch_image_without_final_image_is_rejected(tmp_path):
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        with open(os.path.join(os.environ['TMPDIR'], 'scratch-only.png'), 'wb') as handle:
            handle.write(bytes.fromhex({_PNG_1X1.hex()!r}))
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )
    provider = CodexCLIImageProvider(_settings(binary, tmp_path))

    with pytest.raises(CodexCLIImageInvalidArtifact):
        asyncio.run(provider.generate("сгенерируй цветы"))


@pytest.mark.parametrize(
    "body",
    [
        """
        _ = sys.stdin.read()
        print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Изображение создано'}}), flush=True)
        print(json.dumps({'type':'turn.completed'}), flush=True)
        """,
        """
        _ = sys.stdin.read()
        generated = os.path.join(os.environ['CODEX_HOME'], 'generated_images', 'output.png')
        os.makedirs(os.path.dirname(generated), exist_ok=True)
        with open(generated, 'wb') as handle:
            handle.write(b'not-an-image')
        print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':generated}}), flush=True)
        print(json.dumps({'type':'turn.completed'}), flush=True)
        """,
    ],
    ids=["fake_text_without_file", "invalid_mime"],
)
def test_text_claim_or_invalid_mime_never_becomes_an_artifact(tmp_path, body):
    provider = CodexCLIImageProvider(_settings(_fake_codex(tmp_path, body), tmp_path))

    with pytest.raises(CodexCLIImageInvalidArtifact) as error:
        asyncio.run(provider.generate("сгенерируй цветы"))

    assert str(error.value) == "codex_cli_image_invalid_artifact"


def test_timeout_terminates_attempt_and_returns_no_file(tmp_path):
    marker = tmp_path / "late-file"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        print(json.dumps({{'type':'thread.started'}}), flush=True)
        time.sleep(2)
        with open({str(marker)!r}, 'w') as handle:
            handle.write('late')
        """,
    )
    provider = CodexCLIImageProvider(
        _settings(binary, tmp_path, attempt_timeout_seconds=0.15)
    )

    with pytest.raises(CodexCLIImageTimeout):
        asyncio.run(provider.generate("сгенерируй цветы"))

    assert not marker.exists()


def test_explicit_cancel_terminates_process_group_and_returns_no_artifact(tmp_path):
    started = tmp_path / "started"
    marker = tmp_path / "late-file"
    binary = _fake_codex(
        tmp_path,
        f"""
        _ = sys.stdin.read()
        with open({str(started)!r}, 'w') as handle:
            handle.write('started')
        print(json.dumps({{'type':'thread.started'}}), flush=True)
        time.sleep(3)
        with open({str(marker)!r}, 'w') as handle:
            handle.write('late')
        print(json.dumps({{'type':'turn.completed'}}), flush=True)
        """,
    )
    provider = CodexCLIImageProvider(
        _settings(binary, tmp_path, attempt_timeout_seconds=5.0)
    )

    async def scenario():
        task = asyncio.create_task(
            provider.generate("сгенерируй цветы", run_id="cancel-image")
        )
        for _ in range(300):
            if started.exists():
                break
            await asyncio.sleep(0.01)
        assert started.exists()
        assert await provider.cancel("cancel-image") is True
        with pytest.raises(CodexCLIImageCancelled):
            await task

    asyncio.run(scenario())
    assert not marker.exists()
