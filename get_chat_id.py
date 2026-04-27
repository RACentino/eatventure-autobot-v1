"""
Helper script to get your Telegram chat ID.

Steps:
1. Start your bot by messaging @YourBotName on Telegram.
2. Send any message to your bot (for example, "Hello").
3. Run this script: python get_chat_id.py
4. Copy your chat_id from the output.
5. Paste it into config.py as TELEGRAM_CHAT_ID.
"""

import sys

import requests

import config

REQUEST_TIMEOUT = 10


def main():
    bot_token = str(config.TELEGRAM_BOT_TOKEN or "").strip()
    if not bot_token:
        print("ERROR: No bot token found in config.py or environment")
        print("Please set EATVENTURE_TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN")
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

    if not data.get("ok"):
        print(f"Telegram API error: {data.get('description', data)}")
        return 1

    updates = data.get("result", [])
    if not updates:
        print("No messages found!")
        print("\nPlease:")
        print("1. Open Telegram and find your bot")
        print("2. Send any message to your bot (e.g., 'Hello')")
        print("3. Run this script again")
        return 0

    print("Found messages!\n")
    chat_ids = set()
    for update in updates:
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict) or "id" not in chat:
            continue

        chat_id = str(chat["id"])
        if chat_id in chat_ids:
            continue

        chat_ids.add(chat_id)
        print(f"Chat ID: {chat_id}")
        print(f"Chat Type: {chat.get('type', 'unknown')}")
        if "username" in chat:
            print(f"Username: @{chat['username']}")
        if "first_name" in chat:
            print(f"Name: {chat['first_name']}")
        print("-" * 40)

    if chat_ids:
        example_chat_id = sorted(chat_ids)[0]
        print("\nOK: Copy one of the Chat IDs above")
        print("OK: Paste it into config.py as TELEGRAM_CHAT_ID")
        print("\nExample:")
        print(f'TELEGRAM_CHAT_ID = "{example_chat_id}"')
    else:
        print("No chat IDs were present in the Telegram updates response.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
