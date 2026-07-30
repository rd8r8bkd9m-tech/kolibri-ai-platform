from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock


WORKERS_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = WORKERS_ROOT.parents[1] / "backend"
LAUNCHER_PATH = WORKERS_ROOT / "worker_launcher.py"
SPEC = importlib.util.spec_from_file_location(
    "kolibri_v3_worker_launcher",
    LAUNCHER_PATH,
)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class CanonicalDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.database = self.root / "kolibri-v3.db"
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("CREATE TABLE health (id INTEGER PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()
        self.database.chmod(0o600)
        self.database_url = f"sqlite:///{self.database}"
        self.environment = {
            "KOLIBRI_V3_ENV": "production",
            "KOLIBRI_V3_DATABASE_URL": self.database_url,
            "KOLIBRI_WORKER_EXPECTED_DATABASE_URL": self.database_url,
        }

    def test_accepts_exact_owned_writable_database(self) -> None:
        with mock.patch.dict(os.environ, self.environment, clear=True):
            self.assertEqual(
                launcher.validate_canonical_database(),
                self.database,
            )

    def test_rejects_a_different_database_even_when_it_exists(self) -> None:
        foreign = self.root / "foreign.db"
        foreign.touch(mode=0o600)
        environment = dict(self.environment)
        environment["KOLIBRI_V3_DATABASE_URL"] = f"sqlite:///{foreign}"
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(
                launcher.WorkerConfigurationError,
                "database_url_not_canonical",
            ):
                launcher.validate_canonical_database()

    def test_rejects_symlinked_database(self) -> None:
        alias = self.root / "database-alias.db"
        alias.symlink_to(self.database)
        environment = dict(self.environment)
        alias_url = f"sqlite:///{alias}"
        environment["KOLIBRI_V3_DATABASE_URL"] = alias_url
        environment["KOLIBRI_WORKER_EXPECTED_DATABASE_URL"] = alias_url
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(
                launcher.WorkerConfigurationError,
                "canonical_database_unsafe",
            ):
                launcher.validate_canonical_database()

    def test_rejects_group_writable_database(self) -> None:
        self.database.chmod(0o620)
        self.addCleanup(self.database.chmod, 0o600)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(
                launcher.WorkerConfigurationError,
                "canonical_database_permissions_invalid",
            ):
                launcher.validate_canonical_database()

    def test_rejects_world_readable_database(self) -> None:
        self.database.chmod(0o644)
        self.addCleanup(self.database.chmod, 0o600)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(
                launcher.WorkerConfigurationError,
                "canonical_database_permissions_invalid",
            ):
                launcher.validate_canonical_database()

    def test_rejects_world_readable_wal_sidecar(self) -> None:
        sidecar = Path(f"{self.database}-wal")
        sidecar.touch(mode=0o644)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(
                launcher.WorkerConfigurationError,
                "canonical_database_sidecar_unsafe",
            ):
                launcher.validate_canonical_database()


class OwnershipAndCommandTests(unittest.TestCase):
    def test_release_identity_is_exact_and_lowercase(self) -> None:
        valid = {
            "KOLIBRI_RELEASE_ID": "kolibri-v3-0123456789ab-abcdef012345",
            "KOLIBRI_RELEASE_COMMIT":
                "0123456789abcdef0123456789abcdef01234567",
        }
        with mock.patch.dict(os.environ, valid, clear=True):
            self.assertEqual(
                launcher.validate_release_identity(),
                (
                    valid["KOLIBRI_RELEASE_ID"],
                    valid["KOLIBRI_RELEASE_COMMIT"],
                ),
            )

        for key, value, code in (
            (
                "KOLIBRI_RELEASE_ID",
                "kolibri-v3-0123456789AB-abcdef012345",
                "release_id_invalid",
            ),
            (
                "KOLIBRI_RELEASE_COMMIT",
                "0123456789ABCDEF0123456789ABCDEF01234567",
                "release_commit_invalid",
            ),
        ):
            with self.subTest(key=key):
                invalid = dict(valid)
                invalid[key] = value
                with (
                    mock.patch.dict(os.environ, invalid, clear=True),
                    self.assertRaisesRegex(
                        launcher.WorkerConfigurationError,
                        code,
                    ),
                ):
                    launcher.validate_release_identity()

    def test_second_local_owner_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            runtime.chmod(0o700)
            environment = {
                "KOLIBRI_WORKER_LOCK_PATH": str(runtime / "owner.lock")
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                first = launcher.acquire_owner_lock()
                self.addCleanup(os.close, first)
                with self.assertRaises(launcher.WorkerOwnershipError):
                    launcher.acquire_owner_lock()

    def test_only_read_only_reconciliation_is_allowlisted(self) -> None:
        command = launcher.worker_command("estimate-audit")
        self.assertEqual(command[1:], ("-m", "app.estimate_reconciliation"))
        self.assertNotIn("--apply", command)
        with self.assertRaises(launcher.WorkerConfigurationError):
            launcher.worker_command("estimate-apply")


@unittest.skipUnless(
    importlib.util.find_spec("httpx") is not None
    and importlib.util.find_spec("fastapi") is not None,
    "backend runtime dependencies are required",
)
class RuntimeConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name).resolve()
        self.database = root / "kolibri-v3.db"
        self.database.touch(mode=0o600)
        token = root / "token"
        token.write_text("t" * 32, encoding="utf-8")
        token.chmod(0o600)
        identity_key = root / "identity-key"
        identity_key.write_text("k" * 32, encoding="utf-8")
        identity_key.chmod(0o600)
        self.environment = {
            "KOLIBRI_V3_ENV": "production",
            "KOLIBRI_V3_DATABASE_URL": f"sqlite:///{self.database}",
            "KOLIBRI_V3_ALLOWED_ORIGINS": "https://kolibriai.ru",
            "KOLIBRI_V3_COOKIE_SECURE": "true",
            "KOLIBRI_V3_CSRF_SECRET": "c" * 40,
            "KOLIBRI_V3_PRODUCT_AUTHORITY_ID":
                "authority_product_data_v1",
            "KOLIBRI_V3_PRODUCT_AUTHORITY_EPOCH": "1",
            "KOLIBRI_V3_PRODUCT_AUTHORITY_PLACEMENT_ID":
                "placement_product_backend",
            "KOLIBRI_V3_PRODUCT_AUTHORIZATION_DECISION_ID":
                "decision_product_data_v1",
            "KOLIBRI_V3_HOME_PRODUCT_COMMAND_URL": (
                "http://127.0.0.1:39231/v1/runtime/product-text-runs"
            ),
            "KOLIBRI_V3_HOME_PRODUCT_COMMAND_TOKEN_FILE": str(token),
            "KOLIBRI_V3_HOME_PRODUCT_IDENTITY_HMAC_KEY_FILE":
                str(identity_key),
            "KOLIBRI_V3_PROVIDER_AUTHORITY_DISPATCH_CONFIGURED": "true",
            "KOLIBRI_V3_PROVIDER_AUTHORITY_COMMAND_URL": (
                "http://127.0.0.1:39231/v1/runtime/"
                "product-provider-enrollment-intents"
            ),
            "KOLIBRI_V3_PROVIDER_AUTHORITY_COMMAND_TOKEN_FILE": str(token),
            "KOLIBRI_V3_PROVIDER_AUTHORITY_IDENTITY_HMAC_KEY_FILE":
                str(identity_key),
        }

    def _validate(self, worker_kind: str) -> None:
        with (
            mock.patch.dict(os.environ, self.environment, clear=True),
            mock.patch.object(
                launcher.Path,
                "cwd",
                return_value=BACKEND_ROOT,
            ),
        ):
            launcher.validate_runtime_configuration(worker_kind)

    def test_product_and_provider_dispatch_validate_exactly(self) -> None:
        self._validate("product-run")
        self._validate("provider-enrollment")

    def test_provider_dispatch_flag_fails_closed(self) -> None:
        self.environment[
            "KOLIBRI_V3_PROVIDER_AUTHORITY_DISPATCH_CONFIGURED"
        ] = "false"
        with self.assertRaisesRegex(
            launcher.WorkerConfigurationError,
            "provider_authority_dispatch_not_configured",
        ):
            self._validate("provider-enrollment")

    def test_provider_transport_cannot_outlive_its_lease(self) -> None:
        self.environment[
            "KOLIBRI_V3_PROVIDER_ENROLLMENT_LEASE_SECONDS"
        ] = "5"
        self.environment[
            "KOLIBRI_V3_PROVIDER_AUTHORITY_REQUEST_TIMEOUT_SECONDS"
        ] = "10"
        with self.assertRaisesRegex(
            launcher.WorkerConfigurationError,
            "provider_authority_lease_too_short",
        ):
            self._validate("provider-enrollment")

    def test_missing_product_transport_secret_fails_closed(self) -> None:
        self.environment.pop(
            "KOLIBRI_V3_HOME_PRODUCT_COMMAND_TOKEN_FILE"
        )
        with self.assertRaisesRegex(
            launcher.WorkerConfigurationError,
            "home_product_command_token_invalid",
        ):
            self._validate("product-run")

    def test_combined_reconciliation_audit_keeps_database_unchanged(
        self,
    ) -> None:
        self._validate("estimate-audit")
        from app.database import initialize_database

        initialize_database(self.environment["KOLIBRI_V3_DATABASE_URL"])
        self.database.chmod(0o600)
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, self.environment, clear=True),
            mock.patch.object(
                launcher.Path,
                "cwd",
                return_value=BACKEND_ROOT,
            ),
            redirect_stdout(output),
        ):
            exit_code = launcher.run_reconciliation_audit(self.database)
        after = hashlib.sha256(self.database.read_bytes()).hexdigest()
        self.assertEqual(exit_code, 0)
        self.assertEqual(after, before)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["runtime"]["gate"], "pass")
        self.assertEqual(payload["estimate_repairs"], [])


class RuntimeAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database_path = (
            Path(self.temporary.name).resolve() / "kolibri-v3.db"
        )
        database = sqlite3.connect(self.database_path)
        try:
            database.executescript(
                """
                CREATE TABLE chat_runs (
                    tenant_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, id)
                );
                CREATE TABLE chat_run_execution_contexts (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id)
                );
                CREATE TABLE product_run_outbox (
                    tenant_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, run_id)
                );
                """
            )
            database.executemany(
                """
                INSERT INTO chat_runs (
                    tenant_id, id, status, heartbeat_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (
                        "tenant-a",
                        "run-developer-stale",
                        "running",
                        "2026-07-29T09:00:00+00:00",
                    ),
                    (
                        "tenant-a",
                        "run-standard-stale",
                        "running",
                        "2026-07-29T10:00:00+00:00",
                    ),
                    (
                        "tenant-a",
                        "run-standard-fresh",
                        "running",
                        "2026-07-30T11:45:00+00:00",
                    ),
                ),
            )
            database.executemany(
                """
                INSERT INTO chat_run_execution_contexts (
                    tenant_id, run_id, execution_mode
                ) VALUES (?, ?, ?)
                """,
                (
                    (
                        "tenant-a",
                        "run-developer-stale",
                        "developer",
                    ),
                    (
                        "tenant-a",
                        "run-standard-stale",
                        "standard",
                    ),
                    (
                        "tenant-a",
                        "run-standard-fresh",
                        "standard",
                    ),
                ),
            )
            database.executemany(
                """
                INSERT INTO product_run_outbox (
                    tenant_id, run_id, state
                ) VALUES (?, ?, ?)
                """,
                (
                    (
                        "tenant-a",
                        "run-developer-stale",
                        "blocked",
                    ),
                    (
                        "tenant-a",
                        "run-standard-fresh",
                        "blocked",
                    ),
                ),
            )
            database.commit()
        finally:
            database.close()

    def test_audit_finds_stale_runs_by_mode_and_blocked_outbox(self) -> None:
        result = launcher.runtime_audit(
            self.database_path,
            now=datetime.fromisoformat("2026-07-30T12:00:00+00:00"),
            stale_after_seconds=3600,
        )
        self.assertEqual(result["gate"], "blocked")
        self.assertEqual(result["blocked_product_outbox"], 2)
        self.assertEqual(
            result["stale_running"],
            {
                "total": 2,
                "by_execution_mode": {
                    "developer": 1,
                    "standard": 1,
                },
                "by_outbox_state": {
                    "blocked": 1,
                    "missing": 1,
                },
                "oldest_heartbeat_at":
                    "2026-07-29T09:00:00+00:00",
            },
        )
        serialized = str(result)
        self.assertNotIn("run-developer-stale", serialized)
        self.assertNotIn("run-standard-stale", serialized)

    def test_audit_passes_after_stale_runs_are_terminal(self) -> None:
        database = sqlite3.connect(self.database_path)
        try:
            database.execute(
                """
                UPDATE chat_runs
                SET status = 'failed'
                WHERE heartbeat_at < '2026-07-30'
                """
            )
            database.commit()
        finally:
            database.close()
        result = launcher.runtime_audit(
            self.database_path,
            now=datetime.fromisoformat("2026-07-30T12:00:00+00:00"),
            stale_after_seconds=3600,
        )
        self.assertEqual(result["gate"], "pass")
        self.assertEqual(result["stale_running"]["total"], 0)


class UnitTemplateTests(unittest.TestCase):
    def _unit(self, name: str) -> str:
        return (WORKERS_ROOT / name).read_text(encoding="utf-8")

    def test_durable_workers_share_backend_env_and_hardening(self) -> None:
        for name in (
            "kolibri-v3-product-run-worker.service.in",
            "kolibri-v3-provider-enrollment-worker.service.in",
        ):
            with self.subTest(name=name):
                unit = self._unit(name)
                self.assertIn(
                    "EnvironmentFile=@CONFIG_ROOT@/backend.env",
                    unit,
                )
                self.assertIn(
                    "KOLIBRI_WORKER_EXPECTED_DATABASE_URL="
                    "sqlite:///@INSTALL_ROOT@/var/kolibri-v3.db",
                    unit,
                )
                self.assertIn(
                    "ReadWritePaths=@INSTALL_ROOT@/var ",
                    unit,
                )
                self.assertIn("ProtectSystem=strict", unit)
                self.assertIn("NoNewPrivileges=true", unit)
                self.assertIn("CapabilityBoundingSet=\n", unit)
                self.assertIn("RestartPreventExitStatus=73 75 78", unit)
                self.assertIn("PartOf=@BACKEND_SERVICE@", unit)
                self.assertIn(
                    "@INSTALL_ROOT@/libexec/worker_launcher.py",
                    unit,
                )

    def test_transport_credentials_are_systemd_credentials(self) -> None:
        product = self._unit(
            "kolibri-v3-product-run-worker.service.in"
        )
        provider = self._unit(
            "kolibri-v3-provider-enrollment-worker.service.in"
        )
        self.assertEqual(product.count("LoadCredential="), 2)
        self.assertEqual(provider.count("LoadCredential="), 2)
        self.assertNotIn("COMMAND_TOKEN=", product)
        self.assertNotIn("IDENTITY_HMAC_KEY=", product)
        self.assertNotIn("COMMAND_TOKEN=", provider)
        self.assertNotIn("IDENTITY_HMAC_KEY=", provider)

    def test_reconciliation_unit_cannot_mutate(self) -> None:
        unit = self._unit(
            "kolibri-v3-estimate-reconciliation-audit.service.in"
        )
        self.assertIn("Type=oneshot", unit)
        self.assertIn("PrivateNetwork=true", unit)
        self.assertIn("estimate-audit", unit)
        self.assertNotIn("--apply", unit)
        self.assertNotIn("[Install]", unit)


if __name__ == "__main__":
    unittest.main()
