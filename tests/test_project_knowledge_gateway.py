from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import capability_gateway
import execution_api
import project_knowledge_gateway
import provider_gateway
import public_responses_api


ORIGIN = "http://testserver"
OWNER_LINE = "Кочуров Владислав Евгеньевич. Role: Chief Visionary, Owner, Lead Developer, Final Authority."


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (root / "backend").mkdir()
    (root / "README.md").write_text("Kolibri AI OS\n", encoding="utf-8")
    (docs / "OWNER.md").write_text(
        "# Owner\n\n"
        f"{OWNER_LINE}\n"
        "Internal endpoint: http://10.99.0.2:9101 and /etc/kolibri/private.\n"
        "api_" + "key=not-a-real-secret-but-must-be-redacted\n",
        encoding="utf-8",
    )
    runtime = docs / "agent" / "runs"
    runtime.mkdir(parents=True)
    (runtime / "result.md").write_text("runtime evidence must not be indexed", encoding="utf-8")
    secret = docs / ".env.production"
    secret.write_text("TOKEN=must-not-be-read", encoding="utf-8")
    link = docs / "linked.md"
    try:
        link.symlink_to(Path("OWNER.md"))
    except OSError:
        pass
    return root


def _authorization() -> project_knowledge_gateway.ProjectKnowledgeAuthorization:
    return project_knowledge_gateway.ProjectKnowledgeAuthorization(
        principal="api-key:0123456789abcdef",
        response_id="resp_test",
        allowed_tool_ids=(project_knowledge_gateway.TOOL_ID,),
    )


def _provider_evidence(text: str) -> list[dict]:
    encoded = text.encode("utf-8")
    return [{
        "type": "provider_execution",
        "provider": "factory",
        "provider_model": "codex",
        "exit_code": 0,
        "output_sha256": hashlib.sha256(encoded).hexdigest(),
        "output_bytes": len(encoded),
    }]


class CitationProvider:
    def __init__(self, *, cite: bool = True):
        self.cite = cite
        self.calls: list[dict] = []

    def generate(self, input_value, instructions, response_id, **kwargs):
        self.calls.append({
            "input": input_value,
            "instructions": instructions,
            "response_id": response_id,
            **kwargs,
        })
        text = (
            "Кочуров Владислав Евгеньевич — владелец и final authority проекта [P1]."
            if self.cite
            else "Кочуров Владислав Евгеньевич — владелец и final authority проекта."
        )
        return SimpleNamespace(
            status="completed",
            text=text,
            technical={"evidence": _provider_evidence(text), "tool_calls": []},
        )


def _owner_client(tmp_path: Path, repo: Path, gateway: CitationProvider) -> TestClient:
    execution_api.configure_execution_store(tmp_path / "execution.db")
    execution_api.configure_execution_auth(["owner-key"])
    capability_gateway.configure_capability_gateway(
        capability_gateway.CapabilityGateway([], cache_ttl=0, include_packaged_registry=True)
    )
    project_knowledge_gateway.configure_project_knowledge_gateway(
        project_knowledge_gateway.ProjectKnowledgeGateway(repo)
    )
    provider_gateway.configure_provider_gateway(gateway)
    app = FastAPI()
    app.include_router(execution_api.router)
    return TestClient(app, headers={"Authorization": "Bearer owner-key"})


def test_owner_index_returns_bounded_content_bound_provenance_and_redacts_topology(tmp_path):
    gateway = project_knowledge_gateway.ProjectKnowledgeGateway(_repo(tmp_path))
    result = gateway.execute(
        "Кто такой Кочуров Владислав Евгеньевич и какая у него роль?",
        authorization=_authorization(),
    )

    assert result["status"] == "completed"
    citation = result["citations"][0]
    assert citation["path"] == "docs/OWNER.md"
    assert citation["line_start"] >= 1
    assert citation["line_end"] >= citation["line_start"]
    assert len(citation["file_sha256"]) == len(citation["span_sha256"]) == 64
    assert citation["marker"] == "[P1]"
    serialized = json.dumps(result, ensure_ascii=False)
    assert "10.99.0.2" not in serialized
    assert "/etc/kolibri" not in serialized
    assert "not-a-real-secret" not in serialized
    assert "[INTERNAL_URL_REDACTED]" in serialized
    assert "[INTERNAL_PATH_REDACTED]" in serialized
    assert "[REDACTED]" in serialized
    assert "runtime evidence must not be indexed" not in serialized


def test_canonical_project_docs_prove_owner_and_final_authority():
    result = project_knowledge_gateway.ProjectKnowledgeGateway(ROOT).execute(
        "Кто такой Кочуров Владислав Евгеньевич и какая его роль в проекте Kolibri?",
        authorization=_authorization(),
    )
    supporting = [
        citation for citation in result["citations"]
        if "Кочуров Владислав Евгеньевич" in citation["excerpt"]
        and (
            "Final Authority" in citation["excerpt"]
            or "final authority" in citation["excerpt"]
            or "Владелец" in citation["excerpt"]
        )
    ]
    assert supporting
    assert all(citation["path"].startswith("docs/") for citation in supporting)
    assert all(citation["line_start"] <= citation["line_end"] for citation in supporting)
    assert all(len(citation["file_sha256"]) == 64 for citation in supporting)
    assert all(len(citation["span_sha256"]) == 64 for citation in supporting)


def test_project_knowledge_rejects_public_principal(tmp_path):
    gateway = project_knowledge_gateway.ProjectKnowledgeGateway(_repo(tmp_path))
    with pytest.raises(project_knowledge_gateway.ProjectKnowledgeError) as captured:
        gateway.execute(
            "документы проекта",
            authorization=project_knowledge_gateway.ProjectKnowledgeAuthorization(
                principal="public-session:hash",
                response_id="resp_public",
                allowed_tool_ids=(project_knowledge_gateway.TOOL_ID,),
            ),
        )
    assert captured.value.code == "project_knowledge_owner_required"


@pytest.mark.parametrize("text", [
    "в проекте колибри документы посмотри",
    "документы проекта покажи",
    "Кто такой Кочуров Владислав Евгеньевич в Kolibri?",
    "Какая роль владельца в проекте?",
])
def test_project_context_phrases_auto_plan_owner_index(text):
    assert project_knowledge_gateway.should_auto_plan_project_knowledge(text) is True


@pytest.mark.parametrize("text", [
    "как дела в Москве?",
    "найди свежую погоду в интернете",
    "привет",
])
def test_project_index_is_never_an_internet_substitute(text):
    assert project_knowledge_gateway.should_auto_plan_project_knowledge(text) is False


def test_owner_response_followup_uses_project_evidence_and_citations(tmp_path):
    repo = _repo(tmp_path)
    provider = CitationProvider()
    client = _owner_client(tmp_path, repo, provider)

    first = client.post("/v1/responses", json={
        "model": "kolibri",
        "idempotency_key": "owner-person-question",
        "input": "Кто такой Кочуров Владислав Евгеньевич в Kolibri?",
        "execution_mode": "codex",
    })
    assert first.status_code == 201
    assert first.json()["status"] == "completed"

    followup = client.post("/v1/responses", json={
        "model": "kolibri",
        "idempotency_key": "owner-project-docs-followup",
        "input": "в проекте колибри документы посмотри",
        "previous_response_id": first.json()["id"],
        "execution_mode": "codex",
    })
    assert followup.status_code == 201
    payload = followup.json()
    assert payload["status"] == "completed"
    assert payload["output_text"].endswith("[P1].")
    assert payload["citations"][0]["path"] == "docs/OWNER.md"
    assert payload["technical"]["provider_routing"]["verifier_evidence"]["verdict"] == "passed"
    assert payload["technical"]["provider_routing"]["verifier_evidence"]["checks"][
        "project_knowledge_answer_cited"
    ] is True
    assert OWNER_LINE in provider.calls[-1]["instructions"]


def test_owner_project_answer_fails_closed_without_citation_marker(tmp_path):
    client = _owner_client(tmp_path, _repo(tmp_path), CitationProvider(cite=False))
    response = client.post("/v1/responses", json={
        "model": "kolibri",
        "idempotency_key": "owner-project-no-citation",
        "input": "Кто такой Кочуров Владислав Евгеньевич в Kolibri?",
    })
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "tool_verification_failed"
    assert payload["technical"]["provider_routing"]["verifier_evidence"]["checks"][
        "project_knowledge_answer_cited"
    ] is False


def test_public_session_cannot_request_project_knowledge(tmp_path):
    repo = _repo(tmp_path)
    public_responses_api.configure_public_response_store(tmp_path / "public.db")
    public_responses_api.configure_public_response_origins([ORIGIN])
    capability_gateway.configure_capability_gateway(
        capability_gateway.CapabilityGateway([], cache_ttl=0, include_packaged_registry=True)
    )
    project_knowledge_gateway.configure_project_knowledge_gateway(
        project_knowledge_gateway.ProjectKnowledgeGateway(repo)
    )
    app = FastAPI()
    app.include_router(public_responses_api.router)
    client = TestClient(app)
    assert client.post("/v1/public/session", headers={"Origin": ORIGIN}).status_code == 200
    denied = client.post(
        "/v1/responses",
        headers={"Origin": ORIGIN, "Idempotency-Key": "public-project-tool"},
        json={
            "model": "kolibri",
            "input": "документы проекта",
            "tools": [{"type": "project_knowledge"}],
        },
    )
    assert denied.status_code == 422
    assert denied.json()["detail"] == "public_session_tool_not_allowed"
