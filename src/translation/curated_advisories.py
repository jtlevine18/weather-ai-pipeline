"""
Curated advisory matrix: crop × growth phase × weather condition.
Used by the rule-based fallback provider.
"""

from __future__ import annotations
from typing import Dict

# Structure: condition -> crop_keyword -> advisory
ADVISORY_MATRIX: Dict[str, Dict[str, str]] = {
    "heavy_rain": {
        "rice":       "Heavy rain expected. Ensure drainage channels are clear to prevent waterlogging. Delay fertilizer application by 2-3 days.",
        "paddy":      "Heavy rain expected. Ensure drainage channels are clear to prevent waterlogging. Delay fertilizer application by 2-3 days.",
        "coconut":    "Strong winds with heavy rain. Secure young palms and check for root rot in low-lying areas.",
        "rubber":     "Postpone tapping operations. Heavy rain can dilute latex and increase risk of bark disease.",
        "coffee":     "Heavy rain may cause berry drop. Ensure slopes have proper drainage and avoid herbicide application.",
        "cotton":     "Protect open bolls from rain damage. Suspend harvesting until conditions improve.",
        "millets":    "Ensure field drainage. Waterlogging can cause root rot in millets.",
        "sugarcane":  "Check for waterlogging in furrows. Excess moisture can cause stalk rot.",
        "banana":     "Stake plants to prevent lodging in strong winds. Monitor for Sigatoka disease spread.",
        "default":    "Heavy rain forecast. Avoid field operations and ensure proper drainage.",
    },
    "moderate_rain": {
        "rice":       "Moderate rain expected — good conditions for transplanting. Monitor water levels.",
        "paddy":      "Moderate rain expected — good conditions for transplanting. Monitor water levels.",
        "coconut":    "Moderate rain is beneficial. Good time for fertilizer application when soil is moist.",
        "rubber":     "Delay tapping until 2 hours after rain stops to avoid diluted latex.",
        "coffee":     "Moderate rain is beneficial during flowering and berry development.",
        "cotton":     "Ensure boll weevil monitoring during humid conditions.",
        "default":    "Moderate rain expected. Plan field operations accordingly.",
    },
    "heat_stress": {
        "rice":       "High temperature stress. Ensure adequate irrigation to prevent spikelet sterility.",
        "paddy":      "High temperature stress. Ensure adequate irrigation to prevent spikelet sterility.",
        "coconut":    "Water stress alert. Apply 40-50 liters of water per palm. Mulch the basin.",
        "coffee":     "Heat stress can cause flower drop. Increase irrigation frequency to 3 times per week.",
        "cotton":     "Heat stress may affect boll setting. Apply 25mm irrigation if rainfall is absent.",
        "millets":    "Drought-tolerant millets can handle heat, but ensure soil moisture above 30%.",
        "vegetables": "Shade sensitive crops. Apply mulch to retain soil moisture.",
        "default":    "Heat stress conditions. Irrigate early morning and monitor for wilting.",
    },
    "drought_risk": {
        "rice":       "Drought risk detected. Maintain 5cm standing water. Switch to AWD irrigation method.",
        "paddy":      "Drought risk detected. Maintain 5cm standing water. Switch to AWD irrigation method.",
        "coconut":    "Soil moisture deficit. Apply basin irrigation of 200 liters every 4 days.",
        "rubber":     "Drought stress can reduce latex yield 20-30%. Deep watering every 5 days is advised.",
        "coffee":     "Pre-blossom drought affects flowering. Irrigation critical in December-January.",
        "groundnut":  "Pod filling stage is critical — do not let soil dry below 50% FC.",
        "sugarcane":  "Grand growth phase needs 100mm/week equivalent. Drip irrigation recommended.",
        "default":    "Drought risk. Prioritize irrigation for critical-stage crops.",
    },
    "frost_risk": {
        "coffee":     "Frost risk! Cover nursery seedlings with straw or polythene. Avoid irrigation before frost.",
        "cardamom":   "Frost can damage cardamom capsules. Use wind-breaks and cover plants overnight.",
        "pepper":     "Protect pepper vines from frost. Overhead irrigation can help on frost nights.",
        "tea":        "Light frost can damage tender shoots. Delay harvesting until temperature rises above 5°C.",
        "vegetables": "Cover frost-sensitive crops overnight. Harvest mature crops before frost.",
        "default":    "Frost risk detected. Protect sensitive crops and seedlings overnight.",
    },
    "high_wind": {
        "coconut":    "High winds can cause frond breakage and nut drop. Secure loose fronds.",
        "banana":     "Secure banana plants with bamboo stakes. High winds can cause pseudostem breakage.",
        "arecanut":   "High winds may cause bunch drop in arecanut. Check and tighten supports.",
        "default":    "High wind advisory. Secure plants, trellises, and shade nets.",
    },
    "foggy": {
        "coffee":     "Foggy conditions favor coffee berry borer. Monitor for pest activity.",
        "cardamom":   "High humidity with fog creates ideal conditions for fungal diseases. Apply preventive fungicide.",
        "rice":       "Fog can increase incidence of blast disease. Monitor crop carefully.",
        "default":    "Foggy conditions. Monitor for fungal disease development.",
    },
    "clear": {
        "rice":       "Clear weather — good conditions for weeding and fertilizer application.",
        "paddy":      "Clear weather — good conditions for weeding and fertilizer application.",
        "coconut":    "Favorable conditions for harvesting and farm operations.",
        "rubber":     "Good tapping conditions. Optimal latex flow expected.",
        "coffee":     "Good conditions for crop monitoring and pest scouting.",
        "cotton":     "Ideal conditions for harvesting open bolls.",
        "millets":    "Good conditions for threshing and drying.",
        "default":    "Clear and favorable conditions for most field operations.",
    },
}


def get_advisory(condition: str, crop_context: str) -> str:
    """
    Lookup advisory for a given condition and crop context.
    Matches the first crop keyword found in crop_context.
    """
    condition_map = ADVISORY_MATRIX.get(condition, ADVISORY_MATRIX.get("clear", {}))

    crop_lower = crop_context.lower()
    for keyword, advisory in condition_map.items():
        if keyword != "default" and keyword in crop_lower:
            return advisory

    return condition_map.get("default",
        "Monitor weather conditions closely and adjust farm operations accordingly.")
