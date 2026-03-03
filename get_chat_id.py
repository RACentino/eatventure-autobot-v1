"""Utility script to discover Telegram chat IDs for the configured bot token."""

import argparse
import sys
from typing import Iterable

import requests

import config


def _load_token(cli_token: str | None) -> str:
    # FIX: Support explicit CLI token override and sanitize whitespace.
    token = (cli_token or config.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        raise ValueError("No bot token found. Provide --token or set TELEGRAM_BOT_TOKEN in config.py")
    return token


def _extract_chat_ids(updates: Iterable[dict]) -> dict[int, dict]:
    # FIX: Defensively parse nested response objects to avoid KeyError crashes.
    chats: dict[int, dict] = {}
    for update in updates:
        message = update.get("message") if isinstance(update, dict) else None
        if not isinstance(message, dict):
            continue

        chat = message.get("chat")
        if not isinstance(chat, dict):
            continue

        chat_id = chat.get("id")
        if isinstance(chat_id, int):
            chats[chat_id] = chat
    return chats


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Telegram updates and print discovered chat IDs")
    parser.add_argument("--token", help="Telegram bot token override")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    try:
        token = _load_token(args.token)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    url = f"https://api.telegram.org/bot{token}/getUpdates"

    try:
        # FIX: Use explicit timeout and raise_for_status to fail fast on transport errors.
        response = requests.get(url, timeout=max(1.0, args.timeout))
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        print(f"ERROR: request failed: {exc}")
        return 1
    except ValueError as exc:
        print(f"ERROR: invalid JSON response: {exc}")
        return 1

    if not data.get("ok"):
        print(f"ERROR: Telegram API returned failure payload: {data}")
        return 1

    updates = data.get("result", [])
    if not isinstance(updates, list) or not updates:
        print("No messages found. Send a message to your bot and run this script again.")
        return 0

    chats = _extract_chat_ids(updates)
    if not chats:
        print("No chat IDs found in updates payload.")
        return 0

    print("Found chat IDs:\n")
    for chat_id, chat in sorted(chats.items()):
        print(f"Chat ID: {chat_id}")
        print(f"Chat Type: {chat.get('type', 'unknown')}")
        username = chat.get("username")
        first_name = chat.get("first_name")
        if username:
            print(f"Username: @{username}")
        if first_name:
            print(f"Name: {first_name}")
        print("-" * 40)

    example_chat_id = next(iter(chats))
    print("\n✅ Copy one of the Chat IDs above")
    print("✅ Paste it into config.py as TELEGRAM_CHAT_ID")
    print('\nExample:\nTELEGRAM_CHAT_ID = "{}"'.format(example_chat_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
