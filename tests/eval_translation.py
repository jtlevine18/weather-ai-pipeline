"""
Level 1D (cont.) — Translation Quality Evaluation

Evaluates translation quality via:
1. Back-translating advisory_local -> English via Claude
2. Semantic comparison with original advisory_en (LLM-as-Judge)
3. Agricultural term preservation rate (domain-weighted)

Usage:
    python tests/eval_translation.py
    python tests/eval_translation.py --max 10

Requires: ANTHROPIC_API_KEY, advisories in database (run pipeline first)
"""

import json
import os
import re
from datetime import datetime

import pytest
from rich.console import Console
from rich.table import Table

from config import get_config
from src.database import init_db

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(PROJECT_ROOT, "weather.duckdb")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results")

# Agricultural terms weighted higher in preservation scoring
AG_TERMS = [
    "drainage", "irrigat", "fertiliz", "urea", "nitrogen", "potassium",
    "fungicid", "pesticid", "insecticid", "herbicid", "mulch",
    "harvest", "transplant", "prune", "spray", "sow", "plant",
    "waterlog", "drought", "frost", "disease", "pest", "rot",
    "rice", "paddy", "coconut", "rubber", "coffee", "pepper",
    "banana", "tea", "cardamom", "arecanut", "sugarcane", "cotton",
    "millet", "groundnut", "turmeric", "tapioca", "cashew",
    "Bordeaux", "Trichoderma", "Phytophthora", "NPK",
    "kg/ha", "g/L", "ml/L",
]

SIMILARITY_PROMPT = """Compare these two English agricultural advisories for semantic equivalence.
Rate 0-5:
0 = completely different meaning
1 = same topic but very different advice
2 = similar topic, some shared advice
3 = mostly equivalent, minor differences
4 = nearly identical meaning
5 = semantically identical

Original English:
"{original}"

Back-translated from {language}:
"{back_translated}"

Return ONLY a single number (0-5):"""


def back_translate(client, model, text, language):
    """Translate local language text back to English."""
    lang_name = {"ta": "Tamil", "ml": "Malayalam"}.get(language, language)
    msg = client.messages.create(
        model=model, max_tokens=512,
        system=(f"Translate the following {lang_name} agricultural advisory "
                f"to English. Return only the translation."),
        messages=[{"role": "user", "content": text}],
    )
    return msg.content[0].text.strip()


def score_similarity(client, model, original, back_translated, language):
    """LLM-as-Judge semantic similarity score (0-5)."""
    lang_name = {"ta": "Tamil", "ml": "Malayalam"}.get(language, language)
    msg = client.messages.create(
        model=model, max_tokens=10,
        messages=[{"role": "user",
                   "content": SIMILARITY_PROMPT.format(
                       original=original, back_translated=back_translated,
                       language=lang_name)}],
    )
    match = re.search(r"(\d)", msg.content[0].text.strip())
    return int(match.group(1)) if match else 3


def ag_term_preservation(original, back_translated):
    """Fraction of agricultural terms in original that survive round-trip."""
    orig_lower = original.lower()
    back_lower = back_translated.lower()
    present = [t for t in AG_TERMS if t.lower() in orig_lower]
    if not present:
        return 1.0
    preserved = sum(1 for t in present if t.lower() in back_lower)
    return preserved / len(present)


def run_translation_eval(max_advisories=20):
    console = Console()
    config = get_config()

    if not config.anthropic_key:
        console.print("[red]ANTHROPIC_API_KEY required for back-translation.[/red]")
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=config.anthropic_key)

    conn = init_db(DB_PATH)
    rows = conn.execute("""
        SELECT advisory_en, advisory_local, language, station_id,
               condition, provider
        FROM agricultural_alerts
        WHERE advisory_en IS NOT NULL
          AND advisory_local IS NOT NULL
          AND language != 'en'
        ORDER BY issued_at DESC
        LIMIT ?
    """, [max_advisories]).fetchall()
    cols = [d[0] for d in conn.description]
    advisories = [dict(zip(cols, r)) for r in rows]
    conn.close()

    if not advisories:
        console.print("[yellow]No translated advisories found. "
                      "Run the pipeline first.[/yellow]")
        return None

    console.print(f"\n[bold]Level 1D — Translation Quality Eval[/bold]")
    console.print(f"Advisories to evaluate: {len(advisories)}\n")

    results_list = []
    for i, adv in enumerate(advisories):
        bt = back_translate(client, config.translation.model,
                           adv["advisory_local"], adv["language"])
        sim = score_similarity(client, config.translation.model,
                              adv["advisory_en"], bt, adv["language"])
        ag_pres = ag_term_preservation(adv["advisory_en"], bt)

        results_list.append({
            "station_id": adv["station_id"],
            "language": adv["language"],
            "condition": adv["condition"],
            "provider": adv["provider"],
            "similarity": sim,
            "ag_preservation": ag_pres,
            "original_preview": adv["advisory_en"][:100],
            "back_translated_preview": bt[:100],
        })

        if (i + 1) % 5 == 0:
            console.print(f"  Evaluated {i + 1}/{len(advisories)}...")

    # Aggregate
    avg_sim = sum(r["similarity"] for r in results_list) / len(results_list)
    avg_ag = sum(r["ag_preservation"] for r in results_list) / len(results_list)

    by_lang = {}
    for lang in sorted(set(r["language"] for r in results_list)):
        subset = [r for r in results_list if r["language"] == lang]
        by_lang[lang] = {
            "n": len(subset),
            "avg_similarity": sum(r["similarity"] for r in subset) / len(subset),
            "avg_ag_preservation": sum(r["ag_preservation"] for r in subset) / len(subset),
        }

    # Display
    console.print(f"\n[bold]Overall[/bold]")
    console.print(f"  Semantic similarity: {avg_sim:.1f}/5")
    console.print(f"  Ag term preservation: {avg_ag:.0%}")

    tbl = Table(title="\nTranslation Quality by Language")
    tbl.add_column("Language", style="bold")
    tbl.add_column("N", justify="right")
    tbl.add_column("Similarity (0-5)", justify="right")
    tbl.add_column("Ag Term Preservation", justify="right")
    for lang, m in by_lang.items():
        lang_name = {"ta": "Tamil", "ml": "Malayalam"}.get(lang, lang)
        tbl.add_row(lang_name, str(m["n"]),
                     f"{m['avg_similarity']:.1f}",
                     f"{m['avg_ag_preservation']:.0%}")
    console.print(tbl)

    # Worst cases
    worst = sorted(results_list, key=lambda r: r["similarity"])[:3]
    if worst:
        console.print("\n[bold]Lowest Similarity Cases[/bold]")
        for r in worst:
            console.print(f"  {r['station_id']} ({r['language']}): "
                          f"sim={r['similarity']}/5")
            console.print(f"    Original:  {r['original_preview']}...")
            console.print(f"    Back-xlat: {r['back_translated_preview']}...")

    # Save
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {
        "eval_name": "translation",
        "timestamp": datetime.utcnow().isoformat(),
        "n_advisories": len(advisories),
        "avg_similarity": avg_sim,
        "avg_ag_preservation": avg_ag,
        "by_language": by_lang,
        "details": results_list,
    }
    out = os.path.join(RESULTS_DIR, "translation.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {out}[/dim]")
    return results


@pytest.mark.slow
@pytest.mark.api
def test_eval_translation():
    """Pytest wrapper for standalone eval script."""
    results = run_translation_eval()
    assert results is not None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=20,
                        help="Max advisories to evaluate")
    args = parser.parse_args()
    run_translation_eval(max_advisories=args.max)
