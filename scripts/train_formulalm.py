"""
FormulaLM Training — обучение на исторических данных корпуса.

Загружает тексты из full_corpus.txt + corpus/*.txt + kolibri_fractal_memory.jsonl,
обучает BPE токенизатор, затем эволюционирует FormulaLM.

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

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

DATA_DIR = Path(__file__).parent.parent / "data"
MODELS_DIR = DATA_DIR / "models"


def load_corpus(max_texts: int = 5000) -> list[str]:
    """Загрузить тексты из всех доступных источников."""
    texts: list[str] = []

    # 1. full_corpus.txt
    full_corpus = DATA_DIR / "full_corpus.txt"
    if full_corpus.exists():
        lines = full_corpus.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines:
            line = line.strip()
            if len(line) > 30:
                texts.append(line)
        logger.info("full_corpus.txt: %d строк, отобрано %d", len(lines), len(texts))

    # 2. corpus/*.txt
    corpus_dir = DATA_DIR / "corpus"
    if corpus_dir.is_dir():
        count_before = len(texts)
        for f in sorted(corpus_dir.glob("*.txt")):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                for para in content.split("\n\n"):
                    para = para.strip()
                    if len(para) > 30:
                        texts.append(para)
            except Exception:
                continue
        logger.info("corpus/*.txt: +%d параграфов", len(texts) - count_before)

    # 3. kolibri_fractal_memory.jsonl
    fractal = DATA_DIR / "models" / "kolibri_fractal_memory.jsonl"
    if fractal.exists():
        count_before = len(texts)
        for line in fractal.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                obj = json.loads(line)
                q = obj.get("question", "")
                a = obj.get("answer", "")
                if len(q) > 20:
                    texts.append(q)
                if len(a) > 20:
                    texts.append(a)
                text = obj.get("text", obj.get("content", ""))
                if len(text) > 20:
                    texts.append(text)
            except Exception:
                continue
        logger.info("fractal_memory: +%d записей", len(texts) - count_before)

    # 4. kolibri_qa.kqa (если это JSONL)
    qa_file = DATA_DIR / "models" / "kolibri_qa.kqa"
    if qa_file.exists():
        count_before = len(texts)
        try:
            content = qa_file.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                try:
                    obj = json.loads(line)
                    q = obj.get("question", obj.get("q", ""))
                    a = obj.get("answer", obj.get("a", ""))
                    if len(q) > 10:
                        texts.append(q)
                    if len(a) > 10:
                        texts.append(a)
                except Exception:
                    if len(line) > 30:
                        texts.append(line)
        except Exception:
            pass
        logger.info("kolibri_qa: +%d записей", len(texts) - count_before)

    # Дедупликация
    seen = set()
    unique: list[str] = []
    for t in texts:
        h = hash(t[:200])
        if h not in seen:
            seen.add(h)
            unique.append(t)

    logger.info("Итого: %d уникальных текстов (лимит %d)", len(unique), max_texts)
    return unique[:max_texts]


def train_bpe_tokenizer(texts: list[str], vocab_size: int = 8000):
    """Обучить BPE токенизатор."""
    from service.tokenizer import BPETokenizer

    tokenizer = BPETokenizer(vocab_size=vocab_size)
    tokenizer.train(texts[:2000])
    logger.info("BPE tokenizer: vocab_size=%d", len(tokenizer))
    return tokenizer


def encode_texts(tokenizer, texts: list[str], min_len: int = 5) -> list[list[int]]:
    """Закодировать тексты в последовательности токенов."""
    sequences: list[list[int]] = []
    for text in texts:
        try:
            ids = tokenizer.encode(text)
            if len(ids) >= min_len:
                sequences.append(ids)
        except Exception:
            continue
    logger.info("Закодировано %d последовательностей (мин. длина %d)", len(sequences), min_len)
    return sequences


def train_formulalm(
    sequences: list[list[int]],
    vocab_size: int = 8000,
    embed_dim: int = 64,
    context_size: int = 256,
    num_formulas: int = 16,
    generations: int = 200,
    save_every: int = 50,
    output_prefix: str = "formulalm_trained",
):
    """Обучить FormulaLM эволюцией."""
    from service.formula_lm import FormulaLM

    model = FormulaLM(
        vocab_size=vocab_size,
        embed_dim=embed_dim,
        context_size=context_size,
        num_formulas=num_formulas,
    )

    logger.info(
        "FormulaLM: vocab=%d, embed=%d, ctx=%d, formulas=%d, generations=%d",
        vocab_size, embed_dim, context_size, num_formulas, generations,
    )
    logger.info("Training на %d последовательностях...", len(sequences))

    start_time = time.time()
    batch_size = min(200, len(sequences))

    for gen_start in range(0, generations, save_every):
        gen_count = min(save_every, generations - gen_start)
        model.evolve(sequences[:batch_size], generations=gen_count)

        elapsed = time.time() - start_time
        ppl = model.get_perplexity(sequences[:50])
        logger.info(
            "gen=%d, perplexity=%.2f, best_fitness=%.4f, elapsed=%.0fs",
            model.generation, ppl, model.formulas[model._best_idx].fitness, elapsed,
        )

        # Сохраняем чекпоинт
        save_path = MODELS_DIR / f"{output_prefix}_{model.generation}.npz"
        model.save(save_path)
        logger.info("Чекпоинт сохранён: %s", save_path)

    total_time = time.time() - start_time
    final_ppl = model.get_perplexity(sequences[:100])
    logger.info("Обучение завершено: %d поколений, %.0fс, финальный PPL=%.2f", generations, total_time, final_ppl)

    # Финальное сохранение
    final_path = MODELS_DIR / f"{output_prefix}_final.npz"
    model.save(final_path)
    logger.info("Финальная модель: %s", final_path)

    return model


def main():
    parser = argparse.ArgumentParser(description="Train FormulaLM on historical corpus")
    parser.add_argument("--max-texts", type=int, default=5000, help="Max texts to use")
    parser.add_argument("--vocab-size", type=int, default=8000, help="BPE vocabulary size")
    parser.add_argument("--embed-dim", type=int, default=64, help="Embedding dimension")
    parser.add_argument("--context-size", type=int, default=256, help="Context window size")
    parser.add_argument("--num-formulas", type=int, default=16, help="Number of evolutionary formulas")
    parser.add_argument("--generations", type=int, default=200, help="Evolution generations")
    parser.add_argument("--save-every", type=int, default=50, help="Save checkpoint every N generations")
    parser.add_argument("--output", type=str, default="formulalm_trained", help="Output file prefix")
    args = parser.parse_args()

    logger.info("=== FormulaLM Training ===")
    logger.info("Data dir: %s", DATA_DIR)

    # 1. Загрузка корпуса
    texts = load_corpus(max_texts=args.max_texts)
    if len(texts) < 50:
        logger.error("Недостаточно текстов: %d (нужно >= 50)", len(texts))
        sys.exit(1)

    # 2. Обучение BPE
    tokenizer = train_bpe_tokenizer(texts, vocab_size=args.vocab_size)

    # 3. Кодирование
    sequences = encode_texts(tokenizer, texts)
    if len(sequences) < 30:
        logger.error("Недостаточно последовательностей: %d (нужно >= 30)", len(sequences))
        sys.exit(1)

    # 4. Обучение FormulaLM
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

    # 5. Тест генерации
    logger.info("=== Тест генерации ===")
    test_prompts = ["Привет", "Что такое искусственный интеллект?", "Смета на ремонт"]
    for prompt in test_prompts:
        ids = tokenizer.encode(prompt)
        generated = model.generate(ids, max_tokens=30, temperature=0.8)
        text = tokenizer.decode(generated)
        logger.info("'%s' → '%s'", prompt, text)

    logger.info("=== Готово ===")


if __name__ == "__main__":
    main()
