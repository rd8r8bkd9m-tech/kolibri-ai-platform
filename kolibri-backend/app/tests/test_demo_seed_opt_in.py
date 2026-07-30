from app import storage


def test_demo_seed_is_disabled_by_default(monkeypatch):
    calls = []
    monkeypatch.delenv("KOLIBRI_DEMO_SEED_ENABLED", raising=False)
    monkeypatch.setattr(storage, "seed_db", lambda db: calls.append(db))

    assert storage.seed_demo_data_if_enabled(object()) is False
    assert calls == []


def test_demo_seed_requires_explicit_true_value(monkeypatch):
    database = object()
    calls = []
    monkeypatch.setattr(storage, "seed_db", lambda db: calls.append(db))

    for disabled in ("", "0", "false", "no", "unexpected"):
        monkeypatch.setenv("KOLIBRI_DEMO_SEED_ENABLED", disabled)
        assert storage.seed_demo_data_if_enabled(database) is False

    monkeypatch.setenv("KOLIBRI_DEMO_SEED_ENABLED", "true")
    assert storage.seed_demo_data_if_enabled(database) is True
    assert calls == [database]
