#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description='Vista SQLite and artifact backup verification')
    parser.add_argument('--database', required=True)
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--output', default='var/release-check/backup')
    parser.add_argument('--report', default='var/release-check/backup-restore-check.json')
    args = parser.parse_args()
    source_db = Path(args.database)
    source_artifacts = Path(args.artifacts)
    output = Path(args.output)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    backup_db = output / 'vista.db'
    with sqlite3.connect(source_db) as src, sqlite3.connect(backup_db) as dst:
        src.backup(dst)
    backup_artifacts = output / 'artifacts'
    if source_artifacts.exists():
        shutil.copytree(source_artifacts, backup_artifacts)
    with sqlite3.connect(backup_db) as check:
        integrity = check.execute('PRAGMA integrity_check').fetchone()[0]
        estimates = check.execute('SELECT COUNT(*) FROM estimates').fetchone()[0]
        artifacts = check.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]
    files = []
    if backup_artifacts.exists():
        for path in sorted(p for p in backup_artifacts.rglob('*') if p.is_file()):
            files.append({'path': str(path.relative_to(backup_artifacts)), 'size': path.stat().st_size, 'sha256': digest(path)})
    report = {
        'status': 'passed' if integrity == 'ok' else 'failed',
        'integrity': integrity,
        'database_sha256': digest(backup_db),
        'estimates': estimates,
        'artifact_rows': artifacts,
        'artifact_files': files,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if report['status'] != 'passed' or estimates < 1 or artifacts < 1 or not files:
        raise SystemExit(f'backup verification failed: {report}')
    print(f"ok: Vista backup/restore verification passed; report={report_path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
