"""Twilio SMS delivery provider. Dry-run by default."""

from __future__ import annotations
import logging
from typing import Any, Dict

from config import DeliveryConfig

log = logging.getLogger(__name__)

MAX_SMS_CHARS = 160


class TwilioProvider:
    def __init__(self, config: DeliveryConfig):
        self.config = config

    def _format_sms(self, alert: Dict[str, Any]) -> str:
        condition = alert.get("condition", "clear").replace("_", " ").upper()
        temp      = alert.get("temperature")
        rain      = alert.get("rainfall")
        advisory  = alert.get("advisory_local") or alert.get("advisory_en", "")

        header = f"[WEATHER] {condition}"
        if temp is not None:
            header += f" {temp:.0f}C"
        if rain is not None and rain > 0:
            header += f" {rain:.0f}mm rain"

        # Truncate to fit SMS
        body = f"{header}\n{advisory}"
        if len(body) > MAX_SMS_CHARS:
            body = body[:MAX_SMS_CHARS - 3] + "..."
        return body

    async def send(self, alert: Dict[str, Any], recipient) -> Dict[str, Any]:
        message = self._format_sms(alert)

        if not self.config.live_delivery:
            log.info("[DRY-RUN SMS] To %s: %s", recipient.phone, message[:60])
            return {"status": "dry_run", "message": message}

        if not (self.config.twilio_account_sid and self.config.twilio_auth_token):
            log.warning("Twilio credentials not set — skipping SMS to %s", recipient.phone)
            return {"status": "skipped", "message": "no_credentials"}

        try:
            from twilio.rest import Client
            client = Client(self.config.twilio_account_sid, self.config.twilio_auth_token)
            msg = client.messages.create(
                body=message,
                from_=self.config.twilio_from,
                to=recipient.phone,
            )
            log.info("SMS sent to %s: SID=%s", recipient.phone, msg.sid)
            return {"status": "sent", "message": message, "sid": msg.sid}
        except Exception as exc:
            log.error("Twilio SMS failed to %s: %s", recipient.phone, exc)
            return {"status": "failed", "message": str(exc)}
