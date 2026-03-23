"""
Level 1C — RAG Retrieval Quality Evaluation

Measures precision@5, recall, and relevancy for the hybrid FAISS+BM25
retriever against a golden test set. Compares hybrid vs FAISS-only vs BM25-only.

Usage:
    python tests/eval_rag.py

Requires: sentence-transformers, faiss-cpu (embedding model downloads on first run)
"""

import json
import os
from datetime import datetime

import pytest
from rich.console import Console
from rich.table import Table

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results")
GOLDEN_SET = os.path.join(os.path.dirname(__file__), "eval_advisory_golden_set.json")


def build_query(case):
    """Convert golden test case to a retrieval query."""
    cond = case["condition"].replace("_", " ")
    return (
        f"{cond} weather conditions for {case['crop_context']} in {case['state']}. "
        f"Temperature {case['temperature']:.1f}C, rainfall {case['rainfall']:.1f}mm. "
        f"Agricultural advisory recommendations."
    )


def check_themes(docs, themes):
    """Return set of themes found via substring match in any retrieved doc."""
    found = set()
    for theme in themes:
        tl = theme.lower()
        for doc in docs:
            if tl in doc.lower():
                found.add(theme)
                break
    return found


def run_rag_eval():
    console = Console()

    with open(GOLDEN_SET) as f:
        golden = json.load(f)

    console.print(f"\n[bold]Level 1C — RAG Retrieval Eval[/bold]")
    console.print(f"Golden test cases: {len(golden)}")
    console.print("Loading retriever (may download embedding model on first run)...\n")

    from src.translation.rag_index_builder import build_index, EMBED_MODEL
    from langchain_huggingface import HuggingFaceEmbeddings
    from src.translation.rag_provider import _BM25, HybridRetriever

    index, corpus = build_index()
    if index is None or not corpus:
        console.print("[red]RAG index unavailable. Cannot run eval.[/red]")
        return None

    embedder = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    bm25 = _BM25(corpus)

    modes = {
        "hybrid (a=0.5)": HybridRetriever(index, corpus, embedder, bm25, alpha=0.5),
        "faiss_only (a=1.0)": HybridRetriever(index, corpus, embedder, bm25, alpha=1.0),
        "bm25_only (a=0.0)": HybridRetriever(index, corpus, embedder, bm25, alpha=0.0),
    }

    results_by_mode = {}
    for mode_name, retriever in modes.items():
        console.print(f"  Running {mode_name}...")
        case_results = []
        for case in golden:
            query = build_query(case)
            hits = retriever.retrieve(query, top_k=5, threshold=0.0)
            docs = [text for text, _ in hits]

            themes_found = check_themes(docs, case["expected_themes"])
            neg_found = check_themes(docs, case.get("negative_themes", []))

            relevant_docs = sum(
                1 for doc in docs
                if any(t.lower() in doc.lower() for t in case["expected_themes"])
            )
            p5 = relevant_docs / len(docs) if docs else 0
            recall = (len(themes_found) / len(case["expected_themes"])
                      if case["expected_themes"] else 0)

            case_results.append({
                "id": case["id"],
                "category": case["category"],
                "precision_at_5": p5,
                "recall": recall,
                "themes_found": list(themes_found),
                "themes_missed": [t for t in case["expected_themes"]
                                  if t not in themes_found],
                "negative_found": list(neg_found),
                "n_docs": len(docs),
                "avg_score": (sum(s for _, s in hits) / len(hits)) if hits else 0,
            })

        avg_p5 = sum(c["precision_at_5"] for c in case_results) / len(case_results)
        avg_rec = sum(c["recall"] for c in case_results) / len(case_results)
        neg_hits = sum(1 for c in case_results if c["negative_found"])

        results_by_mode[mode_name] = {
            "cases": case_results,
            "avg_precision": avg_p5,
            "avg_recall": avg_rec,
            "negative_theme_cases": neg_hits,
            "n_cases": len(case_results),
        }

    # Display summary table
    tbl = Table(title="Retrieval Quality by Mode")
    tbl.add_column("Mode", style="bold")
    tbl.add_column("Avg Precision@5", justify="right")
    tbl.add_column("Avg Recall", justify="right")
    tbl.add_column("Neg Theme Hits", justify="right")
    for mode, m in results_by_mode.items():
        tbl.add_row(mode, f"{m['avg_precision']:.2f}", f"{m['avg_recall']:.2f}",
                     str(m["negative_theme_cases"]))
    console.print(tbl)

    # Per-category breakdown (hybrid only)
    hybrid_key = "hybrid (a=0.5)"
    hybrid = results_by_mode.get(hybrid_key, {}).get("cases", [])
    if hybrid:
        cats = sorted(set(c["category"] for c in hybrid))
        tbl2 = Table(title="\nHybrid Retrieval by Category")
        tbl2.add_column("Category", style="bold")
        tbl2.add_column("N", justify="right")
        tbl2.add_column("Avg Precision@5", justify="right")
        tbl2.add_column("Avg Recall", justify="right")
        for cat in cats:
            subset = [c for c in hybrid if c["category"] == cat]
            ap = sum(c["precision_at_5"] for c in subset) / len(subset)
            ar = sum(c["recall"] for c in subset) / len(subset)
            tbl2.add_row(cat, str(len(subset)), f"{ap:.2f}", f"{ar:.2f}")
        console.print(tbl2)

    # Worst recall cases
    if hybrid:
        worst = sorted(hybrid, key=lambda c: c["recall"])[:5]
        console.print("\n[bold]Lowest Recall Cases (hybrid)[/bold]")
        for c in worst:
            console.print(f"  {c['id']}: recall={c['recall']:.2f}  "
                          f"missed={c['themes_missed']}")

    # Save
    os.makedirs(RESULTS_DIR, exist_ok=True)
    save_data = {}
    for mode, m in results_by_mode.items():
        save_data[mode] = {k: v for k, v in m.items() if k != "cases"}
        save_data[mode]["per_case"] = [
            {k: v for k, v in c.items() if k != "themes_found"}
            for c in m["cases"]
        ]
    results = {
        "eval_name": "rag",
        "timestamp": datetime.utcnow().isoformat(),
        "n_cases": len(golden),
        "by_mode": save_data,
    }
    out = os.path.join(RESULTS_DIR, "rag.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    console.print(f"\n[dim]Results saved to {out}[/dim]")
    return results


@pytest.mark.slow
@pytest.mark.offline
def test_eval_rag():
    """Pytest wrapper for standalone eval script."""
    results = run_rag_eval()
    assert results is not None


if __name__ == "__main__":
    run_rag_eval()
