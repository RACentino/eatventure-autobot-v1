import logging
import queue
import threading

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token, chat_id, enabled=True):
        self.bot_token = str(bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.timeout = 5
        self.enabled = bool(enabled and self.bot_token and self.chat_id)
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = None
        self._session = requests.Session() if self.enabled else None

        if self.enabled:
            self._thread = threading.Thread(target=self._worker_loop, name="telegram_notifier", daemon=True)
            self._thread.start()
            logger.info("Telegram notifier enabled")
        else:
            logger.warning("Telegram notifier disabled")

    def _worker_loop(self):
        while not self._stop.is_set():
            try:
                message = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self._send_message_now(message)
            finally:
                self._queue.task_done()

    def _send_message_now(self, message):
        if not self.enabled or self._session is None:
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }

            response = self._session.post(url, json=data, timeout=self.timeout)
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

    def send_message(self, message):
        if not self.enabled:
            return False

        self._queue.put(str(message))
        return True

    def close(self):
        if not self.enabled:
            return
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        if self._session is not None:
            self._session.close()
            self._session = None

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
