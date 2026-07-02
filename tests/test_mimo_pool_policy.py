import argparse
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_factory_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_args(tmp_path, max_inflight=99):
    return argparse.Namespace(
        control_url="http://127.0.0.1:9101",
        control_urls="http://127.0.0.1:9101",
        node_id="pool-node-1",
        agent_id="agent-host-pool-node-1",
        capabilities="generic_implementation,runner:mimo",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=max_inflight,
    )


def test_agent_host_caps_max_inflight_and_reports_pool_on_register(tmp_path):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, max_inflight=200))
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    host = Host()
    host.register()

    assert host.max_inflight == 20
    path, body = host.posts[0]
    assert path == "/v1/nodes/register"
    assert body["max_inflight"] == 20
    assert body["agent_pool"]["configured_agents"] == 20
    assert body["agent_pool"]["max_agents_per_server"] == 20
    assert body["pool_policy"]["external_api_guardrails"]["no_provider_bypass"] is True


def test_factory_control_classified_nodes_include_pool_status():
    control = load_factory_control()
    node = control.classify_node_freshness({
        "node_id": "pool-node-2",
        "health": "online",
        "heartbeat_at": control.utc_now(),
        "max_inflight": 999,
    })

    assert node["agent_pool"]["configured_agents"] == 20
    assert node["agent_pool"]["available_agents"] == 20
    assert node["agent_pool"]["ready"] is True


def test_factory_control_policy_exposes_bootstrap_and_service_template():
    control = load_factory_control()

    assert control.pool_policy()["max_agents_per_server"] == 20
    assert control.BOOTSTRAP_CONTRACT["agent_pool"]["service_template"] == "ops/systemd/kolibri-agent-host@.service"
    assert control.BOOTSTRAP_CONTRACT["agent_pool"]["helper"] == "ops/kolibri-agent-pool"
