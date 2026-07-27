"""
Helper script to get your Telegram chat ID.

Steps:
1. Start your bot by messaging @YourBotName on Telegram.
2. Send any message to your bot (for example, "Hello").
3. Set EATVENTURE_TELEGRAM_BOT_TOKEN in your environment.
4. Run this script: python get_chat_id.py
5. Copy a chat ID from the output into EATVENTURE_TELEGRAM_CHAT_ID.
"""

import sys
from typing import Any

import requests

import config

REQUEST_TIMEOUT = 10


def _redact_token(text: Any, token: str) -> str:
    text = str(text)
    if token:
        return text.replace(token, "<redacted-token>")
    return text


def _terminal_safe_text(value: Any) -> str:
    return repr(str(value))[1:-1]


def _extract_chat(update: Any) -> dict[str, Any] | None:
    if not isinstance(update, dict):
        return None
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    chat_id = chat.get("id")
    if isinstance(chat_id, bool) or not isinstance(chat_id, int):
        return None
    return chat


def _print_no_messages_instructions() -> None:
    print("No messages found!")
    print("\nPlease:")
    print("1. Open Telegram and find your bot")
    print("2. Send any message to your bot (e.g., 'Hello')")
    print("3. Run this script again")


def _print_chat(chat: dict[str, Any]) -> None:
    chat_id = chat["id"]
    print(f"Chat ID: {chat_id}")
    print(f"Chat Type: {_terminal_safe_text(chat.get('type', 'unknown'))}")
    if "username" in chat:
        print(f"Username: @{_terminal_safe_text(chat['username'])}")
    if "first_name" in chat:
        print(f"Name: {_terminal_safe_text(chat['first_name'])}")
    print("-" * 40)


def main() -> int:
    bot_token = str(config.TELEGRAM_BOT_TOKEN or "").strip()
    if not bot_token:
        print("ERROR: EATVENTURE_TELEGRAM_BOT_TOKEN is not set")
        return 1

    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        print(f"Error contacting Telegram: {exc.__class__.__name__}")
        return 1
    except ValueError as exc:
        print(f"Error decoding Telegram response: {exc}")
        return 1

    if not isinstance(data, dict):
        print("Telegram API error: response was not an object")
        return 1
    if not data.get("ok"):
        description = _redact_token(data.get("description", data), bot_token)
        print(f"Telegram API error: {_terminal_safe_text(description)}")
        return 1

    updates = data.get("result", [])
    if not isinstance(updates, list):
        print("Telegram API error: updates response was not a list")
        return 1
    if not updates:
        _print_no_messages_instructions()
        return 0

    print("Found messages!\n")
    chat_ids: set[int] = set()
    for update in updates:
        chat = _extract_chat(update)
        if chat is None:
            continue

        chat_id = chat["id"]
        if chat_id in chat_ids:
            continue

        chat_ids.add(chat_id)
        _print_chat(chat)

    if chat_ids:
        example_chat_id = min(chat_ids)
        print("\nOK: Copy one of the Chat IDs above")
        print("OK: Set EATVENTURE_TELEGRAM_CHAT_ID in your environment")
        print("\nPowerShell example:")
        print(f'$env:EATVENTURE_TELEGRAM_CHAT_ID = "{example_chat_id}"')
    else:
        print("No chat IDs were present in the Telegram updates response.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
