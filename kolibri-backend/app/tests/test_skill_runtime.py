from skill_runtime import public_skill_ids, public_specialization_for_messages


def user(text: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": text}]


def test_estimate_activates_estimate_contracts_only():
    assert public_skill_ids(user("Составь смету на штукатурку 358 м² в Лениногорске")) == (
        "construction-estimates-ru",
        "estimate-builder",
    )


def test_estimate_contract_and_act_are_composed_without_duplicates():
    assert public_skill_ids(user("Сделай смету и акт выполненных работ в DOCX")) == (
        "construction-estimates-ru",
        "estimate-builder",
        "estimate-documents",
        "word-docs",
    )


def test_legal_request_does_not_activate_estimator():
    assert public_skill_ids(user("Проверь договор подряда и риски неустойки")) == (
        "legal-documents-ru",
    )


def test_unrelated_chat_has_no_prompt_bloat():
    assert public_skill_ids(user("Привет, как дела?")) == ()
    assert public_specialization_for_messages(user("Привет, как дела?")) is None


def test_public_prompt_never_contains_operator_skill_contracts():
    prompt = public_specialization_for_messages(
        user("Сделай смету, договор и интерфейс мобильного приложения")
    )
    assert prompt is not None
    assert "kolibri-factory-admin" not in prompt
    assert "kolibri-infrastructure" not in prompt
    assert "Home Control Plane" not in prompt
    assert "Primary" not in prompt
