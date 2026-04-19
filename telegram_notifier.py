import requests
import logging

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token, chat_id, enabled=True):
        self.bot_token = str(bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.timeout = 5
        self.enabled = bool(enabled and self.bot_token and self.chat_id)

        if self.enabled:
            logger.info("Telegram notifier enabled")
        else:
            logger.warning("Telegram notifier disabled")

    def send_message(self, message):
        if not self.enabled:
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }

            response = requests.post(url, json=data, timeout=self.timeout)
            response_data = response.json()

            if response.ok and response_data.get("ok"):
                logger.debug("Telegram message sent successfully")
                return True
            logger.error(
                "Failed to send Telegram message: status=%s description=%s",
                response.status_code,
                response_data.get("description", "unavailable"),
            )
            return False
        except (requests.RequestException, ValueError) as exc:
            logger.error("Error sending Telegram message: %s", exc)
            return False

    def notify_bot_started(self):
        message = "🤖 <b>Bot Started</b>"
        self.send_message(message)

    def notify_bot_stopped(self):
        message = "⏹️ <b>Bot Stopped</b>"
        self.send_message(message)

    def notify_new_level(self, level_number, time_spent):
        minutes = int(time_spent // 60)
        seconds = int(time_spent % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"

        message = f"{level_number}. restaurant completed! Time spent: {time_str}"
        self.send_message(message)

    def notify_level_milestone(self, total_levels):
        message = f"📊 <b>Milestone Reached!</b>\nTotal cities completed: {total_levels}"
        self.send_message(message)
