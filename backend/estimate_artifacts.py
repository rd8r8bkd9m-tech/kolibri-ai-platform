"""Ephemeral editable estimates and immutable PDF artifacts for the public Shell.

The provider may propose scope, quantities, prices and provenance.  This
module revalidates the typed estimate, recalculates every monetary value with
the deterministic minor-unit engine, persists an optimistic-lock revision and
materializes a content-addressed PDF.  Session tokens and provider credentials
never enter the estimate or artifact records.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from artifact_runtime import EstimateSpec, deterministic_estimate
from data_paths import DATA_DIR, DB_PATH


ARTIFACT_SCHEMA = "kolibri.estimate-artifact.v1"
ESTIMATE_SCHEMA = "kolibri.editable-estimate.v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_FONT_LOCK = threading.Lock()
_FONTS: tuple[str, str] | None = None

_REGULAR_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)
_BOLD_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)
_CATEGORY_LABELS = {
    "labor": "Работы",
    "material": "Материалы",
    "equipment": "Оборудование",
    "service": "Услуги",
    "other": "Прочее",
}


class EstimateArtifactError(RuntimeError):
    pass


class EstimateVersionConflict(EstimateArtifactError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: bytes | str) -> str:
    body = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(body).hexdigest()


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _font_pair() -> tuple[str, str]:
    global _FONTS
    if _FONTS is not None:
        return _FONTS
    with _FONT_LOCK:
        if _FONTS is not None:
            return _FONTS
        regular_path = next((Path(path) for path in _REGULAR_FONTS if Path(path).is_file()), None)
        bold_path = next((Path(path) for path in _BOLD_FONTS if Path(path).is_file()), None)
        if regular_path is None:
            raise EstimateArtifactError("cyrillic_pdf_font_missing")
        regular_name = "KolibriEstimateRegular"
        bold_name = "KolibriEstimateBold" if bold_path else regular_name
        pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
        if bold_path:
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
        _FONTS = (regular_name, bold_name)
        return _FONTS


def _styles() -> dict[str, ParagraphStyle]:
    regular, bold = _font_pair()
    base = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "KolibriEstimateEyebrow", parent=base["Normal"], fontName=bold,
            fontSize=7.5, leading=10, textColor=colors.HexColor("#078B9A"),
            uppercase=True, spaceAfter=3,
        ),
        "title": ParagraphStyle(
            "KolibriEstimateTitle", parent=base["Title"], fontName=bold,
            fontSize=20, leading=24, textColor=colors.HexColor("#102126"),
            alignment=TA_LEFT, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "KolibriEstimateH2", parent=base["Heading2"], fontName=bold,
            fontSize=11, leading=14, textColor=colors.HexColor("#102126"),
            spaceBefore=8, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "KolibriEstimateBody", parent=base["BodyText"], fontName=regular,
            fontSize=8.5, leading=12, textColor=colors.HexColor("#28373B"),
        ),
        "small": ParagraphStyle(
            "KolibriEstimateSmall", parent=base["BodyText"], fontName=regular,
            fontSize=7.2, leading=9.5, textColor=colors.HexColor("#4D5B60"),
        ),
        "small_bold": ParagraphStyle(
            "KolibriEstimateSmallBold", parent=base["BodyText"], fontName=bold,
            fontSize=7.2, leading=9.5, textColor=colors.HexColor("#28373B"),
        ),
        "money": ParagraphStyle(
            "KolibriEstimateMoney", parent=base["BodyText"], fontName=bold,
            fontSize=9, leading=12, textColor=colors.HexColor("#102126"),
            alignment=TA_RIGHT,
        ),
    }


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value or "")), style)


def _money(minor: int, minor_unit: int, currency: str) -> str:
    amount = Decimal(minor) / (Decimal(10) ** minor_unit)
    formatted = f"{amount:,.{minor_unit}f}".replace(",", " ").replace(".", ",")
    return f"{formatted} {currency}"


def _rate(bps: int) -> str:
    return f"{Decimal(bps) / Decimal(100):.2f}".replace(".", ",") + "%"


def _page_footer(calculation_sha256: str):
    def draw(canvas, doc):
        regular, bold = _font_pair()
        width, _ = A4
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D8E2E4"))
        canvas.setLineWidth(0.4)
        canvas.line(15 * mm, 13 * mm, width - 15 * mm, 13 * mm)
        canvas.setFont(bold, 7)
        canvas.setFillColor(colors.HexColor("#078B9A"))
        canvas.drawString(15 * mm, 8.5 * mm, "KOLIBRI AI")
        canvas.setFont(regular, 6.5)
        canvas.setFillColor(colors.HexColor("#657176"))
        canvas.drawCentredString(width / 2, 8.5 * mm, f"Расчёт {calculation_sha256[:16]}")
        canvas.drawRightString(width - 15 * mm, 8.5 * mm, f"Страница {doc.page}")
        canvas.restoreState()
    return draw


def generate_estimate_pdf(
    spec: EstimateSpec,
    calculation: dict[str, Any],
    output_path: str | Path,
    *,
    estimate_id: str,
    version: int,
) -> Path:
    """Generate a polished PDF from a validated deterministic calculation."""

    expected = deterministic_estimate(spec)
    if expected != calculation:
        raise EstimateArtifactError("estimate_calculation_mismatch")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    regular, bold = _font_pair()
    calculation_sha = str(calculation["calculation_sha256"])
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=18 * mm,
        title=spec.title, author="Kolibri AI",
        subject=f"Смета {estimate_id}, версия {version}",
    )
    story: list[Any] = [
        _p("KOLIBRI AI / СМЕТА", styles["eyebrow"]),
        _p(spec.title, styles["title"]),
    ]
    meta_rows = [
        [_p("Регион", styles["small_bold"]), _p(spec.region, styles["small"])],
        [_p("Версия", styles["small_bold"]), _p(str(version), styles["small"])],
        [_p("Валюта", styles["small_bold"]), _p(spec.currency, styles["small"])],
        [_p("Источник цен", styles["small_bold"]), _p(spec.source_summary, styles["small"])],
    ]
    if spec.client_name:
        meta_rows.insert(0, [_p("Клиент", styles["small_bold"]), _p(spec.client_name, styles["small"])])
    if spec.object_name or spec.object_address:
        value = " / ".join(item for item in (spec.object_name, spec.object_address) if item)
        meta_rows.insert(1, [_p("Объект", styles["small_bold"]), _p(value, styles["small"])])
    meta = Table(meta_rows, colWidths=[31 * mm, 149 * mm], hAlign="LEFT")
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E5F8FA")),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C5D5D8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8E2E4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([meta, Spacer(1, 7 * mm)])

    calculated_lines = {item["id"]: item for item in calculation["lines"]}
    sections: dict[str, list[Any]] = defaultdict(list)
    for line in spec.lines:
        sections[line.section].append(line)
    line_number = 0
    for section, lines in sections.items():
        story.append(_p(section, styles["h2"]))
        rows: list[list[Any]] = [[
            _p("№", styles["small_bold"]),
            _p("Позиция", styles["small_bold"]),
            _p("Тип", styles["small_bold"]),
            _p("Ед.", styles["small_bold"]),
            _p("Кол-во", styles["small_bold"]),
            _p("Цена", styles["small_bold"]),
            _p("Сумма", styles["small_bold"]),
        ]]
        for line in lines:
            line_number += 1
            result = calculated_lines[line.id]
            source = line.provenance.source_ref or line.provenance.source
            description = line.description
            if source:
                description += f"<br/><font size='6.5' color='#657176'>Источник: {escape(source)}</font>"
            rows.append([
                _p(line_number, styles["small"]),
                Paragraph(escape(line.description) + (
                    f"<br/><font size='6.5' color='#657176'>Источник: {escape(source)}</font>"
                    if source else ""
                ), styles["small"]),
                _p(_CATEGORY_LABELS.get(line.category, "Прочее"), styles["small"]),
                _p(line.unit, styles["small"]),
                _p(result["quantity"], styles["small"]),
                _p(_money(line.unit_price_minor, spec.minor_unit, spec.currency), styles["small"]),
                _p(_money(result["line_total_minor"], spec.minor_unit, spec.currency), styles["small_bold"]),
            ])
        table = LongTable(
            rows,
            colWidths=[8 * mm, 59 * mm, 24 * mm, 13 * mm, 18 * mm, 27 * mm, 31 * mm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F5")),
            ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C5D5D8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E2E4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ]))
        story.extend([table, Spacer(1, 3 * mm)])

    totals = calculation["totals"]
    summary_rows: list[list[Any]] = []
    for category, amount in totals["categories_minor"].items():
        summary_rows.append([
            _p(_CATEGORY_LABELS.get(category, category), styles["body"]),
            _p(_money(amount, spec.minor_unit, spec.currency), styles["money"]),
        ])
    if calculation["overhead_rate_bps"]:
        summary_rows.append([
            _p(f"Накладные, {_rate(calculation['overhead_rate_bps'])}", styles["body"]),
            _p(_money(totals["overhead_minor"], spec.minor_unit, spec.currency), styles["money"]),
        ])
    if calculation["tax_rate_bps"]:
        summary_rows.append([
            _p(f"Налог, {_rate(calculation['tax_rate_bps'])}", styles["body"]),
            _p(_money(totals["tax_minor"], spec.minor_unit, spec.currency), styles["money"]),
        ])
    summary_rows.append([
        _p("Итого", styles["small_bold"]),
        _p(_money(totals["grand_total_minor"], spec.minor_unit, spec.currency), styles["money"]),
    ])
    summary = Table(summary_rows, colWidths=[105 * mm, 75 * mm], hAlign="RIGHT")
    summary.setStyle(TableStyle([
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#17B7C7")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E5F8FA")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([Spacer(1, 3 * mm), summary])

    closing: list[Any] = []
    if spec.assumptions or spec.questions:
        closing.extend([Spacer(1, 3 * mm), _p("Допущения и вопросы", styles["h2"])])
        assumptions = "<br/>".join(
            f"{index}. {escape(item)}" for index, item in enumerate(spec.assumptions, 1)
        ) or "Нет"
        questions = "<br/>".join(
            f"{index}. {escape(item)}" for index, item in enumerate(spec.questions, 1)
        ) or "Нет"
        notes = Table([
            [_p("Допущения", styles["small_bold"]), _p("Нужно уточнить", styles["small_bold"])],
            [Paragraph(assumptions, styles["small"]), Paragraph(questions, styles["small"])],
        ], colWidths=[90 * mm, 90 * mm])
        notes.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F5")),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#C5D5D8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E2E4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        closing.append(notes)

    closing.extend([
        Spacer(1, 5 * mm),
        _p(
            "Денежные итоги рассчитаны движком kolibri.decimal-minor-unit.v1. "
            "Модель предлагает состав, количество и цены, но не определяет итоговую сумму.",
            styles["small"],
        ),
        _p(f"Estimate ID: {estimate_id} / Version: {version}", styles["small"]),
        _p(f"Calculation SHA-256: {calculation_sha}", styles["small"]),
    ])
    story.append(KeepTogether(closing))
    footer = _page_footer(calculation_sha)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    if not path.is_file() or path.stat().st_size < 1_000:
        raise EstimateArtifactError("estimate_pdf_not_materialized")
    return path


class EstimateArtifactStore:
    def __init__(self, db_path: str | Path, artifact_root: str | Path):
        self.db_path = str(db_path)
        self.artifact_root = Path(artifact_root).expanduser().resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS public_estimates (
                    estimate_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    source_response_id TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_public_estimates_session
                    ON public_estimates(session_id, updated_at);
                CREATE TABLE IF NOT EXISTS public_estimate_versions (
                    version_id TEXT PRIMARY KEY,
                    estimate_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    spec_json TEXT NOT NULL,
                    calculation_json TEXT NOT NULL,
                    spec_sha256 TEXT NOT NULL,
                    calculation_sha256 TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(estimate_id, version),
                    UNIQUE(session_id, response_id),
                    FOREIGN KEY(estimate_id) REFERENCES public_estimates(estimate_id)
                );
                CREATE TABLE IF NOT EXISTS public_estimate_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    estimate_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    estimate_version INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    reference_sha256 TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY(estimate_id) REFERENCES public_estimates(estimate_id),
                    FOREIGN KEY(version_id) REFERENCES public_estimate_versions(version_id)
                );
                CREATE INDEX IF NOT EXISTS idx_public_estimate_artifacts_session
                    ON public_estimate_artifacts(session_id, created_at);
                """
            )

    def _cleanup(self, connection: sqlite3.Connection, now: float) -> None:
        expired = connection.execute(
            "SELECT DISTINCT storage_path FROM public_estimate_artifacts WHERE expires_at <= ?",
            (now,),
        ).fetchall()
        connection.execute("DELETE FROM public_estimate_artifacts WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM public_estimate_versions WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM public_estimates WHERE expires_at <= ?", (now,))
        for row in expired:
            storage_path = str(row["storage_path"])
            remaining = connection.execute(
                "SELECT 1 FROM public_estimate_artifacts WHERE storage_path = ? LIMIT 1",
                (storage_path,),
            ).fetchone()
            if remaining is None:
                path = Path(storage_path).resolve()
                if path.is_relative_to(self.artifact_root):
                    path.unlink(missing_ok=True)

    @staticmethod
    def _artifact_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        get = row.__getitem__
        return {
            "id": get("artifact_id"),
            "schema_version": ARTIFACT_SCHEMA,
            "kind": "pdf",
            "name": f"estimate-v{get('estimate_version')}.pdf",
            "locator": f"/v1/public/estimate-artifacts/{get('artifact_id')}/content",
            "media_type": get("media_type"),
            "reference_sha256": get("reference_sha256"),
            "content_sha256": get("content_sha256"),
            "size_bytes": int(get("size_bytes")),
            "deliverable_type": "pdf",
            "evidence_binding_sha256": get("binding_sha256"),
            "status": "materialized",
            "immutable": True,
            "estimate_id": get("estimate_id"),
            "estimate_version": int(get("estimate_version")),
        }

    def _version_public(
        self,
        version_row: sqlite3.Row,
        artifact_row: sqlite3.Row | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": ESTIMATE_SCHEMA,
            "id": version_row["estimate_id"],
            "version_id": version_row["version_id"],
            "version": int(version_row["version"]),
            "project_id": version_row["project_id"],
            "response_id": version_row["response_id"],
            "state": "saved",
            "spec": json.loads(version_row["spec_json"]),
            "calculation": json.loads(version_row["calculation_json"]),
            "spec_sha256": version_row["spec_sha256"],
            "calculation_sha256": version_row["calculation_sha256"],
            "artifacts": [self._artifact_public(artifact_row)] if artifact_row else [],
            "created_at": float(version_row["created_at"]),
        }

    def persist(
        self,
        *,
        session: dict[str, Any],
        response_id: str,
        spec: EstimateSpec,
        calculation: dict[str, Any],
        estimate_id: str | None,
        base_version: int | None,
        materialize_pdf: bool,
    ) -> dict[str, Any]:
        expected = deterministic_estimate(spec)
        if calculation != expected:
            raise EstimateArtifactError("estimate_calculation_mismatch")
        now = time.time()
        expires_at = float(session["expires_at"])
        spec_json = _canonical_json(spec.model_dump(mode="json"))
        calculation_json = _canonical_json(calculation)
        spec_sha = _sha(spec_json)
        calculation_sha = str(calculation["calculation_sha256"])
        if not _SHA256.fullmatch(calculation_sha):
            raise EstimateArtifactError("estimate_calculation_hash_invalid")

        with self._lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            existing_version = connection.execute(
                """SELECT * FROM public_estimate_versions
                   WHERE session_id = ? AND response_id = ?""",
                (session["id"], response_id),
            ).fetchone()
            if existing_version is not None:
                if existing_version["spec_sha256"] != spec_sha:
                    raise EstimateVersionConflict("response_id_reused_with_different_estimate")
                artifact = connection.execute(
                    "SELECT * FROM public_estimate_artifacts WHERE version_id = ?",
                    (existing_version["version_id"],),
                ).fetchone()
                return self._version_public(existing_version, artifact)

            if estimate_id:
                estimate = connection.execute(
                    """SELECT * FROM public_estimates
                       WHERE estimate_id = ? AND session_id = ? AND project_id = ?""",
                    (estimate_id, session["id"], session["project_id"]),
                ).fetchone()
                if estimate is None:
                    raise EstimateVersionConflict("estimate_not_found_in_session")
                current_version = int(estimate["current_version"])
                if base_version is None or base_version != current_version:
                    raise EstimateVersionConflict("estimate_version_conflict")
                version = current_version + 1
            else:
                estimate_id = _opaque_id("estimate")
                version = 1
                connection.execute(
                    """INSERT INTO public_estimates
                       (estimate_id, session_id, project_id, source_response_id,
                        current_version, created_at, updated_at, expires_at)
                       VALUES (?, ?, ?, ?, 0, ?, ?, ?)""",
                    (
                        estimate_id, session["id"], session["project_id"], response_id,
                        now, now, expires_at,
                    ),
                )
            version_id = _opaque_id("estimate_version")
            connection.execute(
                """INSERT INTO public_estimate_versions
                   (version_id, estimate_id, session_id, project_id, response_id,
                    version, spec_json, calculation_json, spec_sha256,
                    calculation_sha256, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id, estimate_id, session["id"], session["project_id"],
                    response_id, version, spec_json, calculation_json, spec_sha,
                    calculation_sha, now, expires_at,
                ),
            )
            artifact_row: sqlite3.Row | None = None
            if materialize_pdf:
                temporary = self.artifact_root / f".{uuid.uuid4().hex}.pdf"
                try:
                    generate_estimate_pdf(
                        spec, calculation, temporary,
                        estimate_id=estimate_id, version=version,
                    )
                    content = temporary.read_bytes()
                    content_sha = _sha(content)
                    storage_path = self.artifact_root / f"{content_sha}.pdf"
                    if storage_path.exists():
                        temporary.unlink(missing_ok=True)
                    else:
                        os.replace(temporary, storage_path)
                        storage_path.chmod(0o444)
                    artifact_id = _opaque_id("artifact")
                    locator = f"/v1/public/estimate-artifacts/{artifact_id}/content"
                    binding_payload = {
                        "schema_version": ARTIFACT_SCHEMA,
                        "session_id": session["id"],
                        "project_id": session["project_id"],
                        "response_id": response_id,
                        "estimate_id": estimate_id,
                        "estimate_version": version,
                        "version_id": version_id,
                        "spec_sha256": spec_sha,
                        "calculation_sha256": calculation_sha,
                        "content_sha256": content_sha,
                        "size_bytes": len(content),
                    }
                    binding_sha = _sha(_canonical_json(binding_payload))
                    reference_sha = _sha(_canonical_json({
                        "artifact_id": artifact_id,
                        "locator": locator,
                        "content_sha256": content_sha,
                        "binding_sha256": binding_sha,
                    }))
                    connection.execute(
                        """INSERT INTO public_estimate_artifacts
                           (artifact_id, estimate_id, version_id, session_id, project_id,
                            response_id, estimate_version, media_type, content_sha256,
                            reference_sha256, binding_sha256, size_bytes, storage_path,
                            created_at, expires_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'application/pdf', ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            artifact_id, estimate_id, version_id, session["id"],
                            session["project_id"], response_id, version, content_sha,
                            reference_sha, binding_sha, len(content), str(storage_path),
                            now, expires_at,
                        ),
                    )
                    artifact_row = connection.execute(
                        "SELECT * FROM public_estimate_artifacts WHERE artifact_id = ?",
                        (artifact_id,),
                    ).fetchone()
                finally:
                    temporary.unlink(missing_ok=True)
            connection.execute(
                """UPDATE public_estimates
                   SET current_version = ?, updated_at = ?, expires_at = ?
                   WHERE estimate_id = ?""",
                (version, now, expires_at, estimate_id),
            )
            version_row = connection.execute(
                "SELECT * FROM public_estimate_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            assert version_row is not None
            return self._version_public(version_row, artifact_row)

    def get_estimate(self, session_id: str, estimate_id: str) -> dict[str, Any] | None:
        now = time.time()
        with self._lock, self.connect() as connection:
            self._cleanup(connection, now)
            estimate = connection.execute(
                """SELECT * FROM public_estimates
                   WHERE estimate_id = ? AND session_id = ? AND expires_at > ?""",
                (estimate_id, session_id, now),
            ).fetchone()
            if estimate is None:
                return None
            version = connection.execute(
                """SELECT * FROM public_estimate_versions
                   WHERE estimate_id = ? AND version = ?""",
                (estimate_id, estimate["current_version"]),
            ).fetchone()
            artifact = connection.execute(
                "SELECT * FROM public_estimate_artifacts WHERE version_id = ?",
                (version["version_id"],),
            ).fetchone()
        return self._version_public(version, artifact)

    def list_versions(self, session_id: str, estimate_id: str) -> list[dict[str, Any]] | None:
        now = time.time()
        with self._lock, self.connect() as connection:
            self._cleanup(connection, now)
            owner = connection.execute(
                "SELECT 1 FROM public_estimates WHERE estimate_id = ? AND session_id = ?",
                (estimate_id, session_id),
            ).fetchone()
            if owner is None:
                return None
            versions = connection.execute(
                """SELECT * FROM public_estimate_versions
                   WHERE estimate_id = ? ORDER BY version DESC""",
                (estimate_id,),
            ).fetchall()
            result = []
            for version in versions:
                artifact = connection.execute(
                    "SELECT * FROM public_estimate_artifacts WHERE version_id = ?",
                    (version["version_id"],),
                ).fetchone()
                result.append(self._version_public(version, artifact))
        return result

    def artifact_content(self, session_id: str, artifact_id: str) -> tuple[dict[str, Any], bytes] | None:
        now = time.time()
        with self._lock, self.connect() as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT * FROM public_estimate_artifacts
                   WHERE artifact_id = ? AND session_id = ? AND expires_at > ?""",
                (artifact_id, session_id, now),
            ).fetchone()
        if row is None:
            return None
        path = Path(row["storage_path"]).resolve()
        if not path.is_relative_to(self.artifact_root) or not path.is_file():
            raise EstimateArtifactError("estimate_artifact_storage_boundary_violation")
        content = path.read_bytes()
        if len(content) != int(row["size_bytes"]) or _sha(content) != row["content_sha256"]:
            raise EstimateArtifactError("estimate_artifact_integrity_failed")
        return self._artifact_public(row), content


_STORE = EstimateArtifactStore(
    DB_PATH,
    os.environ.get(
        "KOLIBRI_ESTIMATE_ARTIFACT_ROOT",
        str(DATA_DIR / "artifacts" / "estimates"),
    ),
)


def configure_estimate_artifact_store(
    db_path: str | Path,
    artifact_root: str | Path,
) -> EstimateArtifactStore:
    global _STORE
    _STORE = EstimateArtifactStore(db_path, artifact_root)
    return _STORE


def get_estimate_artifact_store() -> EstimateArtifactStore:
    return _STORE


def materialize_public_estimate_task(
    *,
    session: dict[str, Any],
    response_id: str,
    task: dict[str, Any],
    request_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a verified estimate result and attach only real PDF evidence.

    Provider proposals retain their content-bound provider/verifier gate.  A
    local assumption fallback is accepted only after its engine/spec/calculation
    binding is independently recomputed by ``vertical_tasks``.  The latter
    never upgrades ``provider_verified`` to true.
    """

    if task.get("intent") != "estimate":
        return task
    execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    provider_verified = (
        execution.get("provider_verified") is True
        and execution.get("status") == "completed"
    )
    engine_verified = False
    if not provider_verified:
        # Local import avoids making the estimate schema module depend on the
        # persistence layer while still sharing one proof verifier.
        from vertical_tasks import verified_deterministic_estimate_fallback

        engine_verified = verified_deterministic_estimate_fallback(task)
    if not (provider_verified or engine_verified):
        return task
    if result.get("type") != "deterministic_estimate":
        return task
    spec = EstimateSpec.model_validate(result.get("estimate"))
    calculation = result.get("calculation")
    if not isinstance(calculation, dict):
        raise EstimateArtifactError("estimate_calculation_missing")
    metadata = request_metadata if isinstance(request_metadata, dict) else {}
    estimate_id = metadata.get("estimate_id")
    if estimate_id is not None and not isinstance(estimate_id, str):
        raise EstimateVersionConflict("estimate_id_invalid")
    base_version = metadata.get("estimate_base_version")
    if base_version is not None and (not isinstance(base_version, int) or isinstance(base_version, bool)):
        raise EstimateVersionConflict("estimate_base_version_invalid")
    requested = task.get("artifact_delivery", {}).get("requested", [])
    materialize_pdf = "pdf" in requested
    persisted = _STORE.persist(
        session=session,
        response_id=response_id,
        spec=spec,
        calculation=calculation,
        estimate_id=estimate_id,
        base_version=base_version,
        materialize_pdf=materialize_pdf,
    )
    artifacts = list(task.get("artifacts") or [])
    artifacts.extend(persisted["artifacts"])
    delivered = sorted({str(item.get("deliverable_type")) for item in artifacts})
    missing = [item for item in requested if item not in delivered]
    return {
        **task,
        "status": "completed" if not missing else "incomplete",
        "result": {
            **result,
            "estimate": persisted["spec"],
            "calculation": persisted["calculation"],
        },
        "persistence": {
            "schema_version": ESTIMATE_SCHEMA,
            "estimate_id": persisted["id"],
            "version_id": persisted["version_id"],
            "version": persisted["version"],
            "state": "saved",
            "spec_sha256": persisted["spec_sha256"],
            "calculation_sha256": persisted["calculation_sha256"],
        },
        "artifacts": artifacts,
        "artifact_delivery": {
            "required": bool(requested),
            "status": (
                "not_required" if not requested
                else "materialized" if not missing
                else "not_materialized"
            ),
            "requested": requested,
            "delivered": delivered,
            "missing": missing,
            "count": len(artifacts),
        },
    }
