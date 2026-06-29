from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MESH_FILES = [
    ROOT / "infra" / "network" / "api.py",
    ROOT / "infra" / "network" / "organism.py",
]


def test_mesh_api_does_not_expose_direct_exec_endpoint():
    for path in MESH_FILES:
        text = path.read_text(encoding="utf-8")
        assert "/task/execute" not in text
        assert "api/exec" not in text


def test_mesh_api_does_not_spawn_shell_commands():
    for path in MESH_FILES:
        text = path.read_text(encoding="utf-8")
        assert "import subprocess" not in text
        assert "subprocess." not in text
        assert "shell=True" not in text
        assert "os.system" not in text
        assert "os.popen" not in text
        assert "--dangerously-skip-permissions" not in text


def test_mesh_compute_delegates_to_control_plane():
    for path in MESH_FILES:
        text = path.read_text(encoding="utf-8")
        assert "CONTROL_PLANE_URL" in text
        assert "submit_control_plane_task" in text
        assert "owner_remote_task" in text


def test_mesh_filesystem_delegates_to_control_plane_namespace():
    for path in MESH_FILES:
        text = path.read_text(encoding="utf-8")
        assert '@app.get("/filesystem")' in text
        assert '@app.get("/mesh/filesystem")' in text
        assert 'client.get(f"{CONTROL_PLANE_URL}/v1/filesystem")' in text
        assert "get_control_plane_filesystem" in text


def test_mesh_filesystem_helper_does_not_read_local_files_or_spawn_commands():
    markers = [
        "Path(",
        "open(",
        ".read_text(",
        "import subprocess",
        "subprocess.",
        "shell=True",
        "os.system",
        "os.popen",
    ]
    for path in MESH_FILES:
        text = path.read_text(encoding="utf-8")
        helper = text.split("async def get_control_plane_filesystem", 1)[1].split(
            "def get_system_load",
            1,
        )[0]
        for marker in markers:
            assert marker not in helper
