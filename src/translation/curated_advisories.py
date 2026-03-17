"""
Curated advisory matrix for Kerala and Tamil Nadu smallholder crops.
Covers: coconut, rubber, rice/paddy, coffee, cardamom, pepper, tea,
        banana, arecanut, tapioca, cotton, millets, groundnut, sugarcane,
        turmeric, vegetables, cashew.
"""

from __future__ import annotations
from typing import Dict

# Structure: condition -> crop_keyword -> advisory
ADVISORY_MATRIX: Dict[str, Dict[str, str]] = {

    "heavy_rain": {
        "rice":       "Heavy rain expected — ensure all drainage channels are clear to prevent waterlogging above 10 cm. Delay urea top-dressing by 3-4 days; excess water leaches nitrogen. Watch for blast disease (diamond-shaped lesions) in humid conditions after rain subsides.",
        "paddy":      "Heavy rain expected — ensure all drainage channels are clear to prevent waterlogging above 10 cm. Delay urea top-dressing by 3-4 days; excess water leaches nitrogen. Watch for blast disease (diamond-shaped lesions) in humid conditions after rain subsides.",
        "coconut":    "Strong winds with heavy rain can snap fronds and cause premature nut drop. Secure young palms with bamboo supports. After rain, check low-lying basins for root rot; improve drainage if water stagnates more than 24 hours.",
        "rubber":     "Postpone tapping for 24-48 hours after heavy rain — wet bark causes latex dilution and increases risk of abnormal leaf fall (Phytophthora). Inspect tapping panels for water accumulation; apply Bordeaux paste to cuts if mold appears.",
        "coffee":     "Heavy rain during berry development can cause berry drop and promote coffee berry disease (CBD). Ensure slopes have clear drainage furrows. Avoid pesticide application; postpone until foliage is dry. Monitor for leaf rust spread in humid canopy.",
        "cardamom":   "Heavy rain promotes Katte disease and capsule rot in cardamom. Clear drainage around clumps immediately. If capsules show water-soaked lesions, apply Bordeaux mixture (1%) at 10-day intervals. Avoid walking through wet beds to prevent disease spread.",
        "pepper":     "Heavy rain causes pepper berry drop and foot rot (Phytophthora capsici) in waterlogged soils. Raise soil around vine base and improve drainage. Apply copper oxychloride 3g/L as preventive spray on stems and soil. Postpone climbing support work.",
        "tea":        "Heavy rain is generally beneficial but monitor for blister blight (Exobasidium vexans) on tender shoots. If white blisters appear, spray copper fungicide immediately. Delay plucking by 1-2 days after heavy rain for shoot quality recovery.",
        "banana":     "Stake banana plants before rain — pseudostem is vulnerable to lodging in strong winds. After rain, monitor for Sigatoka leaf spot; spray Propiconazole 1ml/L if yellow streaks appear. Check bunch covers are secure to prevent rain damage.",
        "arecanut":   "Heavy rain increases koleroga (Phytophthora) in arecanut — the main threat during monsoon. Remove diseased bunches immediately. Spray Bordeaux mixture (1%) on bunches and leaf axils at monthly intervals starting June. Ensure good drainage around palms.",
        "tapioca":    "Tapioca tolerates rain well but waterlogging causes tuber rot. Ensure ridges or mounds are intact for drainage. If stems show soft rot at base, remove affected plants and apply lime to soil. Delay harvesting during prolonged wet spells.",
        "cotton":     "Protect open bolls from rain damage — stained cotton loses 20-30% market value. Harvest all open bolls immediately before expected heavy rain. Drain waterlogged furrows within 24 hours. Spray NAA 20 ppm after rain to reduce flower and boll shedding.",
        "millets":    "Ensure field bunds are intact to prevent waterlogging — millets cannot tolerate submergence beyond 24 hours. After rain, watch for ergot (Claviceps) in sorghum and downy mildew in pearl millet. Delay harvesting until crop dries.",
        "groundnut":  "Heavy rain during pod filling can cause aflatoxin and collar rot. Ensure furrow drainage is clear. If rain is persistent at harvest, dig pods and dry under cover immediately — do not leave mature pods in wet soil beyond 3 days.",
        "sugarcane":  "Check furrow drainage — waterlogging beyond 48 hours causes stalk rot in sugarcane. After rain, apply 20 kg urea/ha to compensate nitrogen leaching. If cane lodges, tie bundles upright within 3 days to prevent rooting at nodes.",
        "turmeric":   "Turmeric rhizomes are highly susceptible to rhizome rot (Pythium) in waterlogged conditions. Ensure raised bed drainage is functional. Remove and destroy affected plants. Apply Trichoderma-enriched compost around healthy plants as preventive biocontrol.",
        "vegetables": "Drain beds within 6 hours — most vegetables are killed by waterlogging faster than field crops. Cover nursery seedlings. Delay transplanting by 3-4 days after heavy rain. Apply copper-based fungicide preventively as humidity promotes damping off.",
        "cashew":     "Heavy rain during flushing and flowering causes anthracnose and tea mosquito bug damage. Spray Carbendazim 1g/L at flowering stage. Ensure orchard drainage to prevent collar rot. Do not prune during wet weather as cuts invite fungal infection.",
        "default":    "Heavy rain forecast. Clear all field and garden drainage channels immediately. Avoid fertilizer and pesticide application for 48 hours. Protect harvested produce from moisture. Monitor for disease after rain subsides.",
    },

    "moderate_rain": {
        "rice":       "Moderate rain is ideal for rice tillering — maintain 5 cm standing water. Good time to apply second nitrogen dose (urea 40 kg/ha) if crop is at 30-35 days after transplanting. Monitor for brown planthopper if humidity stays high.",
        "paddy":      "Moderate rain is ideal for paddy tillering — maintain 5 cm standing water. Good time to apply second nitrogen dose (urea 40 kg/ha) if crop is at 30-35 days after transplanting. Monitor for brown planthopper if humidity stays high.",
        "coconut":    "Moderate rain is beneficial — ideal time for fertilizer application (NPK 13:0:45 at 1 kg/palm/year in two splits). Soil is moist for absorption. Check for rhinoceros beetle damage at crown; treat with Chlorpyrifos 0.05% if fronds show notch-cutting.",
        "rubber":     "Resume tapping 2 hours after rain stops to avoid diluted latex. Check stimulation panels — rain can wash away ethephon. Good conditions for yield boosting clonal material application. Monitor for secondary leaf fall (Oidium) in young plantations.",
        "coffee":     "Moderate rain during flowering (October-November) triggers synchronised bloom — the most critical stage. Avoid any disturbance to canopy. After blossom, apply 20:20:0 fertilizer to support berry development. Monitor for white stem borer in wet conditions.",
        "cardamom":   "Moderate rain benefits cardamom — moist soil is ideal for panicle emergence. Apply Potassium (MOP 50 g/plant) after rain for capsule filling. Maintain shade trees to prevent excess direct sunlight on wet foliage which worsens Katte spread.",
        "pepper":     "Good rain benefits pepper at berry development — apply potassium nitrate 1% foliar spray to improve berry size and quality. Monitor for pollu beetle; if seeds are hollow, use Quinalphos 25EC at 2 ml/L. Ensure vine supports are stable.",
        "banana":     "Moderate rain is ideal for banana bunch development. Apply NPK 100:40:150 g/plant split dose. Cover bunches with blue polythene bags to improve finger filling and protect from pests. Monitor for bunchy top virus — remove infected suckers immediately.",
        "coconut":    "Moderate rain is beneficial. Apply NPK fertilizer while soil is moist for better uptake. Check for bud rot — if crown leaves wilt and emit foul smell, remove affected tissue and apply Bordeaux paste.",
        "sugarcane":  "Moderate rain during grand growth phase (June-September) is ideal. Top-dress with urea 100 kg/ha split into two applications. Earthing up after rain stabilizes stalks against wind. Monitor for top borer — if dead heart appears, apply Chlorpyrifos granules.",
        "millets":    "Moderate rain provides good germination conditions — ideal for direct sowing of sorghum or cumbu. Sow immediately while soil is moist. Apply basal NPK 20:40:20 kg/ha. Expect good tiller development.",
        "default":    "Moderate rain expected — favorable conditions. Apply pending top-dressing fertilizers while soil is moist. Plan spray operations for early morning once foliage dries. Weed flush expected in 5-7 days — prepare for inter-cultivation.",
    },

    "heat_stress": {
        "rice":       "High temperature above 35°C during rice flowering causes spikelet sterility — 1% yield loss per degree above 33°C. Maintain 7-10 cm standing water to cool root zone. Flowering occurs 10 AM-noon; no spray remedy for heat sterility. Irrigate in evenings.",
        "paddy":      "High temperature above 35°C during paddy flowering causes spikelet sterility — 1% yield loss per degree above 33°C. Maintain 7-10 cm standing water to cool root zone. Flowering occurs 10 AM-noon; no spray remedy for heat sterility. Irrigate in evenings.",
        "coconut":    "Heat stress above 38°C reduces coconut nut set and causes premature nut fall. Apply 40-50 liters of water per palm weekly. Mulch basin with coconut husks (15 cm) to retain soil moisture and reduce root zone temperature.",
        "rubber":     "Extreme heat reduces latex flow and increases tapping panel dryness. Shift tapping to early morning (5-6 AM) when temperature is lowest. Apply bark stimulant carefully — heat stress increases tapping panel damage risk. Reduce stimulation frequency.",
        "coffee":     "Heat above 34°C causes flower bud abortion in coffee. Increase irrigation to 3 times per week. Apply 1% potassium chloride foliar spray to improve heat tolerance. Shade management is critical — reduce shade removal in April-May during pre-blossom period.",
        "cardamom":   "Cardamom is a shade-loving crop sensitive to heat above 35°C — capsule abortion increases in open sunlight. Maintain adequate shade (40-50%). Irrigate drip system at 2-litre/plant/day minimum. Mulch thickly with green leaves to reduce soil temperature.",
        "pepper":     "Heat stress causes flower drop and poor berry set in pepper. Irrigate vine base daily during heat wave. Apply mulch around base to keep roots cool. Avoid any pruning during heat — open cuts dry rapidly and invite pests.",
        "banana":     "Banana bunches exposed to heat above 40°C can develop sun scald — finger skin turns brown, reducing market value. Cover bunches with dry leaves or blue bags. Maintain irrigation at 20-25 liters/plant/day. Avoid exposing corm to direct sun.",
        "turmeric":   "Heat stress reduces turmeric rhizome development. Irrigate in evening hours. Apply thick mulch (10 cm) of paddy straw to maintain soil moisture and cool root zone. Spray 0.5% potassium chloride to improve heat tolerance of foliage.",
        "vegetables": "Shade heat-sensitive crops with 50% shade net. Apply mulch to retain soil moisture. Irrigate early morning and late evening. Avoid transplanting during heat wave — wait for cooler conditions. Apply anti-transpirant spray (Kaolin 5%) to reduce leaf temperature.",
        "default":    "Heat stress conditions. Irrigate in early morning and late evening to minimize evaporation. Apply mulch around plant base. Foliar spray of 0.5% KCl improves crop heat tolerance. Avoid field operations between 11 AM and 3 PM.",
    },

    "drought_risk": {
        "rice":       "Drought risk — maintain minimum 5 cm standing water using alternate wetting and drying (AWD). Install perforated pipe to check: irrigate when water drops 15 cm below soil. Drought at flowering causes most severe yield loss — this stage cannot be skipped.",
        "paddy":      "Drought risk — maintain minimum 5 cm standing water using alternate wetting and drying (AWD). Install perforated pipe to check: irrigate when water drops 15 cm below soil. Drought at flowering causes most severe yield loss — this stage cannot be skipped.",
        "coconut":    "Apply basin irrigation of 200 liters per palm every 4-5 days during drought. Soil moisture deficit causes button shedding (immature nut drop) — visible within 3-4 weeks of stress onset. Mulch basin heavily with coconut husks. Foliar spray of KNO3 1% helps.",
        "rubber":     "Drought reduces latex yield by 20-30%. Deep watering (50 liters/tree every 5 days) is preferred over frequent shallow watering. Reduce tapping frequency from d/2 to d/3 to minimize stress on trees. Avoid bark stimulant application during drought.",
        "coffee":     "Pre-blossom drought (October) prevents synchronised flowering — the key quality determinant. Apply supplemental irrigation to trigger uniform blossom. Post-monsoon drought affects bean size — maintain drip at 10 liters/plant/day through berry development.",
        "cardamom":   "Cardamom requires consistent moisture — drought causes panicle drying and capsule abortion. Irrigate by drip or flood at 3-5 day intervals. Apply mulch of green leaves 15-20 cm thick. Drought-stressed plants are more susceptible to thrips and mites.",
        "pepper":     "Drought at flowering and berry set in pepper causes significant yield loss. Irrigate vine base at 15-day intervals (10 liters/vine/application). Foliar spray of 1% KCl improves drought tolerance. Maintain shade tree canopy to reduce vine moisture stress.",
        "banana":     "Banana is highly drought-sensitive — 5-7 days of water stress at bunch emergence reduces bunch weight by 20-30%. Maintain irrigation at 20 liters/plant/day minimum. Mulch with 10 kg dry leaves per plant. Avoid exposing roots when soil is dry.",
        "groundnut":  "Pod filling is the most critical stage — do not let soil dry below 50% field capacity. Irrigate every 7-8 days. Pod development continues for 30-40 days after flowering; each missed irrigation at this stage reduces filled pod percentage by 10-15%.",
        "sugarcane":  "Grand growth phase (June-September) needs equivalent of 100 mm/week. Apply drip irrigation at 80% ETc if water is limited. Drought at this stage reduces final cane weight — yield loss is 500-700 kg/ha per day of water stress. Mulch between rows.",
        "turmeric":   "Turmeric needs consistent moisture for rhizome development. Drought causes premature leaf senescence and small rhizomes. Irrigate every 7-10 days. Mulch with paddy straw 10 cm thick. Apply potassium-rich fertilizer (SOP 50 g/plant) to improve drought tolerance.",
        "default":    "Drought risk. Prioritize irrigation for crops at critical stages. Apply mulch to reduce soil moisture loss. Use furrow or drip irrigation to maximize efficiency. Foliar spray of 2% urea provides nutrients when roots cannot absorb from dry soil.",
    },

    "cyclone_risk": {
        "coconut":    "Cyclone warning — secure immature bunches with rope to adjacent fronds. Remove dry fronds that can become projectiles. After cyclone, remove all damaged fronds at base to prevent infection. Apply Bordeaux paste on cut surfaces. Check palm crown for bud rot.",
        "rubber":     "Secure young rubber trees (under 3 years) with bamboo stakes before cyclone. After the storm, assess trees for bark splitting — apply Bordeaux paste immediately to all wounds. Windrowed branches create disease pressure; remove promptly.",
        "banana":     "Remove all banana bunches that are 75% mature or more before cyclone makes landfall. Pseudostems cannot survive cyclone-force winds. After the storm, assess ratoon damage and cut destroyed stems at ground level. New suckers will regenerate.",
        "pepper":     "Lash pepper vines tightly to standards before cyclone. Remove trailing vines from ground. After cyclone, reattach displaced vines promptly — ground contact causes foot rot within days. Apply copper fungicide to all damaged sections.",
        "arecanut":   "Arecanut palms suffer severe frond and bunch loss in cyclones. Remove loose fronds. After the cyclone, remove damaged bunches at once to prevent rot spread. Apply paste of Bordeaux mixture on all cut surfaces. Young palms need re-staking.",
        "default":    "Cyclone warning. Secure all farm structures, shade nets, and irrigation lines. Harvest mature crops immediately where possible. After cyclone, assess damage and prioritize clearing drainage channels before beginning crop recovery work.",
    },

    "monsoon_onset": {
        "rice":       "Pre-monsoon preparation — prepare nursery beds now. Raise seedlings 21-25 days before expected transplanting date. Apply FYM 5 tonnes/ha to main field and plough 2-3 times for good puddle. First rain marks start of kharif sowing window.",
        "coconut":    "Monsoon onset is the ideal time for coconut fertilizer application — apply NPK mixture (1.3 kg urea + 2.0 kg superphosphate + 1.5 kg muriate of potash per palm per year, split into two applications). Dig pits for new planting — fill with FYM and topsoil.",
        "rubber":     "First monsoon rain triggers uniform leaf flush in rubber. Spray fungicide (Metalaxyl-M 4g/L) before flush to prevent abnormal leaf fall (Phytophthora). Begin tapping preparation — clean panels, sharpen knives, and check bark thickness.",
        "pepper":     "Apply first monsoon fertilizer dose to pepper (20:20:20 NPK at 50g/vine). Tie new runner shoots to standards. Monsoon onset triggers rapid vine growth. Apply organic mulch (green leaves) around vine base before heavy rain begins.",
        "cardamom":   "Monsoon onset triggers panicle emergence in cardamom. Apply full fertilizer dose (NPK 75:75:150 g/plant/year, split equally June and September). Spray Bordeaux mixture before heavy rain season to prevent Katte and capsule rot.",
        "default":    "Monsoon onset expected. Complete all pre-sowing preparations — field ploughing, drainage channel clearing, seedbed preparation. Apply organic manure before first rain for best incorporation. Stock up on fungicide and fertilizer before roads become difficult.",
    },

    "high_wind": {
        "coconut":    "High winds cause frond breakage and green nut drop. Secure young palms (under 5 years) with bamboo supports. After wind event, remove all broken fronds at base; apply Bordeaux paste on cuts. Count nut drop to estimate yield impact.",
        "banana":     "High winds cause pseudostem snap and bunch damage — the most common weather injury to banana. Stake all plants with 3-meter bamboo poles on the windward side. Remove bunches more than 60% mature immediately. After lodging, prop up plants within 6 hours.",
        "arecanut":   "High winds cause bunch drop in arecanut before nuts are fully mature. Check and tighten bunch supports (cloth bands). After wind damage, collect fallen nuts for early processing — they are usable if harvested within 48 hours of drop.",
        "rubber":     "Wind causes bark abrasion on tapping panels, inviting disease. Do not tap during or immediately after high wind. Inspect trees for wounds after wind event; apply protective paint to all bark damage.",
        "pepper":     "Wind displaces pepper vines from standards — check and re-tie all displaced shoots within 24 hours. Soil-touching vines develop foot rot rapidly in wet conditions. Stake all free-hanging vines before expected wind.",
        "coffee":     "High winds cause coffee flower and berry drop. Windbreaks (silver oak or Grevillea) reduce wind damage significantly. After wind event, spray 2% urea foliar to support recovery of stressed branches.",
        "default":    "High wind advisory. Secure shade nets, irrigation pipes, and plant supports. Stake tall-growing crops. Harvest mature produce before wind event if possible. After wind, inspect crops for damage and apply fungicide to broken plant parts.",
    },

    "foggy": {
        "coffee":     "Fog and prolonged humidity favor coffee berry borer (Hypothenemus hampei) — the most damaging coffee pest. Set mass trapping devices (ethanol:methanol 1:3 lure) and inspect berries weekly. Also monitor for leaf rust (orange powder on underside of leaves).",
        "cardamom":   "High humidity with fog creates near-ideal conditions for Phytophthora capsule rot. Apply Bordeaux mixture (1%) preventively before prolonged foggy periods. Ensure canopy air circulation by selective shade tree pruning.",
        "tea":        "Fog promotes blister blight on tea tender shoots — the most economically damaging disease in hill tea. Apply copper fungicide (Cupravit 0.25%) at 7-day intervals during persistent cloudy-foggy spells. Delay plucking by 1 day after fog to allow leaf surface to dry.",
        "pepper":     "Foggy humid conditions favor Phytophthora foot rot spread through splash dispersal. Apply Ridomil 2g/L as soil drench around vine base. Avoid working in plantation during fog as footwear spreads the pathogen.",
        "rice":       "Fog increases incidence of rice blast and sheath blight. Monitor for diamond-shaped lesions on leaves (blast) or brown sheath lesions at water level (sheath blight). Spray Tricyclazole 6g/10L for blast; Validamycin 2ml/L for sheath blight.",
        "rubber":     "Fog delays morning tapping — tap at least 1 hour after fog clears to avoid latex dilution and panel infection. Phytophthora bark rot spreads in foggy conditions; monitor for dark water-soaked patches on tapping panels.",
        "default":    "Foggy conditions with high humidity. Monitor all crops closely for fungal disease development. Apply preventive copper-based fungicide. Avoid overhead irrigation. Improve air circulation where possible through canopy management.",
    },

    "clear": {
        "rice":       "Clear weather — good conditions for weeding, inter-cultivation, and fertilizer application. If crop is at panicle initiation stage, apply potash (MOP 30 kg/ha) for grain filling. Check for stem borer — dead heart in vegetative stage or white ear at panicle stage.",
        "paddy":      "Clear weather — good conditions for weeding, inter-cultivation, and fertilizer application. If crop is at panicle initiation stage, apply potash (MOP 30 kg/ha) for grain filling. Check for stem borer — dead heart in vegetative stage or white ear at panicle stage.",
        "coconut":    "Favorable conditions for harvesting, crown cleaning, and farm operations. Apply fertilizer in two split pits dug at 1.5m radius from trunk. Check for red palm weevil damage — if oozing sap with fermented smell, treat with Chlorpyrifos injection.",
        "rubber":     "Good tapping conditions — optimal latex flow in dry morning weather. Ensure clean cut with sharp knife at 30° angle, removing minimum bark. Apply stimulant (Ethephon 2.5%) at recommended intervals. Check for tapping panel dryness syndrome.",
        "coffee":     "Good conditions for crop monitoring and pest scouting. Use this window for spray operations — apply systemic fungicide for berry disease prevention. Check for white stem borer entry holes at base of main stem; apply Chlorpyrifos paste.",
        "cardamom":   "Clear weather is good for harvest and post-harvest operations. Harvest capsules when 75-80% turn green-yellow. Cure immediately using flue-curing or electric dryers at 50°C. Delay curing reduces green colour and market grade.",
        "pepper":     "Ideal conditions for harvesting pepper when spikes turn from green to yellow-green. Harvest berry clusters when 1-2 berries per spike turn red. Sun dry on clean mats for 5-7 days to reach 10% moisture for black pepper. For white pepper, ret in water for 7 days.",
        "banana":     "Good conditions for bunch care — apply bunch cover (blue polythene bag) to develop finger size and protect from pests. Check for bract mosaic virus (brick red streaks on bracts) and Panama wilt (yellowing of lower leaves). Harvest bunches when fingers are 75% full.",
        "tea":        "Good plucking conditions — harvest two leaves and a bud at 7-day intervals. Apply fertilizer (urea 60 kg/ha) after plucking round. Monitor for red spider mite in dry bright weather — fine webbing on undersides of leaves indicates infestation.",
        "arecanut":   "Clear weather is ideal for arecanut harvesting and copra preparation. Harvest when 25% of nuts in a bunch turn orange. Process promptly — split nuts and dry in sun for 3-4 days. Check for yellow leaf disease (phytoplasma) and remove affected palms.",
        "tapioca":    "Clear weather is ideal for tapioca harvesting and planting. Harvest at 8-10 months for table varieties (Sree Vijaya, H-165). Plant stem cuttings (20 cm long, 6-8 nodes) at 45° angle. Apply FYM 12.5 tonnes/ha and NPK 100:50:100 kg/ha.",
        "millets":    "Good conditions for threshing and drying. Harvest sorghum when grains are hard; cumbu (pearl millet) when 80% of panicle is brown. Sun dry to below 12% moisture before storage. Treat stored grain with Malathion dust to prevent weevil damage.",
        "groundnut":  "Clear weather is ideal for harvesting and sun drying — critical for aflatoxin prevention. Dig when leaves yellow and inner shell shows veining. Dry pods to 8-9% moisture before storage. Poor drying (above 9%) allows Aspergillus infection within 2-3 weeks.",
        "sugarcane":  "Clear conditions are good for fertilizer application and earthing up. Top-dress with urea 80 kg/ha split at 30, 60, and 90 days. Check for red rot (Colletotrichum) — red discoloration in internodes with white patches; destroy affected clumps immediately.",
        "turmeric":   "Good conditions for field operations. At 90-120 days, apply potash (MOP 50 kg/ha) for rhizome bulking. Harvest when lower leaves turn yellow (8-9 months). Cure boiled rhizomes in 1% sodium bisulphate for 1 minute to maintain bright yellow color.",
        "vegetables": "Ideal conditions for transplanting, fertilization, and spray operations. Apply recommended NPK at transplanting. Spray in early morning or late evening. Check for sucking pests (aphids, whitefly, thrips) which multiply rapidly in warm dry conditions.",
        "cashew":     "Good harvesting conditions — collect fallen cashew apples and nuts daily. Separate nut from apple immediately; delay causes staining. Sun dry raw nuts to 9% moisture. Pack in airtight containers. Good time for canopy management pruning after harvest season.",
        "default":    "Clear and favorable conditions for most field operations. Good window for spray applications, inter-cultivation, and harvest. Monitor soil moisture if clear spell extends beyond 5 days — schedule supplemental irrigation for critical-stage crops.",
    },

    "high_humidity": {
        "rubber":     "High humidity above 85% promotes Phytophthora leaf fall and pink disease on branches. Spray copper oxychloride 3g/L preventively on canopy. Avoid tapping during peak humidity hours. Inspect tapping panels for water blister formation.",
        "coffee":     "Prolonged high humidity triggers coffee leaf rust (Hemileia vastatrix) — orange powdery pustules on leaf undersides. Spray Propiconazole 1ml/L or Triadimefon 1g/L at first sign. Ensure adequate potassium nutrition which improves disease resistance.",
        "cardamom":   "High humidity promotes Pythium damping off in nursery and Katte (mosaic) spread by aphids. Apply Metalaxyl 2g/L drench in nursery. Control aphid vectors with Imidacloprid 0.3ml/L spray. Reduce irrigation to avoid waterlogging in humid conditions.",
        "rice":       "High humidity (above 80%) with warm nights promotes rice blast and bacterial blight. Scout for angular water-soaked lesions (bacterial blight) or gray-centered lesions (blast). Spray Streptocycline 0.5g/L for bacterial blight; Tricyclazole for blast.",
        "pepper":     "High humidity above 85% is prime season for Phytophthora foot rot. Avoid any soil disturbance that splashes pathogen onto vine base. Apply Ridomil Gold (Metalaxyl+Copper) 3g/L at vine base. Remove and burn affected vines immediately.",
        "banana":     "High humidity favors Panama wilt (Fusarium oxysporum) and Sigatoka — monitor daily. Yellow leaf margins starting from lowest leaves indicate Panama wilt — no cure; remove and destroy infected plants. For Sigatoka, spray Propiconazole 0.1% at 3-week intervals.",
        "tea":        "High humidity with overcast conditions promotes blister blight on tender shoots and gray blight on mature leaves. Spray copper fungicide at 7-day intervals. Reduce nitrogen application temporarily — excess nitrogen makes shoots more susceptible.",
        "default":    "High humidity advisory. Fungal diseases peak when humidity exceeds 85% for 3+ consecutive days. Apply preventive copper fungicide (Mancozeb 2.5g/L) on susceptible crops. Improve air circulation through canopy pruning. Monitor closely for disease onset.",
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
