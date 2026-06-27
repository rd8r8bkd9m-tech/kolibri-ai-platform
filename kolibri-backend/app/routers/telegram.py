"""Telegram bot scaffold — webhook endpoint for Kolibri commands."""
import os
import hmac
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "kolibri-webhook-secret")


def _verify_webhook(request: Request) -> bool:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not TELEGRAM_WEBHOOK_SECRET:
        return True
    return hmac.compare_digest(secret, TELEGRAM_WEBHOOK_SECRET)


@router.post("/webhook")
async def telegram_webhook(request: Request):
    if not _verify_webhook(request):
        raise HTTPException(403, "Invalid webhook secret")

    body = await request.json()

    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    user = message.get("from", {})

    if text.startswith("/start"):
        return _reply(chat_id, "Добро пожаловать в Колибри! 🐦\n\nДоступные команды:\n/estimate — создать смету\n/document — создать документ\n/status — статус системы\n/help — помощь")

    if text.startswith("/status"):
        return _reply(chat_id, "Система работает нормально.\nАгенты: 6 (4 активных)\nНоды: 20 (15 healthy)\nЗадачи: 20 (5 running)")

    if text.startswith("/help"):
        return _reply(chat_id, "Колибри — AI-ассистент для смет и документов.\n\nИспользуйте веб-интерфейс для полного функционала:\nhttps://kolibri.ai")

    if text.startswith("/estimate"):
        return _reply(chat_id, "Создание сметы доступно через веб-интерфейс.\nОткройте https://kolibri.ai/#/estimates")

    if text.startswith("/document"):
        return _reply(chat_id, "Создание документов доступно через веб-интерфейс.\nОткройте https://kolibri.ai/#/documents")

    return _reply(chat_id, f"Получено: {text}\n\nИспользуйте /help для списка команд.")


def _reply(chat_id: int, text: str) -> dict:
    """Return Telegram sendMessage payload."""
    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }


@router.get("/info")
async def bot_info():
    return {
        "bot_configured": bool(TELEGRAM_BOT_TOKEN),
        "webhook_secret_set": bool(TELEGRAM_WEBHOOK_SECRET),
        "commands": [
            {"command": "start", "description": "Начать работу"},
            {"command": "status", "description": "Статус системы"},
            {"command": "estimate", "description": "Создать смету"},
            {"command": "document", "description": "Создать документ"},
            {"command": "help", "description": "Помощь"},
        ],
    }
