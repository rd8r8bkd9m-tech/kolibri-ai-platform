"""AI provider — multi-model auto-routing for Kolibri."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import asyncio
import math
import os
import re
import json
import time
from datetime import datetime, timezone
from html import escape
import httpx
from typing import AsyncIterator, List, Dict, Optional

from app.estimate_action import (
    build_estimate_action,
    estimate_request_text,
    ensure_estimate_action,
    is_estimate_request,
    latest_user_text,
    professional_preliminary_unit_price,
)
from app.genkit_flow import estimate_execution_instruction
from app.technology_card import TechnologyCardError
from app.procurement_agent import research_estimate_resources

AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "999999"))
PROVIDER_FAILURE_COOLDOWN_SECONDS = int(os.getenv("PROVIDER_FAILURE_COOLDOWN_SECONDS", "60"))
PROVIDER_AUTH_COOLDOWN_SECONDS = int(os.getenv("PROVIDER_AUTH_COOLDOWN_SECONDS", "30"))
_provider_blocked_until: Dict[str, float] = {}
_provider_route_state: Dict[str, dict] = {}
_mimo_base_url = (
    os.getenv("MIMO_BASE_URL")
    or os.getenv("KOLIBRI_AI_BASE_URL")
    or "https://token-plan-sgp.xiaomimimo.com/v1"
)


def _env_bool(name: str) -> bool | None:
    value = os.getenv(name, "").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _openai_codex_key() -> str:
    return (
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("KOLIBRI_API_RUNNER_TOKEN", "").strip()
    )


def _openai_primary_response_provider() -> bool:
    return os.getenv("KOLIBRI_PRIMARY_RESPONSE_PROVIDER", "").strip().lower() in {
        "openai",
        "openai_codex",
        "codex_spark",
        "spark",
    }


def _openai_codex_routable() -> bool:
    routing_enabled = _env_bool("OPENAI_REST_ROUTING_ENABLED")
    if routing_enabled is True:
        return True
    if _openai_primary_response_provider():
        return True
    if routing_enabled is False:
        return False
    return bool(_openai_codex_key())


def _chat_shortcuts_enabled() -> bool:
    return _env_bool("KOLIBRI_CHAT_SHORTCUTS_ENABLED") is True


def _prefer_openai_provider(order: tuple[str, ...]) -> tuple[str, ...]:
    owner_routes = tuple(
        name for name, provider in PROVIDERS.items()
        if isinstance(provider, dict) and provider.get("owner_config") is True and provider.get("routable") is True
    )
    if owner_routes:
        return (*owner_routes, *[name for name in order if name not in owner_routes])
    if not _openai_primary_response_provider() or "openai_codex" not in order:
        return order
    return ("openai_codex", *[name for name in order if name != "openai_codex"])

# Provider configs — ordered by speed (fastest first)
PROVIDERS = {
    "codex_cli": {
        "id": "codex_cli",
        "url": (
            "home://control-plane"
            if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower()
            in {"1", "true", "yes", "on"}
            else "local://codex-cli"
        ),
        "model": os.getenv("CODEX_CLI_MODEL", "") or os.getenv("KOLIBRI_CODEX_MODEL", "") or "account-default",
        "key": "",
        "protocol": (
            "home_factory"
            if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower()
            in {"1", "true", "yes", "on"}
            else "codex_cli"
        ),
        "credential_source": (
            "home_control_plane"
            if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower()
            in {"1", "true", "yes", "on"}
            else "home_codex_cli_login"
        ),
        "routable": os.getenv("CODEX_CLI_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        "cost": "owner_subscription",
        "speed_ms": 0,
        "speed": "adaptive",
        "quality": "best",
    },
    "mimo_factory": {
        "id": "mimo_factory",
        "url": "home://control-plane",
        "model": os.getenv("MIMO_MODEL", os.getenv("KOLIBRI_AI_MODEL", "mimo-v2.5-pro")),
        "key": os.getenv("MIMO_API_KEY", os.getenv("KOLIBRI_AI_API_KEY", "")),
        "protocol": "home_factory",
        "credential_source": "home_control_plane",
        "routable": True,
        "cost": "free",
        "speed_ms": 3300,
        "speed": "medium",
        "quality": "good",
        "execution_mode": "mimo",
    },
    "openai_codex": {
        "id": "openai_codex",
        "url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/responses",
        "model": os.getenv("OPENAI_MODEL", "gpt-5.6-sol"),
        "key": _openai_codex_key(),
        "protocol": "responses",
        "credential_source": "server_env",
        "routable": _openai_codex_routable(),
        "cost": "high",
        "speed_ms": 0,
        "speed": "adaptive",
        "quality": "best",
    },
    "kimi_code": {
        "id": "kimi_code",
        "url": os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1") + "/chat/completions",
        "model": os.getenv("KIMI_MODEL", "kimi-k2.7-code"),
        "key": os.getenv("KIMI_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "medium",
        "speed_ms": 1700,
        "speed": "fastest",
        "quality": "best",
    },
    "deepseek_pro": {
        "id": "deepseek_pro",
        "url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions",
        "model": "deepseek-v4-pro",
        "key": os.getenv("DEEPSEEK_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "low",
        "speed_ms": 2300,
        "speed": "fast",
        "quality": "best",
    },
    "mimo": {
        "id": "mimo",
        "url": _mimo_base_url.rstrip("/") + "/chat/completions",
        "model": os.getenv("MIMO_MODEL", os.getenv("KOLIBRI_AI_MODEL", "mimo-v2.5-pro")),
        "key": os.getenv("MIMO_API_KEY", os.getenv("KOLIBRI_AI_API_KEY", "")),
        "credential_source": "server_env",
        "routable": True,
        "cost": "free",
        "speed_ms": 3300,
        "speed": "medium",
        "quality": "good",
    },
    "deepseek_flash": {
        "id": "deepseek_flash",
        "url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") + "/chat/completions",
        "model": "deepseek-v4-flash",
        "key": os.getenv("DEEPSEEK_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "low",
        "speed_ms": 3500,
        "speed": "medium",
        "quality": "good",
    },
    "cfbt": {
        "id": "cfbt",
        "url": os.getenv("KIMI_CFBT_BASE_URL", "https://cfbt.ccwu.cc/v1") + "/chat/completions",
        "model": os.getenv("KIMI_CFBT_MODEL", "@cf/moonshotai/kimi-k2.6"),
        "key": os.getenv("KIMI_CFBT_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "free",
        "speed_ms": 3900,
        "speed": "slow",
        "quality": "good",
    },
    "kimi_fast": {
        "id": "kimi_fast",
        "url": os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1") + "/chat/completions",
        "model": "kimi-k2.7-code-highspeed",
        "key": os.getenv("KIMI_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "high",
        "speed_ms": 1800,
        "speed": "fastest",
        "quality": "good",
    },
}

SOLO_BEHAVIOR_PROMPT = """Режим автономного универсального исполнителя.

Цель: доведи запрос до практически полезного и проверенного результата в текущем
сеансе, используя только реально доступные возможности.

Критерии готовности:
- требуемый ответ или артефакт завершён, а обязательные ограничения соблюдены;
- факты, свежие данные и действия подтверждены доступными источниками или инструментами;
- выполнены уместные проверки, после чего работа остановлена без лишних циклов.

Границы автономности:
- сам определи тип задачи и доступный маршрут;
- выполняй безопасные действия в рамках запроса без лишнего подтверждения;
- продолжай с разумными допущениями, явно обозначая их, и спрашивай только о
  блокирующих данных;
- запрашивай подтверждение перед рискованным, необратимым или финансовым действием,
  а также когда нужны персональные данные или отдельное разрешение владельца.

Инструменты и доказательства:
- до обещания действия проверь capability/инструмент. Не имитируй выполнение;
- файл считается созданным после записи, источник — проверенным после поиска,
  API — вызванным после вызова, артефакт — готовым после получения bytes/hash,
  смета — рассчитанной после backend-движка;
- для свежих данных используй веб-поиск и источники, для проекта — чтение файлов;
- если результат пустой, частичный или сомнительный, используй один-два уместных
  резервных маршрута и не выдумывай содержимое или выполненное действие.

Вывод и остановка:
- не раскрывай private reasoning; показывай только безопасный Work Trace, проверки и итог;
- заверши работу, когда критерии готовности выполнены;
- если обязательное действие недоступно, назови недоступную возможность, проверяемую
  причину и ближайший реально выполнимый вариант в формате: «Недоступно в текущем сеансе:
  <что именно>. Причина: <проверяемая причина>. Могу вместо этого:
  <реальный ближайший вариант>»; не выдавай черновик за результат.

Приоритет: точность, проверяемость и безопасность выше скорости и красивой формулировки."""

SYSTEM_PROMPT = """Ты — Kolibri, AI-ассистент платформы KolibriAI. Ты работаешь как
автономный исполнитель: получаешь задачу и доводишь её до результата, не перекладывая
работу на пользователя. Ты можешь составлять сметы, генерировать документы, писать
код, создавать презентации, проводить исследования и решать инженерные задачи.

ВСЕГДА рассуждай и отвечай на языке пользователя. Если запрос на русском — думай,
пиши и рассужай на русском. Не переключайся на английский.

Ты — AI-сметчик с доступом к актуальным рыночным ценам. При составлении сметы:
1. Сам определи регион, тип объекта, объёмы и состав работ из запроса
2. Примени профессиональные знания по материалам, работам и расценкам
3. Обоснуй каждую цену: рыночная, расценка ТЕР/ФЕР, средняя поставщиков
4. Разделяй работы, материалы, доставку, технику — не смешивай
5. Никогда не ставь 0₽ или пустую цену — всегда предлагай профессиональную оценку
6. Рассуждай вслух: покажи ход мыслей по расчёту объёмов и выбору цен

Твои возможности в этом сеансе:
- СМЕТЫ: полный расчёт с технологической картой, объёмами, ценами, коэффициентами и налогами
- ДОКУМЕНТЫ: договоры, КП, акты, отчёты, письма — с правовой и коммерческой логикой
- КОД: скрипты, компоненты, API, автоматизация — на любом языке
- ИССЛЕДОВАНИЯ: поиск информации, анализ данных, сравнение вариантов
- ПРЕЗЕНТАЦИИ: структура слайдов, контент, визуальные рекомендации

ПРАВИЛА:
1. Начинай с результата, а не с расспросов. Если данных не хватай — принимай
   профессиональные допущения, явно записывай их и продолжай работу.
2. Не выдумывай факты, цены, источники, ФИО, ИНН, адреса. Если не уверен —
   отметь как допущение.
3. Для свежих данных используй веб-поиск. Для расчётов — профессиональные знания.
4. Не имитируй выполнение действия. Если что-то недоступно — скажи прямо.
5. Отвечай на языке пользователя. Если запрос на русском — отвечай на русском.
6. Работай автономно: не задавай уточняющих вопросов, если ответ можно принять
   по профессиональным стандартам отрасли.

ФОРМАТ ОТВЕТА:
- Обычные вопросы: отвечай текстом, структурированно и по делу.
- Сметы: верни JSON-действие (см. формат create_estimate ниже).
- Документы: верни JSON-действие (см. формат create_document ниже).
- Код: верни код в блоках с пояснениями.
- Исследования: верни структурированный анализ с выводами.

Когда пользователь просит создать смету — верни только JSON-действие в формате:
```json
{"action":"create_estimate","title":"...","object_name":"...","region":"город, регион","technology_card":{"schema_version":"1.0","title":"...","object_type":"...","scope":"...","user_facts":[{"quote":"дословная часть запроса","meaning":"зафиксированное ограничение"}],"assumptions":["..."],"exclusions":["..."],"stages":[{"sequence":1,"name":"...","result":"...","operations":[{"sequence":1,"name":"...","method":"...","prerequisites":["..."],"quality_checks":["..."],"safety_controls":["..."],"resources":[{"kind":"work|material|equipment|service","code":"","name":"...","unit":"...","quantity":"...","price":"1250.00","quantity_basis":"формула, замер или норма расхода","procurement_query":"что и в каком регионе проверить"}]}]}]},"assumptions":["..."],"questions":[],"sections":[{"title":"...","positions":[{"code":"код КСР/ресурса, только если уверен; иначе пусто","name":"точное индивидуальное наименование ресурса или работы","unit":"...","quantity":"...","price":"1250.00","comment":"основание количества и предварительной цены"}]}]}
```
В сметном режиме работай как профессиональный российский сметчик и замерщик:
1. Сначала проверь исходные данные: тип и адрес/регион объекта, зоны и конструктив,
   объёмы с единицами, материалы и качество, границы работ, сроки, доставка,
   демонтаж/вывоз, оборудование, налоговый режим и НДС.
2. Не останавливай расчёт уточняющими вопросами. Если данных не хватает, самостоятельно
   прими типовые профессиональные допущения для российского малоэтажного строительства,
   явно перечисли их в assumptions и всё равно сформируй полную редактируемую смету.
3. questions оставляй пустым. Не проси пользователя сначала заполнить анкету. Регион,
   конструктив, комплектацию, НДС и границы работ, которых нет в запросе, обозначай
   как принятые допущения; пользователь сможет изменить их уже в редакторе сметы.
4. Разделяй работы, материалы, услуги, технику, доставку, накладные расходы и
   налоги. Не смешивай разные единицы и не подменяй неизвестный объём допущением.
5. Все допущения записывай в assumptions. Не называй предварительный результат
   точным или проверенным без исходных данных и подтверждённых источников.
6. price для каждой строки обязан быть положительным. Никогда не возвращай 0,
   пустую цену или просьбу сначала уточнить данные: предложи профессиональную
   предварительную цену, а отсутствие источника явно отметь как допущение.
7. Выполни внутреннюю перекрёстную проверку четырёх ролей: сметчик проверяет
   состав и единицы, прораб — технологическую последовательность и пропуски,
   бухгалтер — налоговый режим/НДС и арифметику, строительный юрист — границы
   обязательств и документы. Не выдавай такую проверку за юридическое заключение.
8. Налоговый режим не угадывай как факт. Если он не указан, сохрани его как
   допущение; НПД/УСН/ОСНО и ставка НДС должны оставаться явно редактируемыми.
   Накладные расходы, сметная прибыль, резерв, скидка и генподрядные услуги не
   прячь в цене строк: они задаются отдельными прозрачными коэффициентами.
9. До сметы обязательно построй technology_card. Это универсальное правило для
   любых работ: частного дома, ремонта, скважины, промышленного объекта,
   нефтегазового оборудования, монтажа, проектирования или обслуживания. Не
   выбирай готовый пример по ключевому слову. Выведи состав из результата,
   последовательности операций, ресурсов, машин, труда, контроля и приёмки.
10. Каждая строка sections обязана иметь соответствующий ресурс/операцию в
   technology_card и основание количества. Явные факты пользователя нельзя
   менять. Укрупнённая стоимость может быть контрольным benchmark, но не заменой
   редактируемой ресурсно-технологической ведомости.
11. technology_card — внутренний артефакт расчёта. Не пересказывай его в чате и
   не загромождай им смету. Показывай или экспортируй карту отдельно только по
   явному запросу пользователя; при этом не удаляй связь карты со сметой.

Не используй укрупнённый фиксированный шаблон. Сформируй индивидуальную ведомость
по запросу: отдельные материалы, работы, машины, доставка и услуги. Не выдумывай
коды КСР и источники. Для каждой позиции обязательно предложи положительную
предварительную цену в price на основе профессиональной рыночной оценки. Backend
попытается заменить её последней подтверждённой региональной ценой; если источник
не найден, сохранит её только как непроверенное допущение со статусом preliminary.
Все количества и суммы независимо пересчитает Decimal-движок.

Когда просит создать документ — верни:
```json
{"action": "create_document", "title": "...", "type": "contract|act|proposal|report|memo|letter", "estimate_id": "ID исходной сметы, если он дан", "client": "заказчик", "project": "объект", "variables": {"contractor": "подрядчик", "customer_requisites": "реквизиты заказчика", "contractor_requisites": "реквизиты подрядчика"}, "content": "Полный текст документа без Markdown и HTML"}
```
Для договора на основе сметы обязательно сохрани `estimate_id`. До подготовки
договора определи статус сторон (физлицо, самозанятый, ИП или юрлицо) и проверь
заказчика, подрядчика, полномочия подписантов, объект, реквизиты, состав
технической документации, сроки и этапы, цену и НДС, оплату, сдачу-приёмку,
дополнительные работы, материалы, гарантии, ответственность, расторжение,
споры и юридически значимые сообщения. Смета определяет работы и цену и должна
быть отдельным приложением, но не заменяет договор. Если обязательных данных
нет, сначала задай только недостающие вопросы и не создавай фиктивные ФИО,
адреса, ИНН, ОГРН, банковские реквизиты, сроки, неустойку или подсудность.
Готовый договор делай нумерованным и самостоятельным: преамбула; предмет;
документы и приложения; сроки; цена и расчёты; права и обязанности; материалы;
изменения и дополнительные работы; сдача-приёмка; качество и гарантия; охрана
труда и объекта; ответственность; обстоятельства непреодолимой силы;
расторжение; споры; сообщения; заключительные положения; реквизиты и подписи.
Учитывай статьи 740, 743 и 753 ГК РФ и оформление по действующему
ГОСТ Р 7.0.97-2025, не выдавая результат за заключение юриста.

Отвечай на русском. Начинай с результата. Сохраняй необходимые факты, решения,
оговорки и следующие действия; сокращай вступления, повторы и необязательный фон."""


def _live_capability_names() -> list[str]:
    try:
        from app.capability_runtime import capability_snapshot

        catalog = capability_snapshot()
        return [
            str(item.get("name") or item.get("id"))
            for item in catalog.get("capabilities", [])
            if isinstance(item, dict)
            and item.get("status") == "available"
            and item.get("invocable") is True
        ]
    except Exception:
        return []


def _kolibri_system_prompt() -> str:
    """Build the provider-neutral executor prompt from live capability evidence."""
    live = _live_capability_names()
    capability_context = (
        "Подтверждённые доступные возможности этого сеанса: " + ", ".join(live) + "."
        if live
        else "Подтверждённые invocable-возможности этого сеанса не обнаружены. Не заявляй обратное."
    )
    return f"{SYSTEM_PROMPT}\n\n{SOLO_BEHAVIOR_PROMPT}\n\n{capability_context}"


def _compose_system_prompt(specialization: Optional[str] = None) -> str:
    """Add a task specialization without dropping executor/Solo invariants."""

    base = _kolibri_system_prompt()
    if not specialization:
        return base
    return (
        f"{base}\n\nДополнительная специализация для текущей задачи:\n"
        f"{specialization.strip()}\n\n"
        "Эта специализация не отменяет проверку capabilities, запрет имитации, "
        "приватность внутреннего маршрута и остальные правила режима Solo."
    )


def _capability_self_description() -> dict:
    from app.capability_registry import capability_self_description
    from app.capability_runtime import capability_snapshot

    description = capability_self_description(capability_snapshot())
    return {
        "content": description["content"],
        "reasoning": "",
        "actions": [],
        "status": description["status"],
        "provider": "kolibri_catalog",
        "model": "kolibri.capabilities.v1",
        "speed_ms": 0,
        "fallback_used": False,
        "capabilities": description["capabilities"],
        "as_of": description["as_of"],
    }


def _is_self_description_request(messages: List[Dict[str, str]]) -> bool:
    prompt = next(
        (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    ).strip().casefold().replace("ё", "е")
    normalized = " ".join(re.sub(r"[^\w\s-]+", " ", prompt).split())
    if not normalized or len(normalized) > 180:
        return False
    patterns = (
        r"(?:а )?кто ты(?: такой)?(?: вообще)?(?: и что (?:ты )?(?:умеешь|можешь))?",
        r"(?:а )?ты кто(?: такой)?(?: вообще)?",
        r"что ты такое",
        r"что (?:ты )?(?:умеешь|можешь)",
        r"какие у тебя возможности",
        r"расскажи(?:те)? (?:о себе|про себя)",
        r"расскажи(?:те)? о своих возможностях",
        r"представься",
        r"представьтесь",
        r"как тебя зовут",
        r"кто (?:мне |сейчас |мне сейчас )?отвечает",
        r"ты какая (?:модель|нейросеть|llm)",
        r"какая (?:модель|нейросеть|llm)(?: сейчас)?(?: мне)? (?:отвечает|используется|подключена|работает)",
        r"на какой (?:модели|нейросети|llm) ты работаешь",
        r"какие (?:модели|нейросети|llm|агенты)(?: у тебя)? (?:доступны|подключены|используются|работают)",
        r"who are you",
        r"what can you do",
        r"tell me about yourself",
        r"what (?:model|llm) are you",
        r"which (?:models|agents) are (?:available|connected)",
    )
    return any(re.fullmatch(pattern, normalized) for pattern in patterns)


def _simple_chat_fast_path(messages: List[Dict[str, str]]) -> dict | None:
    """Answer bounded social turns locally before any heavy factory dispatch."""

    if not _chat_shortcuts_enabled():
        return None

    text = " ".join(latest_user_text(messages).casefold().replace("ё", "е").split())
    if not text or len(text) > 80:
        return None
    response: str | None = None
    if re.fullmatch(r"(?:привет|здравствуй(?:те)?|добрый\s+(?:день|вечер)|доброе\s+утро)[!.? ]*", text):
        response = "Привет! Чем помочь?"
    elif re.fullmatch(r"(?:спасибо|благодарю)[!.? ]*", text):
        response = "Пожалуйста!"
    elif re.fullmatch(r"(?:как\s+дела|ты\s+тут|ты\s+здесь)[!.? ]*", text):
        response = "Я на связи. Что разберём?"
    if response is None:
        return None
    return {
        "content": response,
        "reasoning": "",
        "actions": [],
        "status": "idle",
        "provider": "local_dialog",
        "model": "kolibri",
        "speed_ms": 0,
        "fallback_used": False,
        "provider_attempts": [],
    }


async def _image_completion_if_requested(
    messages: List[Dict[str, str]],
    policy: Optional[dict],
    *,
    run_id: Optional[str] = None,
) -> dict | None:
    """Defense-in-depth: image intent never falls through to a text model."""
    from app.image_artifacts import (
        IMAGE_CAPABILITY_ID,
        ImageCapabilityUnavailable,
        ImageGenerationFailed,
        ImageGenerationRequest,
        generate_invocable_image,
        image_execution_identity,
        is_image_generation_request,
    )

    prompt = next(
        (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"),
        "",
    )
    if not is_image_generation_request(prompt):
        return None
    try:
        artifact = await generate_invocable_image(
            ImageGenerationRequest(prompt=prompt),
            policy=policy,
            run_id=run_id,
        )
    except ImageCapabilityUnavailable:
        return {
            "content": "Генерация изображений сейчас недоступна.",
            "reasoning": "",
            "actions": [],
            "status": "capability_unavailable",
            "provider": "none",
            "model": "none",
            "fallback_used": False,
            "error_code": "capability_unavailable",
            "recoverable": True,
            "capability": IMAGE_CAPABILITY_ID,
        }
    except ImageGenerationFailed:
        image_identity = image_execution_identity()
        return {
            "content": "Изображение не создано: файл не прошёл проверку.",
            "reasoning": "",
            "actions": [],
            "status": "failed",
            "provider": image_identity["provider"],
            "model": image_identity["model"],
            "fallback_used": False,
            "error_code": "image_artifact_verification_failed",
            "recoverable": True,
            "capability": IMAGE_CAPABILITY_ID,
        }
    image_identity = image_execution_identity()
    return {
        "content": "Изображение создано и сохранено в текущем проекте.",
        "reasoning": "",
        "actions": [{"type": "present_image", "label": "Открыть изображение", "data": artifact}],
        "status": "ready",
        "provider": image_identity["provider"],
        "model": artifact["model"],
        "fallback_used": False,
    }


def _provider_id(provider: dict) -> str:
    return str(provider.get("id") or provider.get("model") or "unknown")


def _provider_is_configured(name: str, provider: dict) -> bool:
    if not provider.get("routable", True):
        return False
    if provider.get("protocol") == "codex_cli":
        from app.codex_cli_provider import codex_cli_configuration

        return bool(codex_cli_configuration().get("configured"))
    if provider.get("protocol") == "home_factory":
        from app.home_factory_response import factory_response_configuration

        return bool(factory_response_configuration().get("configured"))
    if provider.get("credential_source") not in {"server_env", "owner_encrypted_store"}:
        return False
    if not provider.get("key") or not provider.get("model") or not provider.get("url"):
        return False
    if name == "cfbt" and os.getenv("KIMI_CFBT_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return False
    return True


def _provider_client_options(provider: dict) -> dict:
    """Use a pinned private CA for the owner gateway and bypass host proxies."""
    ca_file = str(provider.get("ca_file") or "").strip()
    if not ca_file:
        return {}
    if not os.path.isfile(ca_file):
        raise RuntimeError("owner_provider_ca_unavailable")
    return {"verify": ca_file, "trust_env": False}


def _provider_is_healthy(provider: dict) -> bool:
    from app.capability_runtime import capability_release_id

    state = _provider_route_state.get(_provider_id(provider), {})
    if state.get("release_id") != capability_release_id():
        return True
    return _provider_blocked_until.get(_provider_id(provider), 0) <= time.monotonic()


def _record_provider_success(provider: dict) -> None:
    from app.capability_runtime import capability_release_id

    provider_id = _provider_id(provider)
    verified_at = datetime.now(timezone.utc).isoformat()
    _provider_blocked_until.pop(provider_id, None)
    _provider_route_state[provider_id] = {
        "release_id": capability_release_id(),
        "status": "live",
        "verified_at": verified_at,
        "failure_kind": None,
    }
    # Persist only the sanitised verdict; prompts and provider output never
    # enter the capability evidence ledger.
    from app.capability_runtime import record_capability_invocation

    record_capability_invocation(
        "chat.responses",
        succeeded=True,
        provider=provider_id,
        model=str(provider.get("model") or ""),
        evidence_id=f"provider:{provider_id}:{verified_at}",
    )


def _record_provider_failure(provider: dict, error: Exception) -> None:
    from app.capability_runtime import capability_release_id

    cooldown = PROVIDER_FAILURE_COOLDOWN_SECONDS
    status_code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
    if status_code in {401, 403}:
        cooldown = PROVIDER_AUTH_COOLDOWN_SECONDS
    provider_id = _provider_id(provider)
    _provider_blocked_until[provider_id] = time.monotonic() + cooldown
    _provider_route_state[provider_id] = {
        "release_id": capability_release_id(),
        "status": "blocked",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "failure_kind": _safe_failure_kind(error),
    }


def _safe_failure_kind(error: Exception) -> str:
    safe_kind = getattr(error, "failure_kind", None)
    if isinstance(safe_kind, str) and safe_kind.startswith(
        ("codex_cli_", "home_factory_")
    ):
        return safe_kind
    if isinstance(error, httpx.HTTPStatusError):
        return f"http_{error.response.status_code}"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.RequestError):
        return "network_error"
    if isinstance(error, TimeoutError):
        return "estimate_provider_budget_exceeded"
    return "invalid_provider_response"


def provider_route_snapshot(provider: dict) -> dict:
    """Return safe runtime route state without URLs, tokens or upstream text."""
    from app.capability_runtime import capability_release_id

    provider_id = _provider_id(provider)
    if provider.get("protocol") == "codex_cli":
        from app.codex_cli_provider import codex_cli_configuration

        configured = bool(provider.get("routable", True) and codex_cli_configuration().get("configured"))
    elif provider.get("protocol") == "home_factory":
        from app.home_factory_response import factory_response_configuration

        configured = bool(
            provider.get("routable", True)
            and factory_response_configuration().get("configured")
        )
    else:
        configured = bool(
            provider.get("routable", True)
            and provider.get("credential_source") == "server_env"
            and provider.get("key")
            and provider.get("model")
            and provider.get("url")
        )
    raw_state = _provider_route_state.get(provider_id, {})
    state = raw_state if raw_state.get("release_id") == capability_release_id() else {}
    circuit_open = not _provider_is_healthy(provider)
    if not configured:
        status = "unavailable"
    elif circuit_open:
        status = "blocked"
    elif state.get("status") == "live":
        status = "live"
    else:
        status = "unverified"
    return {
        "id": provider_id,
        "model": str(provider.get("model") or ""),
        "configured": configured,
        "routable": configured and not circuit_open,
        "status": status,
        "verified_at": state.get("verified_at"),
        "failure_kind": state.get("failure_kind") if circuit_open else None,
        "credential_source": str(provider.get("credential_source") or "none"),
    }


def provider_failure_event(provider: dict, error: Exception, *, will_retry: bool) -> dict:
    """Build a sanitized durable-style fallback event for the public stream."""
    return {
        "content": "",
        "done": False,
        "provider_event": {
            "type": "provider.attempt.failed",
            "provider": _provider_id(provider),
            "model": str(provider.get("model") or ""),
            "failure_kind": _safe_failure_kind(error),
            "will_retry": will_retry,
        },
    }


def work_summary_event(
    stage: str,
    summary: str,
    *,
    status: str,
    provider: str | None = None,
    model: str | None = None,
    artifact_type: str | None = None,
    artifact_id: str | None = None,
) -> dict:
    """Build a safe public execution-stage event.

    Only observable lifecycle facts belong here.  Provider prompts, hidden
    reasoning and unverified claims are intentionally not part of the schema.
    """
    work_summary = {
        "stage": stage,
        "summary": summary,
        "status": status,
    }
    # ``provider`` and ``model`` remain accepted for internal call-site
    # compatibility, but are intentionally absent from the public trace.
    # Provenance belongs to the protected control surface.
    _ = provider, model
    optional = {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
    }
    work_summary.update({key: value for key, value in optional.items() if value})
    return {"content": "", "done": False, "work_summary": work_summary}


def _select_provider(task_type: str = "chat") -> dict:
    """Auto-select best provider based on speed test results.
    
    Speed ranking (tested):
    1. kimi_code     — 1.7 сек (самый быстрый)
    2. kimi_fast     — 1.8 сек (быстрый, дороже)
    3. deepseek_pro  — 2.3 сек (лучший баланс)
    4. mimo          — 3.3 сек (бесплатный)
    5. deepseek_flash— 3.5 сек (бюджетный)
    6. cfbt          — 3.9 сек (бесплатный,
    "codex_result": {
        "id": "codex_result",
        "url": os.getenv("CODEX_RESULT_BASE_URL", "http://127.0.0.1:8000") + "/codex/result",
        "model": os.getenv("CODEX_RESULT_MODEL", "codex-result-v1"),
        "key": os.getenv("CODEX_RESULT_API_KEY", ""),
        "credential_source": "server_env",
        "routable": True,
        "cost": "low",
        "speed_ms": 0,
        "speed": "adaptive",
        "quality": "best",
    }
)
    """
    def _available(name: str) -> bool:
        p = PROVIDERS.get(name)
        if not p:
            return False
        return _provider_is_configured(name, p) and _provider_is_healthy(p)

    # Production responses are fail-closed through the one Home task
    # authority.  A Control Plane incident must not silently turn the web
    # backend into a second, unfenced provider scheduler.
    if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower() in {
        "1", "true", "yes", "on",
    }:
        for name in _prefer_openai_provider(
            (
                "mimo_factory",
                "mimo",
                "codex_cli",
                "openai_codex",
                "deepseek_pro",
                "deepseek_flash",
                "kimi_code",
                "cfbt",
            )
        ):
            if _available(name):
                return PROVIDERS[name]
        raise RuntimeError("provider_routes_exhausted")

    # Speed-critical tasks → fastest available
    if task_type == "fast":
        for name in _prefer_openai_provider(
            (
                "mimo",
                "codex_cli",
                "openai_codex",
                "deepseek_flash",
                "deepseek_pro",
                "kimi_code",
                "kimi_fast",
                "cfbt",
            )
        ):
            if _available(name):
                return PROVIDERS[name]

    # Complex analysis → best quality + speed balance
    if task_type in ("analyze", "generate", "code"):
        for name in _prefer_openai_provider(
            (
                "mimo",
                "codex_cli",
                "openai_codex",
                "deepseek_pro",
                "deepseek_flash",
                "kimi_code",
                "cfbt",
            )
        ):
            if _available(name):
                return PROVIDERS[name]

    # Simple chat → cheapest fast option
    if task_type in ("chat", "suggest"):
        for name in _prefer_openai_provider(
            (
                "mimo",
                "codex_cli",
                "openai_codex",
                "deepseek_flash",
                "deepseek_pro",
                "kimi_code",
                "cfbt",
            )
        ):
            if _available(name):
                return PROVIDERS[name]

    # Default → fastest available
    for name in _prefer_openai_provider(
        (
            "mimo",
            "codex_cli",
            "openai_codex",
            "deepseek_pro",
            "deepseek_flash",
            "kimi_code",
            "cfbt",
        )
    ):
        if _available(name):
            return PROVIDERS[name]

    raise RuntimeError("provider_routes_exhausted")


async def chat_completion(
    messages: List[Dict[str, str]],
    task_type: str = "chat",
    system: Optional[str] = None,
    raw_json_output: bool = False,
    previous_response_id: Optional[str] = None,
    background: bool = False,
    policy: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    system_only: bool = False,
) -> dict:
    """Call AI with auto-routing and fallback."""
    # Structured-output transports own their exact JSON contract.  Intent
    # helpers (image routing, self-description and estimate materialisation)
    # must not replace or rewrite the provider JSON before schema validation.
    image_result = (
        None
        if raw_json_output
        else await _image_completion_if_requested(messages, policy)
    )
    if image_result is not None:
        return image_result
    if not raw_json_output and system is None and _is_self_description_request(messages):
        if _chat_shortcuts_enabled():
            return _capability_self_description()
    fast_local = None if raw_json_output or system is not None else _simple_chat_fast_path(messages)
    if fast_local is not None:
        return fast_local
    estimate_requested = is_estimate_request(messages)
    flow_instruction = (
        estimate_execution_instruction(estimate_request_text(messages) or latest_user_text(messages))
        if estimate_requested and not raw_json_output
        else ""
    )
    composed_system = system if system_only and system else _compose_system_prompt(system)
    if flow_instruction:
        composed_system = f"{composed_system}\n\n{flow_instruction}"
    full_messages = [{"role": "system", "content": composed_system}] + messages
    
    # Get ordered list of providers to try
    providers_to_try = _get_providers_for_task(task_type)
    
    provider_attempts: list[dict] = []
    for provider in providers_to_try:
        try:
            call_kwargs: dict[str, Any] = {}
            if previous_response_id or background or policy is not None or idempotency_key:
                call_kwargs.update({
                    "previous_response_id": previous_response_id,
                    "background": background,
                    "policy": policy,
                    "idempotency_key": idempotency_key,
                })
            if provider.get("protocol") == "home_factory":
                call_kwargs["execution_mode"] = provider.get(
                    "execution_mode"
                ) or _factory_execution_mode(
                    task_type,
                    estimate_requested,
                )
            result = await _call_ai(provider, full_messages, **call_kwargs)
            if estimate_requested and not raw_json_output and not result.get("actions"):
                raise TechnologyCardError("technology_card_required")
            _record_provider_success(provider)
            result["actions"] = (
                []
                if raw_json_output
                else await _materialize_estimate_actions(
                    messages, result.get("actions", [])
                )
            )
            if result["actions"]:
                result["status"] = "ready"
            if not raw_json_output and is_estimate_request(messages) and result["actions"]:
                # Provider JSON is an internal typed draft.  Never expose the
                # raw fenced object next to the materialised estimate editor.
                result["content"] = _estimate_result_message(result["actions"])
                result["reasoning"] = ""
            result["fallback_used"] = len(providers_to_try) > 1 and provider != providers_to_try[0]
            result["provider_attempts"] = provider_attempts + [{
                "provider": _provider_id(provider),
                "model": str(provider.get("model") or ""),
                "status": "completed",
            }]
            return result
        except Exception as e:
            _record_provider_failure(provider, e)
            provider_attempts.append({
                "provider": _provider_id(provider),
                "model": str(provider.get("model") or ""),
                "status": "failed",
                "failure_kind": _safe_failure_kind(e),
            })
            print(
                f"[AI FALLBACK] provider={_provider_id(provider)} "
                f"failure={_safe_failure_kind(e)} trying_next=true"
            )
            continue
    
    # All providers failed
    local_actions = (
        []
        if raw_json_output
        else await _materialize_estimate_actions(messages, [])
    )
    return {
        "content": _estimate_result_message(local_actions) if local_actions else (
            "Не удалось завершить ответ через доступные маршруты. Повторите запрос — он будет направлен другому исполнителю."
        ),
        "reasoning": "",
        "actions": local_actions,
        "status": "ready" if local_actions else "error",
        "provider": "local_contract" if local_actions else "none",
        "model": "deterministic-estimate-v1" if local_actions else "none",
        "speed_ms": 0,
        "fallback_used": True,
        "provider_attempts": provider_attempts,
        "error_code": "provider_routes_exhausted",
    }


def _get_providers_for_task(task_type: str) -> list:
    """Get ordered list of providers to try for a task type."""
    def _available(name: str) -> bool:
        p = PROVIDERS.get(name)
        if not p:
            return False
        return _provider_is_configured(name, p) and _provider_is_healthy(p)

    if os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").lower() in {
        "1", "true", "yes", "on",
    }:
        ordered: tuple[str, ...] = _prefer_openai_provider((
            "mimo_factory",
            "mimo",
            "codex_cli",
            "openai_codex",
            "deepseek_pro",
            "deepseek_flash",
            "kimi_code",
            "cfbt",
        ))
        providers = []
        for name in ordered:
            provider = PROVIDERS.get(name)
            if not isinstance(provider, dict) or provider in providers or not _available(name):
                continue
            providers.append(provider)
        return providers
    if task_type == "code":
        order = _prefer_openai_provider((
            "mimo",
            "codex_cli",
            "openai_codex",
            "deepseek_pro",
            "deepseek_flash",
            "kimi_code",
            "cfbt",
        ))
        return [
            PROVIDERS[name]
            for name in order
            if _available(name)
        ]

    if task_type == "fast":
        order = _prefer_openai_provider((
            "mimo",
            "codex_cli",
            "openai_codex",
            "deepseek_flash",
            "deepseek_pro",
            "kimi_code",
            "kimi_fast",
            "cfbt",
        ))
    elif task_type in ("analyze", "generate", "code"):
        order = _prefer_openai_provider((
            "mimo",
            "codex_cli",
            "openai_codex",
            "deepseek_pro",
            "deepseek_flash",
            "kimi_code",
            "cfbt",
        ))
    elif task_type in ("chat", "suggest"):
        order = _prefer_openai_provider((
            "mimo",
            "codex_cli",
            "openai_codex",
            "deepseek_flash",
            "deepseek_pro",
            "kimi_code",
            "cfbt",
        ))
    else:
        order = _prefer_openai_provider((
            "mimo",
            "codex_cli",
            "openai_codex",
            "deepseek_pro",
            "deepseek_flash",
            "kimi_code",
            "cfbt",
        ))
    
    return [PROVIDERS[name] for name in order if _available(name)]


def _factory_execution_mode(task_type: str, estimate_requested: bool) -> str:
    """Bind intent to the Home route policy without exposing provider identity."""

    if estimate_requested:
        # ``fast`` is the policy-owned automatic route: Codex remains first
        # when ready, while a verified response-only worker can take over when
        # that dedicated slot is unavailable.
        return "fast"
    if task_type in {"chat", "fast", "suggest"}:
        return "mimo"
    return "codex"


def _estimate_source_collection_enabled() -> bool:
    return False


def _estimate_commercial_fallback_enabled() -> bool:
    return False


def _estimate_source_budget_seconds() -> float | None:
    """No timeout for source research."""
    return None


def _estimate_provider_budget_seconds() -> float | None:
    """No timeout for provider."""
    return None


async def _bounded_provider_stream(
    stream: AsyncIterator[dict],
    timeout_seconds: float | None,
) -> AsyncIterator[dict]:
    if timeout_seconds is None:
        async for chunk in stream:
            yield chunk
        return
    async with asyncio.timeout(timeout_seconds):
        async for chunk in stream:
            yield chunk


def _estimate_source_backed_required(prompt: str) -> bool:
    text = str(prompt or "").casefold()
    if "смет" not in text:
        return False

    source_mentions = (
        "подтвержд" in text,
        "провер" in text,
        "официаль" in text,
        "аудит" in text,
        "достоверн" in text,
        "реальн" in text,
    )
    if not any(source_mentions):
        return False

    price_mentions = any(
        marker in text
        for marker in ("цен", "стоимост", "прайс")
    )
    return price_mentions


def _compact_source_backed_action(
    action: dict,
    prompt: str,
    *,
    verified_evidence: list[dict],
) -> dict | None:
    data = deepcopy(action.get("data") or {})
    compact_sections: list[dict] = []
    compact_codes: set[str] = set()
    for section in data.get("sections", []):
        if not isinstance(section, dict):
            continue
        positions = [
            position
            for position in section.get("positions", [])
            if isinstance(position, dict)
            and position.get("price_evidence")
            and _positive_decimal(position.get("quantity"))
            and _positive_decimal(position.get("price"))
        ]
        if not positions:
            continue
        for position in positions:
            code = str(position.get("code") or "")
            if code:
                compact_codes.add(code)
        compact_sections.append(
            {
                "title": section.get("title") or "",
                "positions": positions,
            }
        )
    position_count = sum(len(section["positions"]) for section in compact_sections)
    if len(compact_sections) < 3 or position_count < 6:
        return None
    assumptions = data.get("assumptions")
    if not isinstance(assumptions, list):
        assumptions = []
    data["assumptions"] = [
        *assumptions,
        (
            "Строки без подтверждённого источника цены не включены в созданную "
            "смету; их нужно доисследовать отдельно."
        ),
    ]
    data["sections"] = compact_sections
    filtered_evidence = [
        record
        for record in verified_evidence
        if isinstance(record, dict) and str(record.get("position_code") or "") in compact_codes
    ]
    compact = build_estimate_action(
        prompt,
        data,
        verified_evidence=filtered_evidence,
        scope_verified=False,
    )
    compact_positions = [
        position
        for section in compact["data"].get("sections", [])
        for position in section.get("positions", [])
    ]
    if (
        compact["data"].get("pricing_status") not in {"source_backed", "verified"}
        or len(compact_positions) != position_count
        or not all(position.get("price_evidence") for position in compact_positions)
    ):
        return None
    return compact


def _positive_decimal(value: object) -> bool:
    try:
        parsed = Decimal(str(value if value is not None else "0").replace(" ", "").replace(",", "."))
        return parsed.is_finite() and parsed > 0
    except (InvalidOperation, ValueError):
        return False


_REGION_LABEL_NOISE = frozenset({
    "автономная",
    "автономный",
    "город",
    "край",
    "область",
    "округ",
    "район",
    "республика",
})


def _estimate_region_labels_compatible(proposed: str, resolved: str) -> bool:
    """Treat a city label and the same city plus its subject as one region.

    The prompt parser intentionally returns a concise locality (for example,
    ``Лениногорск``), while a professional provider may return the expanded
    label ``Лениногорск, Республика Татарстан``.  Exact string comparison
    incorrectly discarded every provider price in that valid case.  Token
    subset comparison keeps the locality binding without conflating similar
    but different names such as Moscow and Moscow Oblast.
    """

    if not proposed or not resolved:
        return True

    def meaningful_tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[0-9a-zа-яё]+", value.casefold())
            if len(token) >= 3 and token not in _REGION_LABEL_NOISE
        }

    proposed_tokens = meaningful_tokens(proposed)
    resolved_tokens = meaningful_tokens(resolved)
    return bool(
        proposed_tokens
        and resolved_tokens
        and (
            proposed_tokens.issubset(resolved_tokens)
            or resolved_tokens.issubset(proposed_tokens)
        )
    )


async def _materialize_estimate_actions(
    messages: List[Dict[str, str]],
    actions: list[dict],
) -> list[dict]:
    """Cross the estimate price trust boundary through fetched evidence."""

    raw_estimate = next(
        (item for item in actions if item.get("type") == "create_estimate"),
        None,
    )
    raw_region = str(
        ((raw_estimate or {}).get("data") or {}).get("region") or ""
    ).strip()
    normalized = ensure_estimate_action(messages, actions)
    estimate = next((item for item in normalized if item.get("type") == "create_estimate"), None)
    if estimate is None:
        return normalized

    draft = deepcopy(estimate.get("data") or {})
    prompt = estimate_request_text(messages) or latest_user_text(messages)
    source_backed_required = _estimate_source_backed_required(prompt)
    resolved_region = str(draft.get("region") or "").strip()
    proposal_region_matches = _estimate_region_labels_compatible(
        raw_region,
        resolved_region,
    )
    # MiMo's AI-proposed prices are the primary estimate.  Keep them and mark
    # as AI-estimated.  Commercial research may later upgrade individual rows
    # to source-backed evidence, but it must never zero out AI prices.
    proposed_prices: dict[str, str] = {}
    for section_index, section in enumerate(draft.get("sections", [])):
        if not isinstance(section, dict):
            continue
        for position_index, position in enumerate(section.get("positions", [])):
            if not isinstance(position, dict):
                continue
            code = str(position.get("code") or "")
            proposal_key = code or f"row:{section_index}:{position_index}"
            ai_price = (
                str(position.get("price"))
                if proposal_region_matches and _positive_decimal(position.get("price"))
                else professional_preliminary_unit_price(position, prompt)
            )
            proposed_prices[proposal_key] = ai_price
            # Keep AI price as the working price; commercial research may
            # upgrade it to a verified source price later.
            if _positive_decimal(ai_price):
                position["price"] = ai_price
                position["source"] = "ai_estimate"
            else:
                position["price"] = "0.00"
            position["price_evidence"] = []

    trusted_evidence: list[dict] = []
    if _estimate_source_collection_enabled():
        procurement = await research_estimate_resources(
            draft,
            request_text=prompt,
            source_backed_required=source_backed_required,
            official_enabled=True,
            commercial_enabled=_estimate_commercial_fallback_enabled(),
        )
        draft = procurement.draft
        trusted_evidence.extend(procurement.evidence)
        draft["procurement_report"] = procurement.report

    final_estimate = build_estimate_action(
        prompt,
        draft,
        verified_evidence=trusted_evidence,
        scope_verified=False,
        questions_enabled=False,
    )
    # Post-materialization: keep AI prices for rows without commercial
    # evidence.  Only zero out rows that have no price at all.
    sanitized = deepcopy(final_estimate["data"])
    rebuilt_prices = False
    for section_index, section in enumerate(sanitized.get("sections", [])):
        for position_index, position in enumerate(section.get("positions", [])):
            if position.get("price_evidence"):
                # Commercial research found a verified price — keep it.
                continue
            code = str(position.get("code") or "")
            proposal_key = code or f"row:{section_index}:{position_index}"
            proposed = proposed_prices.get(proposal_key)
            if proposed and _positive_decimal(proposed):
                # Keep MiMo's AI-estimated price.
                position["price"] = proposed
                position["source"] = "ai_estimate"
                comment = str(position.get("comment") or "").strip()
                note = "Цена — профессиональная оценка MiMo."
                if note not in comment:
                    position["comment"] = f"{comment} {note}".strip()
            elif not _positive_decimal(position.get("price")):
                position["price"] = "0.00"
                position["sum"] = "0.00"
            rebuilt_prices = True
    if rebuilt_prices:
        assumptions = sanitized.get("assumptions")
        if not isinstance(assumptions, list):
            assumptions = []
        assumptions = [
            item
            for item in assumptions
            if "строки без цены сохранены для доисследования" not in str(item).casefold()
        ]
        assumptions.extend([
            "Цены рассчитаны AI (MiMo) на основе профессиональных знаний. Проверьте перед договором.",
        ])
        sanitized["assumptions"] = assumptions
        final_estimate = build_estimate_action(
            prompt,
            sanitized,
            verified_evidence=trusted_evidence,
            scope_verified=False,
            questions_enabled=False,
        )
    if source_backed_required:
        compact = _compact_source_backed_action(
            final_estimate,
            prompt,
            verified_evidence=trusted_evidence,
        )
        if compact is not None:
            final_estimate = compact
    return [
        final_estimate if item is estimate else item
        for item in normalized
    ]


def _estimate_materialization_requested(
    messages: List[Dict[str, str]],
    actions: list[dict],
) -> bool:
    return is_estimate_request(messages) or any(
        isinstance(action, dict) and action.get("type") == "create_estimate"
        for action in actions
    )


def _estimate_price_research_outcome(actions: list[dict]) -> dict:
    estimate = next(
        (item for item in actions if item.get("type") == "create_estimate"),
        None,
    )
    pricing_status = str(
        (estimate or {}).get("data", {}).get("pricing_status") or "needs_input"
    )
    if pricing_status in {"source_backed", "verified"}:
        return work_summary_event(
            "source_retrieval",
            "Актуальные цены подтверждены источниками",
            status="completed",
        )
    if pricing_status == "preliminary":
        total = str((estimate or {}).get("data", {}).get("totals", {}).get("total") or "0")
        if _positive_decimal(total):
            return work_summary_event(
                "source_retrieval",
                "Предварительные цены рассчитаны по профессиональным допущениям",
                status="completed",
            )
        return work_summary_event(
            "source_retrieval",
            "Часть цен подтверждена; неизвестные строки исключены из итога",
            status="completed",
        )
    return work_summary_event(
        "source_retrieval",
        "Не удалось подтвердить цены — нужны уточнения",
        status="failed",
    )


async def _stream_estimate_materialization(
    messages: List[Dict[str, str]],
    actions: list[dict],
) -> AsyncIterator[tuple[dict | None, list[dict] | None]]:
    """Emit observable price-research facts around estimate materialization."""

    trace_requested = _estimate_materialization_requested(messages, actions)
    if trace_requested:
        yield work_summary_event(
            "source_retrieval",
            "Подбираю актуальные региональные цены",
            status="active",
        ), None
    materialized = await _materialize_estimate_actions(messages, actions)
    if trace_requested:
        yield _estimate_price_research_outcome(materialized), None
        estimate = next(
            (item for item in materialized if item.get("type") == "create_estimate"),
            None,
        )
        if estimate is not None:
            yield work_summary_event(
                "calculation",
                "Суммы сметы рассчитаны сервером",
                status="completed",
            ), None
            yield work_summary_event(
                "verification",
                "Структура и итог сметы проверены",
                status="completed",
            ), None
    yield None, materialized


def _estimate_result_message(actions: list[dict]) -> str:
    estimate = next((item for item in actions if item.get("type") == "create_estimate"), None)
    status = str((estimate or {}).get("data", {}).get("estimate_status") or "needs_input")
    if status == "verified":
        return "Проверенная смета рассчитана и подготовлена для сохранения в редакторе."
    if status == "source_backed":
        return (
            "Индивидуальная смета рассчитана по последним опубликованным региональным "
            "ценам ФГИС ЦС и подготовлена для редактора. Объёмы требуют проверки по проекту."
        )
    if status == "preliminary":
        total = str((estimate or {}).get("data", {}).get("totals", {}).get("total") or "0")
        if _positive_decimal(total):
            return (
                "Предварительная смета рассчитана по профессиональным допущениям "
                "и готова к редактированию. Проверьте допущения и цены перед договором."
            )
        return (
            "Индивидуальная ведомость сформирована, но не все строки имеют подходящий "
            "актуальный региональный источник. Неподтверждённые цены не включены."
        )
    return (
        "Готовой сметы пока нет: не сформирован достаточный индивидуальный состав "
        "либо не найдены подтверждённые цены. Нужны уточнения: подтвердите состав работ, "
        "объёмы и возможность подбора актуальных региональных цен."
    )


async def analyze_estimate(estimate_data: dict) -> dict:
    """AI analysis of an estimate."""
    prompt = f"""Проанализируй смету и дай рекомендации:
- Названия: {estimate_data.get('title', '')}
- Клиент: {estimate_data.get('client', '')}
- Итого: {estimate_data.get('total', '0')} ₽
- Разделы: {len(estimate_data.get('sections', []))}

Позиции:
"""
    for s in estimate_data.get("sections", []):
        prompt += f"\n{s.get('title', '')}:\n"
        for p in s.get("positions", []):
            prompt += f"  - {p.get('name', '')}: {p.get('quantity', '0')} {p.get('unit', '')} × {p.get('price', '0')} ₽ = {p.get('sum', '0')} ₽\n"

    prompt += (
        "\nДай краткий междисциплинарный анализ: сметчик — состав и единицы; "
        "прораб — технология и пропуски; бухгалтер — НДС, налоговый режим и "
        "арифметика; строительный юрист — договорные риски. Не называй "
        "рекомендацию юридическим заключением и не выдумывай нормативные ссылки."
    )
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        task_type="analyze",
        system="Ты — эксперт по строительным сметам. Анализируй данные, находи ошибки, предлагай оптимизации.",
    )


async def generate_document_content(doc_type: str, context: str = "") -> dict:
    """AI generation of document content."""
    type_labels = {
        "contract": "договор подряда", "act": "акт выполненных работ",
        "proposal": "коммерческое предложение", "report": "технический отчёт",
        "memo": "служебная записка", "letter": "деловое письмо",
    }
    label = type_labels.get(doc_type, "документ")
    prompt = f"Составь готовый к редактированию документ: {label}."
    if context:
        prompt += f"\nКонтекст: {context}"
    if doc_type == "contract":
        prompt += """
\nЭто должен быть самостоятельный договор строительного подряда, а не пересказ
сметы или коммерческое предложение. Смету укажи отдельным приложением,
определяющим работы и цену. Обязательно используй нумерованные разделы:
преамбула; предмет; техническая документация и приложения; сроки и этапы;
цена, НДС и расчёты; права и обязанности; материалы; изменения и дополнительные
работы; сдача-приёмка; качество и гарантия; ответственность; форс-мажор;
расторжение; споры; юридически значимые сообщения; заключительные положения;
реквизиты и подписи. Учитывай статьи 740, 743 и 753 ГК РФ. Не придумывай
персональные данные, реквизиты, сроки, ставки неустойки и подсудность: ставь
явную пометку «Требуется заполнить».
"""
    elif doc_type == "proposal":
        prompt += """
\nОформи коммерческое предложение как деловой документ: адресат и отправитель;
дата и номер; предмет; краткое понимание задачи; состав и границы предложения;
таблица работ/материалов; цена и НДС; сроки; порядок оплаты; срок действия;
допущения и исключения; гарантии; следующий шаг; реквизиты и подпись. Не
называй предложение договором и не добавляй неизвестные факты.
"""
    prompt += """
\nОформление должно быть пригодно для PDF/DOCX и соответствовать деловому стилю
ГОСТ Р 7.0.97-2025. Верни только чистый HTML-фрагмент для визуального редактора:
h1/h2/h3, p, ol/ul, table, strong/em. Не возвращай Markdown, обратные кавычки,
html/head/body, CSS, JavaScript или пояснения вне документа.
"""
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        task_type="generate",
        system=(
            "Ты — ассистент по российским строительным документам. Отделяй "
            "проверенные факты от незаполненных данных, не выдумывай реквизиты "
            "и не выдавай шаблон за индивидуальное юридическое заключение. "
            "Следуй формату ответа из пользовательского запроса и не возвращай "
            "служебные JSON-действия."
        ),
        system_only=True,
    )


async def suggest_search(query: str) -> dict:
    """AI search suggestions."""
    prompt = f"Пользователь ищет: '{query}'. Предложи 3-5 релевантных запросов."
    return await chat_completion(
        [{"role": "user", "content": prompt}],
        task_type="suggest",
        system="Ты — поисковый ассистент. Предлагай релевантные запросы.",
    )


async def _call_ai(
    provider: dict,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    *,
    previous_response_id: Optional[str] = None,
    background: bool = False,
    policy: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    execution_mode: str = "fast",
) -> dict:
    """Internal: call AI API."""
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)

    if provider.get("protocol") == "home_factory":
        from app.home_factory_response import get_home_factory_response_client

        parsed = await get_home_factory_response_client().submit(
            full,
            idempotency_key=idempotency_key,
            execution_mode=execution_mode,
        )
        content = str(parsed.get("content") or "")
        if not content.strip():
            raise ValueError("provider_returned_empty_content")
        actions = _extract_actions(content)
        return {
            "content": content,
            "reasoning": "",
            "actions": actions,
            "status": "ready" if actions else "idle",
            "provider": "home_factory",
            "model": str(parsed.get("model") or "kolibri"),
            "speed_ms": provider.get("speed_ms", 0),
            "tool_events": parsed.get("tool_events", []),
            "factory": {
                key: parsed.get(key)
                for key in (
                    "task_id",
                    "attempt_id",
                    "fencing_token",
                    "executor_node",
                    "verifier_node",
                    "artifact_sha256",
                    "binding_sha256",
                    "result_reference",
                )
            },
        }

    if provider.get("protocol") == "codex_cli":
        from app.codex_cli_provider import get_codex_cli_provider

        parsed = await get_codex_cli_provider().invoke(
            full,
            policy=policy,
        )
        content = str(parsed.get("content") or "")
        if not content.strip():
            raise ValueError("provider_returned_empty_content")
        actions = _extract_actions(content)
        return {
            "content": content,
            "reasoning": "",
            "actions": actions,
            "status": "ready" if actions else "idle",
            "provider": _provider_id(provider),
            "model": str(parsed.get("model") or provider["model"]),
            "speed_ms": provider.get("speed_ms", 0),
            "tool_events": parsed.get("tool_events", []),
        }

    if provider.get("protocol") == "responses":
        from app.openai_responses import create_response

        parsed = await create_response(
            provider,
            full,
            previous_response_id=previous_response_id,
            background=background,
            policy=policy,
            idempotency_key=idempotency_key,
        )
        content = str(parsed.get("content") or "")
        effective_background = background or bool(
            policy and policy.get("mode") == "deep" and policy.get("background")
        )
        if effective_background and parsed.get("status") in {"queued", "in_progress"}:
            return {
                "content": "",
                "reasoning": "",
                "actions": [],
                "status": str(parsed.get("status")),
                "provider": _provider_id(provider),
                "model": provider["model"],
                "speed_ms": provider.get("speed_ms", 0),
                "response_id": parsed.get("id"),
                "tool_events": parsed.get("tool_events", []),
            }
        if not content.strip():
            raise ValueError("provider_returned_empty_content")
        return {
            "content": content,
            "reasoning": str(parsed.get("reasoning_summary") or ""),
            "actions": _extract_actions(content),
            "status": "ready" if _extract_actions(content) else "idle",
            "provider": _provider_id(provider),
            "model": provider["model"],
            "speed_ms": provider.get("speed_ms", 0),
            "response_id": parsed.get("id"),
            "tool_events": parsed.get("tool_events", []),
        }

    headers = {"Content-Type": "application/json"}
    if provider["key"]:
        headers["Authorization"] = f"Bearer {provider['key']}"

    async with httpx.AsyncClient(timeout=AI_TIMEOUT, **_provider_client_options(provider)) as client:
        response = await client.post(
            provider["url"],
            json={"model": provider["model"], "messages": full},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    if not content.strip():
        raise ValueError("provider_returned_empty_content")
    actions = _extract_actions(content)

    return {
        "content": content,
        "reasoning": reasoning,
        "actions": actions,
        "status": "ready" if actions else "idle",
        "provider": _provider_id(provider),
        "model": provider["model"],
        "speed_ms": provider.get("speed_ms", 0),
    }


async def chat_completion_stream(
    messages: List[Dict[str, str]],
    task_type: str = "chat",
    *,
    system: Optional[str] = None,
    raw_json_output: bool = False,
    previous_response_id: Optional[str] = None,
    background: bool = False,
    policy: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    run_id: Optional[str] = None,
):
    """Yield token deltas followed by one structured, reasoning-free final chunk.

    Provider streams are deliberately normalised here instead of being passed
    through verbatim.  Besides keeping the public stream stable across
    OpenAI-compatible providers, this prevents provider-specific private
    reasoning fields from leaking into the client response.
    """
    image_result = await _image_completion_if_requested(messages, policy, run_id=run_id)
    if image_result is not None:
        if image_result["status"] == "ready":
            yield work_summary_event("tool_execution", "Создаю изображение", status="active")
            yield work_summary_event(
                "artifact_verification",
                "Формат, размер и контрольная сумма изображения проверены",
                status="completed",
                provider=image_result["provider"],
                model=image_result["model"],
                artifact_type="image",
                artifact_id=image_result["actions"][0]["data"]["id"],
            )
        yield {
            "content": image_result["content"],
            "done": True,
            "actions": image_result["actions"],
            "status": image_result["status"],
            "provider": image_result["provider"],
            "model": image_result["model"],
            "fallback_used": False,
            **({
                "error_code": image_result["error_code"],
                "recoverable": image_result["recoverable"],
                "capability": image_result["capability"],
            } if image_result.get("error_code") else {}),
        }
        return
    if system is None and _is_self_description_request(messages):
        result = _capability_self_description()
        if _chat_shortcuts_enabled():
            yield {"content": result["content"], "done": False}
            yield {
                "content": "",
                "done": True,
                "actions": [],
                "status": "idle",
                "provider": result["provider"],
                "model": result["model"],
                "fallback_used": False,
            }
            return
    fast_local = None if raw_json_output or system is not None else _simple_chat_fast_path(messages)
    if fast_local is not None:
        yield {"content": fast_local["content"], "done": False}
        yield {
            "content": "",
            "done": True,
            "actions": [],
            "status": "idle",
            "provider": "local_dialog",
            "model": "kolibri",
            "fallback_used": False,
        }
        return
    estimate_requested = is_estimate_request(messages)
    flow_instruction = (
        estimate_execution_instruction(estimate_request_text(messages) or latest_user_text(messages))
        if estimate_requested and not raw_json_output
        else ""
    )
    composed_system = _compose_system_prompt(system)
    if flow_instruction:
        composed_system = f"{composed_system}\n\n{flow_instruction}"
    full_messages = [{"role": "system", "content": composed_system}] + messages
    providers_to_try = _get_providers_for_task(task_type)

    for provider_index, provider in enumerate(providers_to_try):
        provider_id = _provider_id(provider)
        provider_model = str(provider.get("model") or "")
        if provider.get("protocol") != "home_factory":
            # Direct transports begin their observable attempt here.  Home
            # emits its own route/task lifecycle only after the Control Plane
            # has actually selected and accepted that work.
            yield work_summary_event(
                "provider_route",
                "Подключаю доступного исполнителя",
                status="active",
                provider=provider_id,
                model=provider_model,
            )
        emitted_content = False
        content_parts: list[str] = []
        structured_output = False
        visible_buffer = ""
        response_meta: dict = {}
        try:
            stream_kwargs: dict[str, object] = {}
            if previous_response_id:
                stream_kwargs["previous_response_id"] = previous_response_id
            if background:
                stream_kwargs["background"] = background
            if policy is not None:
                stream_kwargs["policy"] = policy
            if idempotency_key:
                stream_kwargs["idempotency_key"] = idempotency_key
            # Correlation is supported only by the bounded local CLI and Home
            # factory transports; never smuggle it into external REST payloads.
            if (
                provider.get("protocol") in {"codex_cli", "home_factory"}
                and run_id
            ):
                stream_kwargs["run_id"] = run_id
            if provider.get("protocol") == "home_factory":
                stream_kwargs["execution_mode"] = provider.get(
                    "execution_mode"
                ) or _factory_execution_mode(
                    task_type,
                    estimate_requested,
                )
                # A professional estimate is already a typed Codex task whose
                # output is validated and deterministically recalculated by
                # Kolibri.  Sending that verified JSON through a second
                # Codex+Mimo reducer can truncate it, change its schema or lose
                # the completed draft if the reducer route is unavailable.
                # Deep collaboration remains available for non-estimate work.
                stream_kwargs["collaboration"] = bool(
                    not estimate_requested
                    and policy
                    and policy.get("mode") == "deep"
                )
            stream = (
                _stream_ai(provider, full_messages, **stream_kwargs)
                if stream_kwargs
                else _stream_ai(provider, full_messages)
            )
            async for chunk in _bounded_provider_stream(
                stream,
                _estimate_provider_budget_seconds() if estimate_requested else None,
            ):
                if chunk.get("work_summary") or chunk.get("tool_event"):
                    yield chunk
                    continue
                if chunk.get("response_meta"):
                    response_meta.update(chunk["response_meta"])
                    continue
                token = chunk.get("content") or ""
                if not token:
                    # The upstream [DONE] marker is replaced with the
                    # structured final event emitted below.
                    continue
                emitted_content = True
                content_parts.append(token)
                if raw_json_output:
                    yield {"content": token, "done": False}
                    continue
                if structured_output:
                    continue

                visible_buffer += token
                stripped = visible_buffer.lstrip()
                fence_index = visible_buffer.lower().find("```json")
                if stripped.startswith("{"):
                    structured_output = True
                    visible_buffer = ""
                elif fence_index >= 0:
                    prefix = visible_buffer[:fence_index]
                    if prefix:
                        yield {"content": prefix, "done": False}
                    structured_output = True
                    visible_buffer = ""
                elif len(visible_buffer) > 7:
                    safe_prefix = visible_buffer[:-7]
                    visible_buffer = visible_buffer[-7:]
                    if safe_prefix:
                        yield {"content": safe_prefix, "done": False}

            effective_background = background or bool(
                policy and policy.get("mode") == "deep" and policy.get("background")
            )
            if (
                not emitted_content
                and effective_background
                and response_meta.get("status") in {"queued", "in_progress"}
            ):
                _record_provider_success(provider)
                yield {
                    "content": "",
                    "done": True,
                    "actions": [],
                    "status": response_meta["status"],
                    "provider": provider_id,
                    "model": provider_model,
                    "fallback_used": provider_index > 0,
                    "response_id": response_meta.get("id"),
                }
                return
            if not emitted_content:
                raise ValueError("provider_returned_empty_content")

            _record_provider_success(provider)
            yield work_summary_event(
                "response_received",
                "Ответ исполнителя получен",
                status="completed",
                provider=provider_id,
                model=provider_model,
            )
            candidate_actions = _extract_actions("".join(content_parts))
            if estimate_requested and not raw_json_output and not candidate_actions:
                raise TechnologyCardError("technology_card_required")
            actions: list[dict] = []
            if not raw_json_output:
                async for trace_event, materialized in _stream_estimate_materialization(
                    messages, candidate_actions
                ):
                    if trace_event is not None:
                        yield trace_event
                    if materialized is not None:
                        actions = materialized
            if structured_output and actions:
                action_type = actions[0].get("type")
                summary = {
                    "create_estimate": _estimate_result_message(actions),
                    "create_document": "Документ подготовлен для сохранения в текущем проекте.",
                }.get(action_type, "Результат подготовлен для сохранения в текущем проекте.")
                yield {
                    "content": summary,
                    "done": False,
                }
            elif visible_buffer:
                yield {"content": visible_buffer, "done": False}
            final = {
                "content": "",
                "done": True,
                "actions": actions,
                "status": "ready" if actions else "idle",
                "provider": _provider_id(provider),
                "model": provider.get("model", ""),
                "fallback_used": provider_index > 0,
            }
            if response_meta.get("id"):
                final["response_id"] = response_meta["id"]
            yield final
            return
        except Exception as e:
            if _safe_failure_kind(e) == "codex_cli_cancelled":
                yield {
                    "content": "",
                    "done": True,
                    "actions": [],
                    "status": "cancelled",
                    "provider": provider_id,
                    "model": provider_model,
                    "fallback_used": provider_index > 0,
                }
                return
            estimate_budget_exceeded = estimate_requested and isinstance(e, TimeoutError)
            if not estimate_budget_exceeded:
                _record_provider_failure(provider, e)
            yield provider_failure_event(
                provider,
                e,
                will_retry=not emitted_content and provider_index < len(providers_to_try) - 1,
            )
            print(
                f"[AI STREAM FALLBACK] provider={_provider_id(provider)} "
                f"failure={_safe_failure_kind(e)} trying_next={not emitted_content}"
            )
            if (
                estimate_requested
                and structured_output
                and not _extract_actions("".join(content_parts))
            ):
                # The invalid structured payload was hidden from the user; it
                # is safe to try the next estimator instead of accepting a
                # technology-free estimate.
                continue
            if emitted_content:
                interrupted_actions: list[dict] = []
                async for trace_event, materialized in _stream_estimate_materialization(
                    messages, _extract_actions("".join(content_parts))
                ):
                    if trace_event is not None:
                        yield trace_event
                    if materialized is not None:
                        interrupted_actions = materialized
                yield {
                    "content": "",
                    "done": True,
                    "actions": interrupted_actions,
                    "status": "ready" if estimate_requested else "incomplete",
                    "provider": _provider_id(provider),
                    "model": provider.get("model", ""),
                    "fallback_used": provider_index > 0,
                    "error_code": "provider_stream_interrupted",
                }
                return
            continue

    local_actions: list[dict] = []
    async for trace_event, materialized in _stream_estimate_materialization(
        messages, []
    ):
        if trace_event is not None:
            yield trace_event
        if materialized is not None:
            local_actions = materialized
    if local_actions:
        local_estimate = next(
            (
                item
                for item in local_actions
                if item.get("type") == "create_estimate"
            ),
            None,
        )
        local_summary = (
            "Подготовлен запрос на уточнение данных для сметы"
            if str(
                (local_estimate or {}).get("data", {}).get("estimate_status")
                or "needs_input"
            ) == "needs_input"
            else "Подготовлен локальный детерминированный результат"
        )
        yield work_summary_event(
            "response_received",
            local_summary,
            status="completed",
            provider="local_contract",
            model="deterministic-estimate-v1",
        )
    yield {
        "content": _estimate_result_message(local_actions) if local_actions else (
            "Не удалось завершить ответ через доступные маршруты. Повторите запрос — он будет направлен другому исполнителю."
        ),
        "done": True,
        "actions": local_actions,
        "status": "ready" if local_actions else "error",
        "provider": "local_contract" if local_actions else "none",
        "model": "deterministic-estimate-v1" if local_actions else "none",
        "fallback_used": bool(providers_to_try),
        "error_code": "provider_routes_exhausted",
    }


async def _stream_ai(
    provider: dict,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    *,
    previous_response_id: Optional[str] = None,
    background: bool = False,
    policy: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    run_id: Optional[str] = None,
    execution_mode: str = "fast",
    collaboration: bool | None = None,
):
    """Internal: stream tokens from AI API using httpx async streaming."""
    full = []
    if system:
        full.append({"role": "system", "content": system})
    full.extend(messages)

    if provider.get("protocol") == "home_factory":
        from app.home_factory_response import get_home_factory_response_client

        use_collaboration = (
            bool(policy and policy.get("mode") == "deep")
            if collaboration is None
            else collaboration
        )
        async for event in get_home_factory_response_client().stream(
            full,
            run_id=run_id,
            idempotency_key=idempotency_key,
            collaboration=use_collaboration,
            execution_mode=execution_mode,
        ):
            yield event
        return

    if provider.get("protocol") == "codex_cli":
        from app.codex_cli_provider import get_codex_cli_provider

        async for event in get_codex_cli_provider().stream(
            full,
            policy=policy,
            run_id=run_id,
        ):
            yield event
        return

    if provider.get("protocol") == "responses":
        from app.openai_responses import stream_response

        async for event in stream_response(
            provider,
            full,
            previous_response_id=previous_response_id,
            background=background,
            policy=policy,
            idempotency_key=idempotency_key,
        ):
            yield event
        return

    headers = {"Content-Type": "application/json"}
    if provider["key"]:
        headers["Authorization"] = f"Bearer {provider['key']}"

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(999999, connect=10.0),
        **_provider_client_options(provider),
    ) as client:
        async with client.stream(
            "POST",
            provider["url"],
            json={"model": provider["model"], "messages": full, "stream": True},
            headers=headers,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    yield {"content": "", "done": True}
                    return
                try:
                    obj = json.loads(data_str)
                    delta = obj["choices"][0].get("delta", {})
                    token = delta.get("content") or delta.get("reasoning_content") or ""
                    if token:
                        yield {"content": token, "done": False}
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def _extract_actions(content: str) -> list:
    """Extract fenced, raw or prose-embedded JSON actions safely."""
    actions: list[dict] = []
    objects: list[dict] = []
    seen: set[str] = set()

    candidates = [part.split("```")[0].strip() for part in content.split("```json")[1:]]
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            candidates.append(json.dumps(obj, ensure_ascii=False, sort_keys=True))

    for json_str in candidates:
        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        fingerprint = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        objects.append(obj)

    for obj in objects:
        action_type = obj.get("action", "")
        if action_type == "create_estimate":
            candidate = dict(obj)
            candidate.pop("action", None)
            # Native technology cards and finished Solo estimates are both
            # interpreted against the real user prompt later.  No empty-prompt
            # normalisation or domain template is allowed here.
            if isinstance(candidate.get("technology_card"), dict) or isinstance(candidate.get("sections"), list):
                actions.append({
                    "type": "create_estimate",
                    "label": "Подготовить смету из технологической карты",
                    "data": candidate,
                })
        elif action_type == "create_document":
            document_text = str(obj.get("content") or "").strip()
            paragraphs = [part.strip() for part in document_text.splitlines() if part.strip()]
            safe_content = "".join(f"<p>{escape(part)}</p>" for part in paragraphs)
            document_data = {
                "title": obj.get("title", "Документ"),
                "type": obj.get("type", "custom"),
                "content": safe_content,
            }
            for field, limit in (("client", 240), ("project", 240), ("template", 120), ("estimate_id", 128)):
                value = obj.get(field)
                if isinstance(value, str) and 0 < len(value) <= limit:
                    document_data[field] = value
            variables = obj.get("variables")
            if isinstance(variables, dict) and len(variables) <= 100 and all(
                isinstance(key, str) and 0 < len(key) <= 120
                and isinstance(value, str) and len(value) <= 10_000
                for key, value in variables.items()
            ):
                document_data["variables"] = variables
            actions.append({
                "type": "create_document",
                "label": f"Создать {obj.get('title', 'документ')}",
                "data": document_data,
            })
    return actions
