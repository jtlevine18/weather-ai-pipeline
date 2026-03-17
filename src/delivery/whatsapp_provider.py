"""WhatsApp delivery provider via Twilio WhatsApp sandbox. Dry-run by default."""

from __future__ import annotations
import logging
from typing import Any, Dict

from config import DeliveryConfig

log = logging.getLogger(__name__)


class WhatsAppProvider:
    def __init__(self, config: DeliveryConfig):
        self.config = config

    def _format_whatsapp(self, alert: Dict[str, Any]) -> str:
        condition = alert.get("condition", "clear").replace("_", " ").title()
        temp      = alert.get("temperature")
        rain      = alert.get("rainfall")
        advisory  = alert.get("advisory_local") or alert.get("advisory_en", "")
        station   = alert.get("station_id", "")

        lines = [
            f"🌾 *Kerala/TN Weather Advisory*",
            f"📍 Station: {station}",
            f"🌤️ Condition: *{condition}*",
        ]
        if temp is not None:
            lines.append(f"🌡️ Temperature: {temp:.1f}°C")
        if rain is not None and rain > 0:
            lines.append(f"🌧️ Rainfall: {rain:.1f}mm")
        lines.append(f"\n{advisory}")
        return "\n".join(lines)

    async def send(self, alert: Dict[str, Any], recipient) -> Dict[str, Any]:
        message = self._format_whatsapp(alert)

        if not self.config.live_delivery:
            log.info("[DRY-RUN WA] To %s: %s...", recipient.phone, message[:60])
            return {"status": "dry_run", "message": message}

        if not (self.config.twilio_account_sid and self.config.twilio_auth_token):
            return {"status": "skipped", "message": "no_credentials"}

        try:
            from twilio.rest import Client
            client = Client(self.config.twilio_account_sid, self.config.twilio_auth_token)
            msg = client.messages.create(
                body=message,
                from_=f"whatsapp:{self.config.twilio_from}",
                to=f"whatsapp:{recipient.phone}",
            )
            return {"status": "sent", "message": message, "sid": msg.sid}
        except Exception as exc:
            log.error("WhatsApp failed to %s: %s", recipient.phone, exc)
            return {"status": "failed", "message": str(exc)}
