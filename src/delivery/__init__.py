"""
Step 6: Multi-channel delivery — console, Twilio SMS, WhatsApp.
"""

from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from config import DeliveryConfig

log = logging.getLogger(__name__)


class DeliveryChannel(str, Enum):
    CONSOLE   = "console"
    SMS       = "sms"
    WHATSAPP  = "whatsapp"


@dataclass
class Recipient:
    name:       str
    phone:      str
    station_id: str
    language:   str = "en"
    alt_m:      Optional[float] = None


# Default recipients for demo (one per state)
DEFAULT_RECIPIENTS: List[Recipient] = [
    Recipient("Arun Kumar",    "+919876543210", "KL_TVM", "ml"),
    Recipient("Biju Thomas",   "+919876543211", "KL_COK", "ml"),
    Recipient("Murugan P",     "+919876543220", "TN_TNJ", "ta"),
    Recipient("Selvi R",       "+919876543221", "TN_MDU", "ta"),
    Recipient("Ravi S",        "+919876543222", "TN_CHN", "ta"),
    Recipient("Suresh Nair",   "+919876543212", "KL_NLB", "ml"),
]


class MultiChannelDelivery:
    def __init__(self, config: DeliveryConfig, channels: Optional[List[DeliveryChannel]] = None):
        from src.delivery.console_provider   import ConsoleProvider
        from src.delivery.twilio_provider    import TwilioProvider
        from src.delivery.whatsapp_provider  import WhatsAppProvider

        self.config   = config
        self.channels = channels or [DeliveryChannel.CONSOLE]
        self._providers = {
            DeliveryChannel.CONSOLE:  ConsoleProvider(),
            DeliveryChannel.SMS:      TwilioProvider(config),
            DeliveryChannel.WHATSAPP: WhatsAppProvider(config),
        }

    async def deliver(self, alert: Dict[str, Any], recipient: Recipient) -> List[Dict[str, Any]]:
        """Deliver an alert through all configured channels. Returns delivery log entries."""

        results = []
        for channel in self.channels:
            provider = self._providers.get(channel)
            if provider is None:
                continue
            try:
                result = await provider.send(alert, recipient)
                results.append({
                    "id":         str(uuid.uuid4()),
                    "alert_id":   alert.get("id"),
                    "station_id": alert.get("station_id"),
                    "channel":    channel.value,
                    "recipient":  recipient.phone,
                    "status":     result.get("status", "sent"),
                    "message":    result.get("message", ""),
                })
            except Exception as exc:
                log.warning("Delivery failed on %s: %s", channel, exc)
                results.append({
                    "id":         str(uuid.uuid4()),
                    "alert_id":   alert.get("id"),
                    "station_id": alert.get("station_id"),
                    "channel":    channel.value,
                    "recipient":  recipient.phone,
                    "status":     "failed",
                    "message":    str(exc),
                })
        return results
