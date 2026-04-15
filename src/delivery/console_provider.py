"""Console delivery provider — prints advisory to terminal."""

from __future__ import annotations
from typing import Any, Dict

from rich.console import Console
from rich.panel   import Panel
from rich.text    import Text

console = Console()

CONDITION_EMOJI = {
    "heavy_rain":    "🌧️",
    "moderate_rain": "🌦️",
    "heat_stress":   "🌡️",
    "drought_risk":  "🌵",
    "frost_risk":    "❄️",
    "high_wind":     "💨",
    "foggy":         "🌫️",
    "clear":         "☀️",
}


class ConsoleProvider:
    async def send(self, alert: Dict[str, Any], recipient) -> Dict[str, Any]:
        condition = alert.get("condition", "clear")
        emoji     = CONDITION_EMOJI.get(condition, "🌤️")
        station   = alert.get("station_id", "?")
        temp      = alert.get("temperature")
        rain      = alert.get("rainfall")
        lang      = alert.get("language", "en")
        advisory  = alert.get("advisory_local") or alert.get("advisory_en", "")

        temp_str  = f"{temp:.1f}°C" if temp is not None else "N/A"
        rain_str  = f"{rain:.1f}mm" if rain is not None else "N/A"

        # Weekly advisories are station-level (one advisory fans out to every
        # farmer in that station's registry). Don't print a specific farmer's
        # name in the sample panel — it misleads readers into thinking the
        # advisory is personalized. The delivery_log row still records the
        # recipient's phone; only the visible debug panel is station-scoped.
        body = Text()
        body.append(f"{emoji} {condition.upper().replace('_', ' ')}\n", style="bold yellow")
        body.append(f"Station: {station}  |  Lang: {lang}\n", style="dim")
        body.append(f"Temp: {temp_str}  Rain: {rain_str}\n\n")
        body.append(advisory, style="green")

        console.print(Panel(body, title=f"[bold cyan]Advisory — {station}[/bold cyan]",
                             border_style="cyan"))

        return {"status": "sent", "message": advisory[:80]}
