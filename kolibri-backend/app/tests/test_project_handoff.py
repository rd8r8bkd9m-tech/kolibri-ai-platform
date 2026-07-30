from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.browser_session import issue_anonymous_session
from app.models import ProjectHandoffDB
from app.project_handoff import (
    ProjectHandoffAlreadyClaimed,
    ProjectHandoffConfigurationError,
    ProjectHandoffExpired,
    ProjectHandoffNotFound,
    adopt_anonymous_project_access,
    claim_project_handoff,
    issue_project_handoff,
)
from app.project_history import ProjectHistoryRepository, ProjectNotFoundError


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv(
        "KOLIBRI_PROJECT_HANDOFF_SECRET",
        "test-project-handoff-secret-0123456789abcdef",
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_handoff_is_one_use_project_scoped_and_keeps_both_surfaces_live(db):
    source = ProjectHistoryRepository(db, "telegram:7001")
    project, _ = source.create_project({"title": "Telegram", "metadata": {}}, "telegram-chat:7001")
    source.append_message(
        project["id"],
        {"role": "user", "content": "Начало в Telegram", "status": "completed", "metadata": {}},
        "telegram-message:1",
    )

    token = issue_project_handoff(
        db,
        project_id=project["id"],
        source_scope_id="telegram:7001",
        idempotency_key="telegram-update:1:project-handoff",
    )
    assert issue_project_handoff(
        db,
        project_id=project["id"],
        source_scope_id="telegram:7001",
        idempotency_key="telegram-update:1:project-handoff",
    ) == token
    stored = db.query(ProjectHandoffDB).one()
    assert stored.token_hash != token
    assert len(stored.token_hash) == 64

    claimed = claim_project_handoff(
        db,
        project_id=project["id"],
        target_scope_id="anon:browser-one",
        token=token,
    )
    assert claimed["id"] == project["id"]
    browser = ProjectHistoryRepository(db, "anon:browser-one")
    assert browser.list_messages(project["id"], after=0, limit=10)["total"] == 1
    browser.append_message(
        project["id"],
        {"role": "user", "content": "Продолжение в Web", "status": "completed", "metadata": {}},
        "browser-message:1",
    )
    assert source.list_messages(project["id"], after=0, limit=10)["total"] == 2

    # Removing a handed-off project only removes it from that surface. The
    # Telegram-owned canonical project remains live, and Undo restores access.
    removed = browser.soft_delete_project(project["id"])
    assert removed["status"] == "deleted"
    assert removed["deleted_at"] is not None
    with pytest.raises(ProjectNotFoundError):
        browser.get_project(project["id"])
    source.append_message(
        project["id"],
        {"role": "user", "content": "Telegram всё ещё работает", "status": "completed", "metadata": {}},
        "telegram-message:2",
    )
    assert source.list_messages(project["id"], after=0, limit=10)["total"] == 3
    assert browser.restore_project(project["id"])["id"] == project["id"]
    assert browser.list_messages(project["id"], after=0, limit=10)["total"] == 3

    assert claim_project_handoff(
        db,
        project_id=project["id"],
        target_scope_id="anon:browser-one",
        token=token,
    )["id"] == project["id"]
    with pytest.raises(ProjectHandoffAlreadyClaimed):
        claim_project_handoff(
            db,
            project_id=project["id"],
            target_scope_id="anon:browser-two",
            token=token,
        )
    with pytest.raises(ProjectHandoffNotFound):
        claim_project_handoff(
            db,
            project_id=project["id"],
            target_scope_id="anon:browser-one",
            token="B" * 43,
        )


def test_expired_handoff_never_creates_a_grant(db):
    source = ProjectHistoryRepository(db, "telegram:7001")
    project, _ = source.create_project({"title": "Telegram", "metadata": {}}, "telegram-chat:7001")
    token = issue_project_handoff(
        db,
        project_id=project["id"],
        source_scope_id="telegram:7001",
        idempotency_key="telegram-update:2:project-handoff",
    )
    handoff = db.query(ProjectHandoffDB).one()
    handoff.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    with pytest.raises(ProjectHandoffExpired):
        claim_project_handoff(
            db,
            project_id=project["id"],
            target_scope_id="anon:expired",
            token=token,
        )
    with pytest.raises(ProjectNotFoundError):
        ProjectHistoryRepository(db, "anon:expired").get_project(project["id"])

    replacement = issue_project_handoff(
        db,
        project_id=project["id"],
        source_scope_id="telegram:7001",
        idempotency_key="telegram-update:2:project-handoff",
    )
    assert replacement != token
    with pytest.raises(ProjectHandoffNotFound):
        claim_project_handoff(
            db,
            project_id=project["id"],
            target_scope_id="anon:expired",
            token=token,
        )
    assert claim_project_handoff(
        db,
        project_id=project["id"],
        target_scope_id="anon:replacement",
        token=replacement,
    )["id"] == project["id"]


def test_handoff_requires_a_dedicated_secret(db, monkeypatch):
    source = ProjectHistoryRepository(db, "telegram:7001")
    project, _ = source.create_project({"title": "Telegram", "metadata": {}}, "telegram-chat:7001")
    monkeypatch.delenv("KOLIBRI_PROJECT_HANDOFF_SECRET", raising=False)

    with pytest.raises(ProjectHandoffConfigurationError):
        issue_project_handoff(
            db,
            project_id=project["id"],
            source_scope_id="telegram:7001",
            idempotency_key="telegram-update:missing-secret:project-handoff",
        )


def test_anonymous_handoff_access_moves_to_authenticated_scope(db):
    source = ProjectHistoryRepository(db, "telegram:7001")
    project, _ = source.create_project({"title": "Telegram", "metadata": {}}, "telegram-chat:7001")
    token = issue_project_handoff(
        db,
        project_id=project["id"],
        source_scope_id="telegram:7001",
        idempotency_key="telegram-update:3:project-handoff",
    )
    cookie, anonymous = issue_anonymous_session(sid="browser-session-id-with-more-than-forty-characters")
    claim_project_handoff(
        db,
        project_id=project["id"],
        target_scope_id=anonymous.scope_id,
        token=token,
    )

    assert adopt_anonymous_project_access(
        db,
        anonymous_cookie=cookie,
        target_scope_id="user:owner-one",
    ) == 1
    db.commit()
    assert ProjectHistoryRepository(db, "user:owner-one").get_project(project["id"])["id"] == project["id"]
    assert claim_project_handoff(
        db,
        project_id=project["id"],
        target_scope_id="user:owner-one",
        token=token,
    )["id"] == project["id"]
    with pytest.raises(ProjectHandoffAlreadyClaimed):
        claim_project_handoff(
            db,
            project_id=project["id"],
            target_scope_id=anonymous.scope_id,
            token=token,
        )
    with pytest.raises(ProjectNotFoundError):
        ProjectHistoryRepository(db, anonymous.scope_id).get_project(project["id"])
    with pytest.raises(ProjectNotFoundError):
        ProjectHistoryRepository(db, anonymous.scope_id).restore_project(project["id"])
    assert adopt_anonymous_project_access(
        db,
        anonymous_cookie=cookie,
        target_scope_id="user:owner-one",
    ) == 0
