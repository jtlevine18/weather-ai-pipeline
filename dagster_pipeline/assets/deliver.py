"""Step 6: Deliver advisories via console/SMS/WhatsApp."""

import asyncio
from dagster import asset, AssetExecutionContext, AssetIn
from typing import Any, Dict, List

from config import PipelineConfig
from src.delivery import MultiChannelDelivery, DEFAULT_RECIPIENTS, DeliveryChannel


@asset(
    ins={"agricultural_alerts": AssetIn()},
    description="Delivery records — console output and optional SMS/WhatsApp.",
    group_name="pipeline",
)
def delivery_log(
    context: AssetExecutionContext,
    agricultural_alerts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    config = PipelineConfig()
    channels = [DeliveryChannel.CONSOLE]
    delivery = MultiChannelDelivery(config.delivery, channels)

    alert_map = {a["station_id"]: a for a in agricultural_alerts}

    async def _run():
        all_logs = []
        for recipient in DEFAULT_RECIPIENTS:
            alert = alert_map.get(recipient.station_id)
            if alert is None:
                continue
            logs = await delivery.deliver(alert, recipient)
            all_logs.extend(logs)
        return all_logs

    logs = asyncio.run(_run())
    context.log.info(f"Delivered {len(logs)} messages")
    return logs
