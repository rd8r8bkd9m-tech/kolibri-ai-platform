#!/usr/bin/env python3
"""Extract training data from Kolibri SQLite conversations.

Reads messages from data/kolibri.db and generates JSONL datasets
suitable for fine-tuning TinyLlama-1.1B with LoRA.

Output format (chat JSONL):
  {"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

Usage:
  python3 extract_conversations.py --db /opt/kolibri-ai/data/kolibri.db
  python3 extract_conversations.py --db /opt/kolibri-ai/data/kolibri.db --min-turns 3 --val-split 0.15
"""

import argparse
import json
import sqlite3
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional


SYSTEM_PROMPT = "You are Kolibri, a helpful and concise AI assistant. Answer questions accurately and clearly."


def get_conversations(db_path: str, min_turns: int = 2) -> List[Dict]:
    """Load conversation threads from SQLite with minimum turn count."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT conversation_id, role, content, provider, created_at
        FROM messages
        WHERE content IS NOT NULL AND content != ''
        ORDER BY conversation_id, created_at
    """)
    rows = c.fetchall()
    conn.close()

    conversations = {}
    for row in rows:
        conv_id = row["conversation_id"]
        if conv_id not in conversations:
            conversations[conv_id] = []
        conversations[conv_id].append({
            "role": row["role"],
            "content": row["content"].strip(),
            "provider": row["provider"],
        })

    valid = []
    for conv_id, messages in conversations.items():
        user_turns = sum(1 for m in messages if m["role"] == "user")
        assistant_turns = sum(1 for m in messages if m["role"] == "assistant")
        if user_turns >= min_turns and assistant_turns >= 1:
            valid.append({"id": conv_id, "messages": messages})

    return valid


def deduplicate(conversations: List[Dict]) -> List[Dict]:
    """Remove duplicate conversations by content hash."""
    seen = set()
    unique = []
    for conv in conversations:
        content_str = json.dumps(
            [(m["role"], m["content"]) for m in conv["messages"]],
            sort_keys=True,
        )
        h = hashlib.sha256(content_str.encode()).hexdigest()[:16]
        if h not in seen:
            seen.add(h)
            unique.append(conv)
    return unique


def build_training_pairs(conversations: List[Dict]) -> List[Dict]:
    """Convert multi-turn conversations into training pairs.

    Each pair contains a system prompt + accumulated context + assistant response.
    Generates multiple samples from multi-turn conversations.
    """
    samples = []

    for conv in conversations:
        msgs = conv["messages"]
        context = [{"role": "system", "content": SYSTEM_PROMPT}]

        for i, msg in enumerate(msgs):
            if msg["role"] == "user":
                context.append({"role": "user", "content": msg["content"]})

                # Find the next assistant response
                for j in range(i + 1, len(msgs)):
                    if msgs[j]["role"] == "assistant":
                        sample_messages = list(context) + [
                            {"role": "assistant", "content": msgs[j]["content"]}
                        ]
                        samples.append({"messages": sample_messages})
                        break

            elif msg["role"] == "assistant":
                # Skip orphaned assistant messages (no preceding user message)
                if len(context) > 1 and context[-1]["role"] == "user":
                    context.append({"role": "assistant", "content": msg["content"]})

        # Also add the full conversation as one sample if it has enough turns
        if sum(1 for m in msgs if m["role"] == "user") >= 2:
            full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for msg in msgs:
                if msg["role"] in ("user", "assistant"):
                    full_messages.append({"role": msg["role"], "content": msg["content"]})
            if full_messages[-1]["role"] == "assistant":
                samples.append({"messages": full_messages})

    return samples


def filter_quality(samples: List[Dict], min_len: int = 20, max_len: int = 4096) -> List[Dict]:
    """Filter out low-quality samples."""
    filtered = []
    for sample in samples:
        msgs = sample["messages"]
        # Must end with assistant
        if msgs[-1]["role"] != "assistant":
            continue
        # Check assistant response length
        assistant_content = msgs[-1]["content"]
        if len(assistant_content) < min_len or len(assistant_content) > max_len:
            continue
        # Check for degenerate content (repeated characters, etc.)
        if len(set(assistant_content)) < 5:
            continue
        filtered.append(sample)
    return filtered


def save_jsonl(data: List[Dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Extract training data from Kolibri conversations")
    parser.add_argument("--db", type=str, default="/opt/kolibri-ai/data/kolibri.db",
                        help="Path to kolibri.db SQLite database")
    parser.add_argument("-o", "--output-dir", type=str, default="data",
                        help="Output directory for JSONL files")
    parser.add_argument("--min-turns", type=int, default=2,
                        help="Minimum user turns per conversation")
    parser.add_argument("--min-len", type=int, default=20,
                        help="Minimum assistant response length")
    parser.add_argument("--val-split", type=float, default=0.1,
                        help="Validation split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--system-prompt", type=str, default=None,
                        help="Override system prompt")
    args = parser.parse_args()

    if args.system_prompt:
        global SYSTEM_PROMPT
        SYSTEM_PROMPT = args.system_prompt

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not Path(args.db).exists():
        print(f"Error: Database not found at {args.db}")
        print("Provide --db path to kolibri.db")
        return 1

    print(f"Loading conversations from {args.db}...")
    conversations = get_conversations(args.db, min_turns=args.min_turns)
    print(f"Found {len(conversations)} conversations with >= {args.min_turns} user turns")

    if not conversations:
        print("No conversations found. Use synthetic data generator instead.")
        return 1

    conversations = deduplicate(conversations)
    print(f"After dedup: {len(conversations)} conversations")

    print("Building training pairs...")
    samples = build_training_pairs(conversations)
    print(f"Generated {len(samples)} raw samples")

    samples = filter_quality(samples, min_len=args.min_len)
    print(f"After quality filter: {len(samples)} samples")

    if not samples:
        print("No valid samples after filtering.")
        return 1

    import random
    random.seed(args.seed)
    random.shuffle(samples)

    val_size = max(1, int(len(samples) * args.val_split))
    val_data = samples[:val_size]
    train_data = samples[val_size:]

    train_path = output_dir / "train_conversations.jsonl"
    val_path = output_dir / "val_conversations.jsonl"

    save_jsonl(train_data, str(train_path))
    save_jsonl(val_data, str(val_path))

    print(f"\nSaved {len(train_data)} training samples -> {train_path}")
    print(f"Saved {len(val_data)} validation samples -> {val_path}")

    # Stats
    total_user_chars = sum(
        len(m["content"])
        for s in samples
        for m in s["messages"]
        if m["role"] == "user"
    )
    total_asst_chars = sum(
        len(m["content"])
        for s in samples
        for m in s["messages"]
        if m["role"] == "assistant"
    )
    avg_turns = sum(len(s["messages"]) for s in samples) / len(samples)
    print(f"\nStats:")
    print(f"  Avg messages per sample: {avg_turns:.1f}")
    print(f"  Total user chars: {total_user_chars:,}")
    print(f"  Total assistant chars: {total_asst_chars:,}")

    return 0


if __name__ == "__main__":
    exit(main())
