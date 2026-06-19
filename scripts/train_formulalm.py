"""
FormulaLM Training — обучение на исторических данных корпуса.

Usage:
    python3 train_formulalm.py [--generations 200] [--vocab-size 8000] [--max-texts 5000]
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("train-formulalm")

sys.path.insert(0, str(Path(__file__).parent))

DATA_DIR = Path(__file__).parent.parent / "data"
MODELS_DIR = DATA_DIR / "models"


def load_corpus(max_texts: int = 5000) -> list[str]:
    texts: list[str] = []

    full_corpus = DATA_DIR / "full_corpus.txt"
    if full_corpus.exists():
        lines = full_corpus.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines:
            line = line.strip()
            if len(line) > 30:
                texts.append(line)
        logger.info("full_corpus.txt: %d строк, отобрано %d", len(lines), len(texts))

    corpus_dir = DATA_DIR / "corpus"
    if corpus_dir.is_dir():
        n = len(texts)
        for f in sorted(corpus_dir.glob("*.txt")):
            try:
                for para in f.read_text(encoding="utf-8", errors="replace").split("\n\n"):
                    para = para.strip()
                    if len(para) > 30:
                        texts.append(para)
            except Exception:
                continue
        logger.info("corpus/*.txt: +%d", len(texts) - n)

    fractal = DATA_DIR / "models" / "kolibri_fractal_memory.jsonl"
    if fractal.exists():
        n = len(texts)
        for line in fractal.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                obj = json.loads(line)
                for key in ("question", "answer", "text", "content"):
                    val = obj.get(key, "")
                    if len(val) > 20:
                        texts.append(val)
            except Exception:
                continue
        logger.info("fractal_memory: +%d", len(texts) - n)

    qa_file = DATA_DIR / "models" / "kolibri_qa.kqa"
    if qa_file.exists():
        n = len(texts)
        for line in qa_file.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                obj = json.loads(line)
                for key in ("question", "answer", "q", "a"):
                    val = obj.get(key, "")
                    if len(val) > 10:
                        texts.append(val)
            except Exception:
                if len(line) > 30:
                    texts.append(line)
        logger.info("kolibri_qa: +%d", len(texts) - n)

    seen = set()
    unique = []
    for t in texts:
        h = hash(t[:200])
        if h not in seen:
            seen.add(h)
            unique.append(t)

    logger.info("Итого: %d уникальных (лимит %d)", len(unique), max_texts)
    return unique[:max_texts]


def train_bpe_tokenizer(texts: list[str], vocab_size: int = 8000):
    from service.tokenizer import BPETokenizer
    tokenizer = BPETokenizer(vocab_size=vocab_size)
    tokenizer.train(texts[:2000])
    logger.info("BPE tokenizer: vocab=%d", len(tokenizer))
    return tokenizer


def encode_texts(tokenizer, texts: list[str], min_len: int = 5) -> list[list[int]]:
    seqs = []
    for t in texts:
        try:
            ids = tokenizer.encode(t)
            if len(ids) >= min_len:
                seqs.append(ids)
        except Exception:
            continue
    logger.info("Закодировано %d последовательностей", len(seqs))
    return seqs


def train_formulalm(
    sequences: list[list[int]],
    vocab_size: int = 8000,
    embed_dim: int = 64,
    context_size: int = 256,
    num_formulas: int = 16,
    generations: int = 200,
    save_every: int = 10,
    output_prefix: str = "formulalm_trained",
):
    from service.formula_lm import FormulaLM

    model = FormulaLM(
        vocab_size=vocab_size,
        embed_dim=embed_dim,
        context_size=context_size,
        num_formulas=num_formulas,
    )

    logger.info("FormulaLM: vocab=%d embed=%d ctx=%d formulas=%d gen=%d",
                vocab_size, embed_dim, context_size, num_formulas, generations)

    batch_size = min(200, len(sequences))
    train_seqs = sequences[:batch_size]
    logger.info("Batch: %d последовательностей", batch_size)

    start = time.time()

    for gen_start in range(0, generations, save_every):
        gen_count = min(save_every, generations - gen_start)

        # Use original evolve() — much faster than inline loop
        model.evolve(train_seqs, generations=gen_count)

        # Log AFTER evolve returns (fitness is already updated)
        best_f = model.formulas[model._best_idx].fitness
        import math
        ppl = math.exp(-best_f) if -500 < best_f < 500 else float('inf')
        elapsed = time.time() - start
        logger.info("gen=%d/%d, fitness=%.4f, ppl=%.1f, elapsed=%.0fs",
                     model.generation, generations, best_f, ppl, elapsed)

        save_path = MODELS_DIR / f"{output_prefix}_{model.generation}.npz"
        model.save(save_path)
        logger.info("Чекпоинт: %s", save_path)

    total = time.time() - start
    logger.info("Готово: %d gen, %.0fс", generations, total)

    final_path = MODELS_DIR / f"{output_prefix}_final.npz"
    model.save(final_path)
    logger.info("Финал: %s", final_path)
    return model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-texts", type=int, default=5000)
    parser.add_argument("--vocab-size", type=int, default=8000)
    parser.add_argument("--embed-dim", type=int, default=64)
    parser.add_argument("--context-size", type=int, default=256)
    parser.add_argument("--num-formulas", type=int, default=16)
    parser.add_argument("--generations", type=int, default=200)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--output", type=str, default="formulalm_trained")
    args = parser.parse_args()

    logger.info("=== FormulaLM Training ===")

    texts = load_corpus(max_texts=args.max_texts)
    if len(texts) < 50:
        logger.error("Мало текстов: %d", len(texts))
        sys.exit(1)

    tokenizer = train_bpe_tokenizer(texts, vocab_size=args.vocab_size)
    sequences = encode_texts(tokenizer, texts)
    if len(sequences) < 30:
        logger.error("Мало последовательностей: %d", len(sequences))
        sys.exit(1)

    model = train_formulalm(
        sequences=sequences,
        vocab_size=args.vocab_size,
        embed_dim=args.embed_dim,
        context_size=args.context_size,
        num_formulas=args.num_formulas,
        generations=args.generations,
        save_every=args.save_every,
        output_prefix=args.output,
    )

    logger.info("=== Тест генерации ===")
    for prompt in ["Привет", "Что такое AI?", "Смета на ремонт"]:
        ids = tokenizer.encode(prompt)
        out = model.generate(ids, max_tokens=30, temperature=0.8)
        logger.info("'%s' → '%s'", prompt, tokenizer.decode(out))


if __name__ == "__main__":
    main()
