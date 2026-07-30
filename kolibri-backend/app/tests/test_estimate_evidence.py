from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import pytest
from pydantic import ValidationError

from app.estimate_action import build_estimate_action, ensure_estimate_action
from app.estimate_evidence import PriceEvidenceRecord, attest_price_evidence
from app.project_schemas import PersistedEstimateAction


def _candidate(*, price: str = "15000", source_payload: bool = False) -> dict:
    position = {
        "code": "ФН-01",
        "name": "Устройство монолитной фундаментной плиты",
        "unit": "м2",
        "quantity": "100",
        "price": price,
        "sum": "1",
        "source": "https://fake.invalid/provider-claim",
    }
    if source_payload:
        position["price_evidence"] = [_evidence()]
    return {
        "title": "Смета: фундамент дома 100 м² — Лениногорск",
        "object_name": "Одноэтажный дом 100 м²",
        "region": "Лениногорск, Татарстан",
        "sections": [{"title": "Фундамент", "positions": [position]}],
        "price_sources": [_evidence()] if source_payload else [],
        "pricing_status": "verified",
        "estimate_status": "verified",
    }


def _evidence(
    *,
    verification: str = "source_backed",
    unit_price: str = "15000",
    unit: str = "м²",
    region: str = "Республика Татарстан",
    content_sha256: str = "a" * 64,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "position_code": "ФН-01",
        "source_id": "supplier-example-20260714-foundation",
        "url": "https://supplier.example/catalog/foundation-slab",
        "source_title": "Монолитная плита: датированное предложение поставщика",
        "source_type": "supplier_quote",
        "region": region,
        "observed_at": now.isoformat().replace("+00:00", "Z"),
        "price_date": now.date().isoformat(),
        "unit": unit,
        "vat_status": "included",
        "quote": "15 000 ₽/м², НДС включён",
        "unit_price": unit_price,
        "currency": "RUB",
        "content_sha256": content_sha256,
        "verification": verification,
    }


def _trusted_evidence(**kwargs) -> dict:
    return attest_price_evidence(_evidence(**kwargs))


def test_missing_provider_draft_is_needs_input_not_fixed_template():
    action = build_estimate_action(
        "Составь смету на одноэтажный дом 100 м² в Лениногорске, Татарстан"
    )

    data = action["data"]
    assert action["label"] == "Уточнить данные для сметы"
    assert data["estimate_status"] == "needs_input"
    assert data["pricing_status"] == "needs_input"
    assert data["sections"] == []
    assert data["price_sources"] == []
    assert data["totals"] == {
        "subtotal": "0.00",
        "overhead_amount": "0.00",
        "vat_amount": "0.00",
        "total": "0.00",
    }
    assert "Комплекс устройства фундамента" not in str(action)


def test_routes_exhausted_does_not_invent_plaster_technology():
    actions = ensure_estimate_action(
        [{"role": "user", "content": (
            "Составь сразу готовую смету на штукатурку стен 420 м² в Казани, "
            "отдельно работы и материалы, без уточняющих вопросов"
        )}],
        [],
    )

    assert len(actions) == 1
    data = actions[0]["data"]
    assert data["region"] == "Казань, Республика Татарстан"
    assert data["estimate_status"] == "preliminary"
    assert data["pricing_status"] == "preliminary"
    assert data["questions"] == []
    assert data["sections"]
    assert Decimal(data["totals"]["total"]) > 0
    assert data["price_sources"] == []


def test_routes_exhausted_does_not_invent_house_technology():
    actions = ensure_estimate_action(
        [{"role": "user", "content": (
            "Составь смету на строительство одноэтажного дома 234 м² в Лениногорске, "
            "кирпичный эконом-класса. Сам подбери, без уточняющих вопросов."
        )}],
        [],
    )

    assert len(actions) == 1
    action = actions[0]
    data = action["data"]
    assert data["region"] == "Лениногорск"
    assert action["label"] == "Открыть предварительную смету"
    assert data["estimate_status"] == "preliminary"
    assert data["pricing_status"] == "preliminary"
    assert data["questions"] == []
    assert data["sections"]
    assert Decimal(data["totals"]["total"]) > 0
    assert data["price_sources"] == []


def test_provider_estimate_with_empty_sections_is_fallbacked_to_professional_scope():
    actions = ensure_estimate_action(
        [{"role": "user", "content": (
            "Составь подробную смету на штукатурку стен 358 м² в Лениногорске"
        )}],
        [{
            "type": "create_estimate",
            "label": "Уточнить данные для сметы",
            "data": {
                "title": "Смета: штукатурка стен 358 м² — Лениногорск",
                "client": "",
                "object_name": "Штукатурка стен 358 м²",
                "region": "Лениногорск",
                "sections": [],
                "assumptions": ["временные"],
                "questions": ["Нужно уточнить"],
                "estimate_status": "needs_input",
                "pricing_status": "needs_input",
            },
        }],
    )

    assert len(actions) == 1
    data = actions[0]["data"]
    assert data["estimate_status"] in {"preliminary", "source_backed"}
    assert data["pricing_status"] in {"preliminary", "source_backed"}
    assert data["sections"], "Смета должна получить рабочий scope по fallback-правилу"
    assert data["questions"] == []


def test_provider_sections_are_preserved_and_totals_are_recalculated():
    candidate = _candidate()
    candidate["sections"].append(
        {
            "title": "Кровля",
            "positions": [
                {
                    "code": "КР-01",
                    "name": "Монтаж кровельного покрытия",
                    "unit": "м2",
                    "quantity": "130.5",
                    "price": "2450.25",
                    "sum": "999999999",
                }
            ],
        }
    )

    action = build_estimate_action("Составь смету", candidate)
    data = action["data"]
    positions = [position for section in data["sections"] for position in section["positions"]]

    assert [section["title"] for section in data["sections"]] == ["Фундамент", "Кровля"]
    assert [position["name"] for position in positions] == [
        "Устройство монолитной фундаментной плиты",
        "Монтаж кровельного покрытия",
    ]
    assert positions[0]["sum"] == "1500000.00"
    assert positions[1]["sum"] == "319757.63"
    assert data["totals"]["subtotal"] == "1819757.63"
    assert data["totals"]["total"] == "1819757.63"
    assert data["vat_rate"] == "0"
    assert data["pricing_status"] == "preliminary"


def test_zero_price_draft_is_retained_without_inventing_a_replacement_price():
    action = build_estimate_action("Составь смету", _candidate(price="0"))
    position = action["data"]["sections"][0]["positions"][0]

    assert position["price"] == "0"
    assert position["sum"] == "0.00"
    assert action["data"]["pricing_status"] == "needs_input"
    assert action["data"]["estimate_status"] == "needs_input"


def test_provider_claimed_sources_and_promotion_are_ignored():
    action = build_estimate_action("Составь смету", _candidate(source_payload=True))
    data = action["data"]
    position = data["sections"][0]["positions"][0]

    assert data["pricing_status"] == "preliminary"
    assert data["estimate_status"] == "preliminary"
    assert data["price_sources"] == []
    assert position["source"] == ""
    assert position["price_evidence"] == []


def test_trusted_source_promotes_only_to_source_backed():
    evidence = _trusted_evidence()
    action = build_estimate_action(
        "Составь смету",
        _candidate(),
        verified_evidence=[evidence],
    )
    data = action["data"]
    position = data["sections"][0]["positions"][0]

    assert data["pricing_status"] == "source_backed"
    assert data["estimate_status"] == "source_backed"
    assert data["scope_status"] == "unverified"
    assert position["source"] == evidence["url"]
    assert position["price_evidence"][0]["content_sha256"] == "a" * 64
    assert data["price_sources"] == position["price_evidence"]
    persisted = PersistedEstimateAction.model_validate(action)
    assert persisted.data.pricing_status == "preliminary"
    assert persisted.data.estimate_status == "preliminary"
    assert persisted.data.scope_status == "unverified"
    assert persisted.data.price_sources[0].attestation == evidence["attestation"]
    assert persisted.label == "Открыть предварительную смету"


def test_partial_source_backed_prices_open_preliminary_editor_without_fake_totals():
    candidate = _candidate()
    candidate["sections"][0]["positions"].append({
        "code": "UNKNOWN-02",
        "name": "Неисследованный дополнительный материал",
        "unit": "шт",
        "quantity": "3",
        "price": "0",
    })
    evidence = _trusted_evidence()

    action = build_estimate_action(
        "Составь смету",
        candidate,
        verified_evidence=[evidence],
    )
    data = action["data"]
    first, unknown = data["sections"][0]["positions"]

    assert action["label"] == "Открыть предварительную смету"
    assert data["pricing_status"] == "preliminary"
    assert data["estimate_status"] == "preliminary"
    assert first["price"] == "15000"
    assert first["price_evidence"][0]["url"] == evidence["url"]
    assert unknown["price"] == "0"
    assert unknown["sum"] == "0.00"
    assert unknown["price_evidence"] == []
    assert data["totals"]["total"] == "1500000.00"
    assert "строки без актуальной цены" in data["source_note"].casefold()
    assert any("в сумму не включены" in item.casefold() for item in data["assumptions"])

    persisted = PersistedEstimateAction.model_validate(action)
    assert persisted.data.pricing_status == "preliminary"
    assert persisted.data.estimate_status == "preliminary"
    assert persisted.label == "Открыть предварительную смету"


def test_federal_source_is_compatible_but_explicitly_flagged_as_non_local():
    evidence = _trusted_evidence(region="Россия")
    action = build_estimate_action(
        "Составь смету",
        _candidate(),
        verified_evidence=[evidence],
    )

    data = action["data"]
    assert data["pricing_status"] == "source_backed"
    assert data["price_sources"][0]["region"] == "Россия"
    assert data["region"] == "Лениногорск, Татарстан"
    assert data["evidence_issues"] == [
        {
            "code": "federal_price_scope",
            "position_code": "ФН-01",
            "message": (
                "Источник подтверждает федеральную цену или доставку по России, "
                "но не локальную цену населённого пункта."
            ),
        }
    ]


def test_moscow_oblast_source_is_not_compatible_with_moscow_city():
    candidate = _candidate()
    candidate["region"] = "Москва"
    evidence = _trusted_evidence(region="Московская область")

    action = build_estimate_action(
        "Составь смету в Москве",
        candidate,
        verified_evidence=[evidence],
    )

    assert action["data"]["price_sources"] == []
    assert action["data"]["evidence_issues"][0]["code"] == "region_mismatch"


def test_verified_estimate_requires_verified_price_and_scope():
    verified_record = _trusted_evidence(verification="verified")
    price_only = build_estimate_action(
        "Составь смету",
        _candidate(),
        verified_evidence=[verified_record],
    )
    fully_verified = build_estimate_action(
        "Составь смету",
        _candidate(),
        verified_evidence=[verified_record],
        scope_verified=True,
    )

    assert price_only["data"]["pricing_status"] == "verified"
    assert price_only["data"]["estimate_status"] == "source_backed"
    assert fully_verified["data"]["pricing_status"] == "verified"
    assert fully_verified["data"]["estimate_status"] == "verified"
    persisted = PersistedEstimateAction.model_validate(fully_verified)
    assert persisted.data.pricing_status == "preliminary"
    assert persisted.data.estimate_status == "preliminary"
    assert persisted.data.scope_status == "unverified"


@pytest.mark.parametrize(
    ("change", "issue_code"),
    [
        ({"unit_price": "14999"}, "price_mismatch"),
        ({"unit": "м³"}, "unit_mismatch"),
        ({"region": "Москва"}, "region_mismatch"),
        ({"content_sha256": "not-a-hash"}, "invalid_evidence"),
    ],
)
def test_mismatching_or_invalid_evidence_fails_closed(change: dict, issue_code: str):
    evidence = _evidence()
    evidence.update(change)
    if issue_code != "invalid_evidence":
        evidence = attest_price_evidence(evidence)
    action = build_estimate_action(
        "Составь смету",
        _candidate(),
        verified_evidence=[evidence],
    )

    assert action["data"]["pricing_status"] == "preliminary"
    assert action["data"]["price_sources"] == []
    assert action["data"]["evidence_issues"][0]["code"] == issue_code


def test_well_formed_but_unattested_evidence_cannot_self_promote():
    action = build_estimate_action(
        "Составь смету",
        _candidate(),
        verified_evidence=[_evidence(verification="verified")],
        scope_verified=True,
    )

    assert action["data"]["pricing_status"] == "preliminary"
    assert action["data"]["estimate_status"] == "preliminary"
    assert action["data"]["price_sources"] == []
    assert action["data"]["evidence_issues"][0]["code"] == "untrusted_evidence"


def test_evidence_contract_rejects_non_http_url_and_unknown_fields():
    invalid = _evidence()
    invalid["url"] = "file:///etc/passwd"
    invalid["provider_reasoning"] = "trust me"

    with pytest.raises(ValidationError):
        PriceEvidenceRecord.model_validate(invalid)


def test_persisted_schema_rejects_non_deterministic_totals_and_downgrades_fake_promotion():
    action = build_estimate_action("Составь смету", _candidate())
    action["data"]["totals"]["total"] = "1.00"

    with pytest.raises(ValidationError):
        PersistedEstimateAction.model_validate(action)

    fake_promotion = build_estimate_action("Составь смету", _candidate())
    fake_promotion["data"]["estimate_status"] = "verified"
    fake_promotion["data"]["pricing_status"] = "verified"
    fake_promotion["data"]["scope_status"] = "verified"
    normalized = PersistedEstimateAction.model_validate(fake_promotion)
    assert normalized.data.estimate_status == "preliminary"
    assert normalized.data.pricing_status == "preliminary"
    assert normalized.data.scope_status == "unverified"
    assert normalized.label == "Открыть предварительную смету"


def test_browser_forged_attestation_is_opaque_and_cannot_promote_message_metadata():
    action = build_estimate_action("Составь смету", _candidate())
    forged = _evidence(verification="verified")
    forged["attestation"] = "f" * 64
    position = action["data"]["sections"][0]["positions"][0]
    position["source"] = forged["url"]
    position["price_evidence"] = [forged]
    action["data"]["price_sources"] = [forged]
    action["data"]["estimate_status"] = "verified"
    action["data"]["pricing_status"] = "verified"
    action["data"]["scope_status"] = "verified"
    action["label"] = "Открыть проверенную смету"

    normalized = PersistedEstimateAction.model_validate(action)

    assert normalized.data.estimate_status == "preliminary"
    assert normalized.data.pricing_status == "preliminary"
    assert normalized.data.scope_status == "unverified"
    assert normalized.data.price_sources[0].attestation == "f" * 64
    assert normalized.label == "Открыть предварительную смету"


def test_decimal_calculation_has_no_binary_float_drift():
    candidate = _candidate(price="0.10")
    candidate["sections"][0]["positions"][0]["quantity"] = "0.30"
    action = build_estimate_action("Составь смету", candidate)

    assert Decimal(action["data"]["totals"]["subtotal"]) == Decimal("0.03")
    assert action["data"]["sections"][0]["positions"][0]["sum"] == "0.03"


def test_versioned_release_refuses_the_public_development_evidence_key(monkeypatch):
    monkeypatch.delenv("KOLIBRI_EVIDENCE_SIGNING_KEY", raising=False)
    monkeypatch.delenv("KOLIBRI_SESSION_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-p7-test")

    with pytest.raises(RuntimeError, match="estimate_evidence_signing_key_not_configured"):
        attest_price_evidence(_evidence())


def test_versioned_release_accepts_a_dedicated_evidence_key(monkeypatch):
    monkeypatch.setenv("KOLIBRI_RELEASE_ID", "kolibri-p7-test")
    monkeypatch.setenv("KOLIBRI_EVIDENCE_SIGNING_KEY", "e" * 64)

    record = attest_price_evidence(_evidence())

    assert len(record["attestation"]) == 64
