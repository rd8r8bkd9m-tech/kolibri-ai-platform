from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from app.chat.service import storage_client_run_id
from app.direct_model_runtime import (
    GET_WEATHER_TOOL,
    _history,
    _try_local_conversational_answer,
    _turn_from_decision,
    _validated_weather_tool_call,
)
from app.product_widgets import (
    deterministic_house_estimate_proposal,
    has_estimate_scope_input,
    is_estimate_generation_prompt,
    is_estimate_revision_prompt,
)
from app.weather_service import _location_candidates, try_parse_weather_query


def test_model_decision_selects_weather_tool_without_city_allowlist() -> None:
    turn = _turn_from_decision(
        json.dumps(
            {
                "type": "tool",
                "text": "",
                "toolName": "get_weather",
                "location": "Рейкьявик",
                "forecastDays": 4,
            },
            ensure_ascii=False,
        )
    )

    assert turn.text is None
    assert turn.tool_call is not None
    assert turn.tool_call.name == "get_weather"
    assert turn.tool_call.arguments == {
        "location": "Рейкьявик",
        "forecastDays": 4,
    }


def test_openai_style_tool_call_arguments_are_strictly_validated() -> None:
    call = _validated_weather_tool_call(
        '{"location":"Антананариву","forecastDays":3}'
    )

    assert call.name == "get_weather"
    assert call.arguments["location"] == "Антананариву"
    assert call.arguments["forecastDays"] == 3

    parameters = GET_WEATHER_TOOL["function"]["parameters"]
    assert parameters["additionalProperties"] is False
    assert parameters["required"] == ["location", "forecastDays"]


def test_regular_model_decision_remains_a_text_answer() -> None:
    turn = _turn_from_decision(
        json.dumps(
            {
                "type": "answer",
                "text": "Обычный ответ.",
                "toolName": "",
                "location": "",
                "forecastDays": 0,
            },
            ensure_ascii=False,
        )
    )

    assert turn.text == "Обычный ответ."
    assert turn.tool_call is None




def test_greeting_capabilities_and_math_are_local_context_breakers() -> None:
    assert _try_local_conversational_answer("567+678") == "1245"
    answer = _try_local_conversational_answer("привет что умеешь?")
    assert answer is not None
    assert "Привет" in answer
    assert "смет" in answer
    assert "Открыта редактируемая смета" not in answer
    assert "Подготовлены технологическая карта" not in answer


def test_local_context_breakers_do_not_match_estimate_generation() -> None:
    for prompt in ("привет", "привет что умеешь?", "4+6", "567+678"):
        assert not is_estimate_generation_prompt(prompt)

def test_explicit_weather_queries_use_a_city_agnostic_fast_path() -> None:
    query = try_parse_weather_query(
        "Стоит ли брать зонт в Зеленограде сегодня?"
    )
    assert query is not None
    assert query.location == "Зеленограде"
    assert query.forecast_days == 5

    forecast = try_parse_weather_query(
        "Покажи прогноз на неделю для Нижнего Новгорода"
    )
    assert forecast is not None
    assert forecast.location == "Нижнего Новгорода"
    assert forecast.forecast_days == 7


def test_weather_fast_path_defers_ambiguous_text_to_the_model() -> None:
    assert try_parse_weather_query("Как погода влияет на бетон?") is None
    assert try_parse_weather_query("Подготовь смету в Казани") is None


def test_scope_bearing_estimate_prompt_enters_deterministic_engine_path() -> None:
    assert is_estimate_generation_prompt(
        "358 м² механизированной штукатурки, слой 15 мм, "
        "Республика Татарстан. Сначала технологическая карта, "
        "затем детерминированная смета с источниками цен."
    )
    assert is_estimate_generation_prompt(
        "Ремонт ванной 6 м2 — нужна смета"
    )


def test_interactive_estimate_command_opens_current_document() -> None:
    prompt = "Интерактивную смету составь"
    assert is_estimate_generation_prompt(prompt)
    assert not has_estimate_scope_input(prompt)
    assert has_estimate_scope_input(
        "Составь смету дома 38 м²: фундамент, стены и кровля"
    )


def test_estimate_navigation_prompt_does_not_start_a_new_calculation() -> None:
    assert not is_estimate_generation_prompt("Где моя последняя смета?")
    assert not is_estimate_generation_prompt("Открой смету")


def test_estimate_revision_is_detected_without_the_word_estimate() -> None:
    assert is_estimate_revision_prompt("Мягкая кровля должна быть на крыше")
    assert is_estimate_revision_prompt("Добавь в смету позицию доставки")
    assert is_estimate_revision_prompt("Площадь изменилась на 100 м²")
    assert not is_estimate_revision_prompt("Расскажи, что такое мягкая кровля")


def test_landscape_revision_is_detected() -> None:
    assert is_estimate_revision_prompt("добавь благоустройство")
    assert is_estimate_revision_prompt("Добавь в смету благоустройство")
    assert is_estimate_revision_prompt("Нужно добавить забор и газон")
    assert is_estimate_revision_prompt("Добавь отмостку и ливневую канализацию")
    assert not is_estimate_revision_prompt("Что такое благоустройство?")


def test_add_to_estimate_word_order_is_matched() -> None:
    from app.product_widgets import ESTIMATE_ADD_ITEM

    match = ESTIMATE_ADD_ITEM.search("в смету добавь позицию доставки")
    assert match is not None
    assert (match.group(1) or match.group(2)) is not None

    match2 = ESTIMATE_ADD_ITEM.search("добавь в смету позицию доставки")
    assert match2 is not None


def test_landscape_rows_count_and_section() -> None:
    from app.product_widgets import LANDSCAPE_SECTION_TITLE, _default_landscape_rows

    rows = _default_landscape_rows(None)
    assert len(rows) == 7
    assert all(r["section"] == LANDSCAPE_SECTION_TITLE for r in rows)
    descriptions = [r["description"] for r in rows]
    assert any("Отмостка" in d for d in descriptions)
    assert any("Забор" in d for d in descriptions)
    assert any("Газон" in d or "газон" in d.lower() for d in descriptions)


def test_house_area_keeps_integer_trailing_zeroes() -> None:
    proposal = deterministic_house_estimate_proposal(
        "Составь смету одноэтажного дома 100 м²"
    )
    assert proposal is not None
    assert proposal.title.endswith("100 м²")
    assert proposal.rows[0].quantity == "100"


def test_house_estimate_normalizes_moscow_grammatical_case() -> None:
    proposal = deterministic_house_estimate_proposal(
        "Составь подробную смету строительства одноэтажного дома 38 м² в Москве"
    )
    assert proposal is not None
    assert proposal.region == "Москва"
    assert len(proposal.rows) == 12


def test_weather_geocoder_retries_common_russian_case_forms() -> None:
    assert "Казань" in _location_candidates("Казани")
    assert "Лениногорск" in _location_candidates("Лениногорске")
    assert "Пекин" in _location_candidates("Пекине")


def test_repeat_run_history_stops_at_its_triggering_user_message() -> None:
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.executescript(
        """
        CREATE TABLE chat_messages (
            tenant_id TEXT, id TEXT, thread_id TEXT, sequence INTEGER,
            role TEXT, content_text TEXT
        );
        CREATE TABLE chat_runs (
            tenant_id TEXT, id TEXT, thread_id TEXT, input_message_id TEXT
        );
        INSERT INTO chat_messages VALUES
          ('tenant_1', 'message_user', 'thread_1', 1, 'user', 'Погода в Казани'),
          ('tenant_1', 'message_answer_1', 'thread_1', 2, 'assistant', 'Ответ 1'),
          ('tenant_1', 'message_answer_2', 'thread_1', 3, 'assistant', 'Ответ 2');
        INSERT INTO chat_runs VALUES
          ('tenant_1', 'run_repeat', 'thread_1', 'message_user');
        """
    )

    history = _history(
        database,
        SimpleNamespace(
            tenant_id="tenant_1",
            thread_id="thread_1",
            run_id="run_repeat",
        ),
    )

    assert history == [{"role": "user", "content": "Погода в Казани"}]


def test_ag_ui_storage_key_is_stable_only_for_the_exact_request() -> None:
    first = storage_client_run_id("run_transport123", "sha256:" + "a" * 64)
    retry = storage_client_run_id("run_transport123", "sha256:" + "a" * 64)
    changed = storage_client_run_id("run_transport123", "sha256:" + "b" * 64)

    assert first == retry
    assert first != changed
    assert first.startswith("run_")
