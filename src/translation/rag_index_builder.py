"""
Build FAISS index from curated agricultural advisories corpus.
Uses BAAI/bge-base-en-v1.5 embeddings.
"""

from __future__ import annotations
import logging
import os
import pickle
from typing import List, Tuple

log = logging.getLogger(__name__)

INDEX_DIR    = "models/faiss_index"
INDEX_FILE   = os.path.join(INDEX_DIR, "index.faiss")
CORPUS_FILE  = os.path.join(INDEX_DIR, "corpus.pkl")
EMBED_MODEL  = "BAAI/bge-base-en-v1.5"


def _load_dataset_texts() -> List[str]:
    """Load agricultural corpus from curated advisories."""
    from src.translation.curated_advisories import ADVISORY_MATRIX
    texts = []
    for cond, crop_map in ADVISORY_MATRIX.items():
        for crop, advisory in crop_map.items():
            texts.append(f"[{cond}][{crop}] {advisory}")
    log.info("Corpus size: %d documents", len(texts))
    return texts


def build_index(force_rebuild: bool = False) -> Tuple[any, List[str]]:
    """
    Build or load FAISS index.
    Returns (index, corpus_texts).
    """
    if not force_rebuild and os.path.exists(INDEX_FILE) and os.path.exists(CORPUS_FILE):
        log.info("Loading cached FAISS index from %s", INDEX_DIR)
        try:
            import faiss
            index  = faiss.read_index(INDEX_FILE)
            with open(CORPUS_FILE, "rb") as f:
                corpus = pickle.load(f)
            log.info("Loaded index with %d vectors", index.ntotal)
            return index, corpus
        except Exception as exc:
            log.warning("Failed to load cached index: %s — rebuilding", exc)

    log.info("Building FAISS index...")
    corpus = _load_dataset_texts()

    if not corpus:
        log.error("No corpus texts — cannot build index")
        return None, []

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        import faiss
        import numpy as np

        embedder = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
        log.info("Embedding %d documents with %s...", len(corpus), EMBED_MODEL)

        batch_size = 64
        all_vecs   = []
        for i in range(0, len(corpus), batch_size):
            batch = corpus[i:i + batch_size]
            vecs  = embedder.embed_documents(batch)
            all_vecs.extend(vecs)
            if (i // batch_size) % 10 == 0:
                log.info("  embedded %d/%d", i + len(batch), len(corpus))

        matrix = np.array(all_vecs, dtype="float32")
        dim    = matrix.shape[1]
        index  = faiss.IndexFlatIP(dim)  # Inner product (cosine after normalization)
        faiss.normalize_L2(matrix)
        index.add(matrix)

        os.makedirs(INDEX_DIR, exist_ok=True)
        faiss.write_index(index, INDEX_FILE)
        with open(CORPUS_FILE, "wb") as f:
            pickle.dump(corpus, f)

        log.info("FAISS index built: %d vectors, dim=%d", index.ntotal, dim)
        return index, corpus

    except Exception as exc:
        log.error("FAISS index build failed: %s", exc)
        return None, corpus
