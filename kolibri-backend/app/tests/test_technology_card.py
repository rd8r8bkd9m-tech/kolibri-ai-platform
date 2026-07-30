from __future__ import annotations

from decimal import Decimal

import pytest

from app.estimate_action import ensure_estimate_action
from app.technology_card import (
    TechnologyCardError,
    interpret_estimate_candidate,
    prepare_estimate_candidate,
    validate_stored_technology_card,
)


def _card(*, quote: str, object_type: str, stage: str, resource_name: str, unit: str, quantity: str):
    return {
        "schema_version": "1.0",
        "title": f"Технологическая карта: {object_type}",
        "object_type": object_type,
        "scope": f"Полный комплекс: {stage}",
        "user_facts": [{"quote": quote, "meaning": "обязательное исходное ограничение"}],
        "assumptions": ["Неизвестные параметры приняты предварительно."],
        "exclusions": ["Работы за границей указанного объекта"],
        "stages": [{
            "sequence": 1,
            "name": stage,
            "result": "Этап завершён и принят по контрольным критериям",
            "operations": [{
                "sequence": 1,
                "name": f"Выполнение: {stage}",
                "method": "Работы выполняются последовательно по проекту и допускам производителя.",
                "prerequisites": ["Исходные данные и фронт работ подтверждены"],
                "quality_checks": ["Количество и результат проверены ответственным специалистом"],
                "safety_controls": ["Наряд-допуск и средства защиты по виду работ"],
                "resources": [
                    {
                        "kind": "work",
                        "code": "",
                        "name": resource_name,
                        "unit": unit,
                        "quantity": quantity,
                        "price": "1250.00",
                        "quantity_basis": f"из запроса пользователя: {quote}",
                        "procurement_query": "Проверить региональную ставку и доступность исполнителя",
                    },
                    {
                        "kind": "service",
                        "code": "",
                        "name": "Контроль качества и исполнительная документация",
                        "unit": "компл",
                        "quantity": "1",
                        "price": "15000.00",
                        "quantity_basis": "один комплект на объект",
                        "procurement_query": "Проверить стоимость услуги в регионе объекта",
                    },
                ],
            }],
        }],
    }


@pytest.mark.parametrize(
    ("prompt", "quote", "object_type", "stage", "resource", "unit", "quantity"),
    [
        (
            "Составь смету на строительство одноэтажного дома 123 м²",
            "одноэтажного дома 123 м²",
            "Одноэтажный жилой дом",
            "Строительно-монтажные работы",
            "Комплекс работ по технологической карте",
            "м²",
            "123",
        ),
        (
            "Составь смету на бурение водяной скважины глубиной 80 м",
            "водяной скважины глубиной 80 м",
            "Водяная скважина",
            "Бурение и обсадка",
            "Бурение ствола скважины",
            "м",
            "80",
        ),
    ],
)
def test_any_domain_is_interpreted_from_the_same_technology_contract(
    prompt, quote, object_type, stage, resource, unit, quantity
):
    action = ensure_estimate_action(
        [{"role": "user", "content": prompt}],
        [{
            "type": "create_estimate",
            "label": "draft",
            "data": {
                "title": f"Смета: {object_type}",
                "object_name": object_type,
                "technology_card": _card(
                    quote=quote,
                    object_type=object_type,
                    stage=stage,
                    resource_name=resource,
                    unit=unit,
                    quantity=quantity,
                ),
                # These rows must never bypass lineage from the card.
                "sections": [{"title": "Подменённый шаблон", "positions": []}],
            },
        }],
    )[0]

    data = action["data"]
    assert data["technology_card"]["content_sha256"]
    assert [section["title"] for section in data["sections"]] == [f"01. {stage}"]
    assert [position["name"] for position in data["sections"][0]["positions"]] == [
        resource,
        "Контроль качества и исполнительная документация",
    ]
    assert Decimal(data["totals"]["total"]) > 0
    assert all("Основание количества:" in position["comment"] for position in data["sections"][0]["positions"])


def test_card_omitting_an_explicit_measurement_is_rejected():
    prompt = "Составь смету на бурение скважины глубиной 80 м"
    candidate = {
        "title": "Смета",
        "technology_card": _card(
            quote="бурение скважины",
            object_type="Скважина",
            stage="Бурение",
            resource_name="Бурение",
            unit="м",
            quantity="50",
        ),
    }

    with pytest.raises(TechnologyCardError, match="measurement_omitted"):
        prepare_estimate_candidate(prompt, candidate)


def test_card_hash_detects_browser_side_mutation():
    prompt = "Составь смету на монтаж ограждения 40 м"
    candidate = prepare_estimate_candidate(
        prompt,
        {
            "title": "Ограждение",
            "technology_card": _card(
                quote="монтаж ограждения 40 м",
                object_type="Ограждение",
                stage="Монтаж",
                resource_name="Монтаж секций ограждения",
                unit="м",
                quantity="40",
            ),
        },
    )
    card = candidate["technology_card"]
    assert validate_stored_technology_card(card)["content_sha256"] == card["content_sha256"]
    card["scope"] = "Подменённый объём"
    with pytest.raises(TechnologyCardError, match="hash_mismatch"):
        validate_stored_technology_card(card)


def test_finished_solo_estimate_is_preserved_and_interpreted_without_domain_template():
    prompt = (
        "Составь смету на строительство одноэтажного дома 123 м² "
        "в Лениногорске, кирпичный, эконом-класс"
    )
    candidate = {
        "title": "Смета одноэтажного кирпичного дома 123 м²",
        "object_name": "Одноэтажный кирпичный дом",
        "region": "Лениногорск, Татарстан",
        "assumptions": ["Площадь 123 м² принята как общая площадь дома."],
        "sections": [
            {
                "title": "Нулевой цикл",
                "positions": [
                    {
                        "code": "SOLO-01",
                        "name": "Устройство монолитного фундамента по проекту",
                        "unit": "м³",
                        "quantity": "44.5",
                        "price": "14800.00",
                        "comment": "Объём из расчёта Solo по конструктивной схеме.",
                    }
                ],
            },
            {
                "title": "Кирпичная коробка одного этажа",
                "positions": [
                    {
                        "code": "SOLO-02",
                        "name": "Кладка наружных кирпичных стен одного этажа",
                        "unit": "м³",
                        "quantity": "81.2",
                        "price": "19250.00",
                        "comment": "Объём стен из готовой сметы Solo.",
                    }
                ],
            },
        ],
    }

    interpreted = interpret_estimate_candidate(prompt, candidate)

    assert interpreted["title"] == candidate["title"]
    assert interpreted["object_name"] == candidate["object_name"]
    assert interpreted["region"] == candidate["region"]
    assert [position["code"] for section in interpreted["sections"] for position in section["positions"]] == [
        "SOLO-01",
        "SOLO-02",
    ]
    assert [position["name"] for section in interpreted["sections"] for position in section["positions"]] == [
        "Устройство монолитного фундамента по проекту",
        "Кладка наружных кирпичных стен одного этажа",
    ]
    assert interpreted["technology_card"]["content_sha256"]
    assert interpreted["technology_card"]["user_facts"][0]["quote"] == prompt
