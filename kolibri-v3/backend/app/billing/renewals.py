"""One-shot executor for due T-Bank RebillId renewals.

Usable as a cron/systemd-timer step (`python -m app.billing.renewals`) or from
the owner endpoint `/v1/platform-admin/billing/renewals/run`. Each charge is
idempotent per subscription period, so overlapping runs are safe.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from ..config import Settings
from ..database import connect_database, initialize_database
from .config import TBankSettings
from .service import run_due_renewals
from .tbank import TBankGateway


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Charge due Kolibri subscription renewals via RebillId"
    )
    parser.add_argument("--limit", type=int, default=50)
    arguments = parser.parse_args()
    settings = Settings.from_env()
    billing = TBankSettings.from_env(runtime_environment=settings.environment)
    if not billing.enabled:
        print(json.dumps({"error": "billing_disabled"}))
        return 2
    gateway = TBankGateway(billing)
    initialize_database(settings.database_url)
    database = connect_database(settings.database_url)
    try:
        summary = run_due_renewals(database, gateway=gateway, limit=arguments.limit)
    finally:
        database.close()
    print(json.dumps(asdict(summary)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
