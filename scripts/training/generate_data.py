#!/usr/bin/env python3
"""Generate synthetic QA training data for TinyLlama-1.1B fine-tuning.

Generates JSONL datasets with instruction-response pairs.
Also reads real conversations from SQLite when available.
Uses only stdlib — no external dependencies required.

Usage:
  python3 generate_data.py -n 200
  python3 generate_data.py -n 500 --db /opt/kolibri-ai/data/kolibri.db
"""

import json
import random
import argparse
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional


TOPICS = {
    "python": [
        ("What is a list in Python?", "A list is an ordered, mutable collection of items in Python. It can contain elements of different types and is defined using square brackets, e.g., my_list = [1, 2, 3]."),
        ("How do you define a function in Python?", "You define a function using the def keyword: def my_function(param1, param2): followed by the function body and an optional return statement."),
        ("What is a dictionary in Python?", "A dictionary is an unordered collection of key-value pairs. It is defined using curly braces: my_dict = {'key': 'value'}. Keys must be unique and immutable."),
        ("What is the difference between a tuple and a list?", "A list is mutable (can be modified after creation) and uses square brackets []. A tuple is immutable (cannot be modified) and uses parentheses ()."),
        ("How do you handle exceptions in Python?", "You handle exceptions using try-except blocks: try: code_that_may_fail() except ExceptionType: handle_error(). You can also use finally for cleanup code."),
        ("What is a list comprehension?", "A list comprehension is a concise way to create lists: [x**2 for x in range(10)] creates a list of squares. It can include conditions: [x for x in range(10) if x % 2 == 0]."),
        ("What is __init__ in Python?", "__init__ is the constructor method of a Python class. It is automatically called when a new object is instantiated and is used to initialize the object's attributes."),
        ("What is the self parameter?", "self refers to the current instance of a class. It must be the first parameter of instance methods and is used to access instance variables and other methods."),
        ("What is a generator in Python?", "A generator is a function that uses yield instead of return to produce a sequence of values lazily. It maintains state between calls and is memory-efficient for large sequences."),
        ("How do you read a file in Python?", "Use open() with a context manager: with open('file.txt', 'r') as f: content = f.read(). You can also iterate line by line: for line in f: process(line)."),
    ],
    "linux": [
        ("How do you list files in Linux?", "Use the ls command to list files. ls -la shows all files including hidden ones with detailed information like permissions, owner, size, and date."),
        ("How do you change file permissions?", "Use chmod to change permissions: chmod 755 file gives read/write/execute to owner and read/execute to group and others. You can also use symbolic mode: chmod u+x file."),
        ("What is a symbolic link?", "A symbolic link (symlink) is a file that points to another file or directory. Create it with: ln -s target_path link_name. It acts as a shortcut."),
        ("How do you search for text in files?", "Use grep to search: grep -r 'pattern' /path/ searches recursively. grep -i makes it case-insensitive. grep -n shows line numbers."),
        ("How do you check disk usage?", "Use df -h to see filesystem disk usage in human-readable format. Use du -sh /path/ to check the size of a specific directory."),
        ("What is systemctl?", "systemctl is used to manage systemd services: systemctl start/stop/restart/status service_name. systemctl enable service_name makes a service start at boot."),
        ("How do you find files in Linux?", "Use find: find /path -name '*.txt' searches by name. find /path -type f -size +100M finds files larger than 100MB. locate uses a database for faster searching."),
        ("How do you check running processes?", "Use ps aux to see all running processes. top shows real-time process info. htop provides an interactive view. pgrep finds processes by name."),
    ],
    "networking": [
        ("What is an IP address?", "An IP address is a unique numerical identifier for a device on a network. IPv4 uses 4 octets (e.g., 192.168.1.1), IPv6 uses 8 groups of hexadecimal numbers."),
        ("What is DNS?", "DNS (Domain Name System) translates domain names to IP addresses. When you type a URL, a DNS resolver queries root servers, then TLD servers, then authoritative servers to find the IP."),
        ("What is TCP vs UDP?", "TCP is connection-oriented, reliable, ordered — used for HTTP, email. UDP is connectionless, faster, no guarantee of delivery — used for video streaming, gaming, DNS queries."),
        ("What is a firewall?", "A firewall monitors and controls network traffic based on security rules. It can be hardware or software-based and filters packets by IP, port, protocol, and content."),
        ("What is SSH?", "SSH (Secure Shell) is a protocol for secure remote access. It encrypts all traffic between client and server. Default port is 22. Usage: ssh user@hostname."),
        ("What is a subnet?", "A subnet divides a network into smaller segments. A subnet mask (e.g., 255.255.255.0) determines which bits of an IP address identify the network vs. host."),
    ],
    "ai_ml": [
        ("What is machine learning?", "Machine learning is a subset of AI where algorithms learn patterns from data without being explicitly programmed. Common types: supervised, unsupervised, and reinforcement learning."),
        ("What is a neural network?", "A neural network is a computing model inspired by the brain. It has layers of interconnected nodes (neurons) that process information through weighted connections and activation functions."),
        ("What is fine-tuning in AI?", "Fine-tuning takes a pre-trained model and continues training on domain-specific data. It's faster than training from scratch and adapts the model to specific tasks while retaining general knowledge."),
        ("What is LoRA?", "LoRA (Low-Rank Adaptation) is a parameter-efficient fine-tuning method. It adds small trainable matrices to frozen model weights, reducing the number of parameters to train by 10-100x."),
        ("What is a transformer?", "A transformer is a neural network architecture that uses self-attention to process sequences in parallel. It's the foundation of models like GPT, LLaMA, and BERT."),
        ("What is GGUF?", "GGUF (GPT-Generated Unified Format) is a file format for quantized language models. It supports various quantization levels (Q4_K_M, Q5_K_M, etc.) and is optimized for CPU inference."),
    ],
    "devops": [
        ("What is Docker?", "Docker is a containerization platform that packages applications with their dependencies into portable containers. Dockerfile defines the image, docker-compose orchestrates multi-container apps."),
        ("What is CI/CD?", "CI (Continuous Integration) automatically builds and tests code on every push. CD (Continuous Delivery/Deployment) automates releasing to production. Tools: GitHub Actions, GitLab CI, Jenkins."),
        ("What is Kubernetes?", "Kubernetes (K8s) is a container orchestration system. It manages deployment, scaling, and networking of containers across clusters. Key concepts: pods, services, deployments, namespaces."),
        ("What is Redis?", "Redis is an in-memory data store used as a database, cache, and message broker. It supports strings, hashes, lists, sets, and streams. Common use: session storage, pub/sub, rate limiting."),
    ],
}

SYSTEM_PROMPT = "You are Kolibri, a helpful and concise AI assistant. Answer questions accurately and clearly."


def load_conversations_from_db(db_path: str, min_turns: int = 2) -> List[Dict]:
    """Load real conversations from Kolibri SQLite database."""
    if not Path(db_path).exists():
        return []

    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT conversation_id, role, content
            FROM messages
            WHERE content IS NOT NULL AND content != ''
            ORDER BY conversation_id, created_at
        """)
        rows = c.fetchall()
        conn.close()
    except Exception as e:
        print(f"Warning: Could not read database: {e}")
        return []

    conversations = {}
    for conv_id, role, content in rows:
        if conv_id not in conversations:
            conversations[conv_id] = []
        conversations[conv_id].append({"role": role, "content": content.strip()})

    samples = []
    for conv_id, messages in conversations.items():
        user_turns = sum(1 for m in messages if m["role"] == "user")
        if user_turns < min_turns:
            continue

        # Build training pairs from conversation
        context = [{"role": "system", "content": SYSTEM_PROMPT}]
        for i, msg in enumerate(messages):
            if msg["role"] == "user":
                context.append({"role": "user", "content": msg["content"]})
                # Find next assistant reply
                for j in range(i + 1, len(messages)):
                    if messages[j]["role"] == "assistant":
                        sample = list(context) + [
                            {"role": "assistant", "content": messages[j]["content"]}
                        ]
                        samples.append({
                            "system": SYSTEM_PROMPT,
                            "user": msg["content"],
                            "assistant": messages[j]["content"],
                            "topic": "conversation",
                        })
                        break
            elif msg["role"] == "assistant" and len(context) > 1:
                context.append({"role": "assistant", "content": msg["content"]})

    return samples


def generate_qa_pairs(n_samples: int, seed: int = 42) -> List[Dict]:
    """Generate QA pairs from topic templates with some variation."""
    random.seed(seed)
    all_pairs = []
    for topic, pairs in TOPICS.items():
        for q, a in pairs:
            all_pairs.append((topic, q, a))

    samples = []
    for _ in range(n_samples):
        topic, question, answer = random.choice(all_pairs)
        if random.random() < 0.3:
            question = question.rstrip("?") + "?"
        samples.append({
            "system": SYSTEM_PROMPT,
            "user": question,
            "assistant": answer,
            "topic": topic,
        })
    random.shuffle(samples)
    return samples


def save_jsonl(data: List[Dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate training data for TinyLlama")
    parser.add_argument("-n", "--num-samples", type=int, default=100,
                        help="Number of synthetic samples to generate")
    parser.add_argument("-o", "--output", type=str, default="data/train.jsonl",
                        help="Output JSONL path")
    parser.add_argument("--db", type=str, default=None,
                        help="Path to kolibri.db for real conversation extraction")
    parser.add_argument("--val-split", type=float, default=0.1,
                        help="Validation split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--synthetic-only", action="store_true",
                        help="Skip DB extraction, use only synthetic data")
    args = parser.parse_args()

    output_dir = Path(args.output).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    all_data = []

    # Load real conversations from DB
    if args.db and not args.synthetic_only:
        print(f"Loading conversations from {args.db}...")
        db_samples = load_conversations_from_db(args.db)
        if db_samples:
            all_data.extend(db_samples)
            print(f"  Loaded {len(db_samples)} samples from conversations")
        else:
            print("  No conversations found in database")

    # Generate synthetic data
    if args.num_samples > 0:
        print(f"Generating {args.num_samples} synthetic QA pairs (seed={args.seed})...")
        synthetic = generate_qa_pairs(args.num_samples, args.seed)
        all_data.extend(synthetic)

    if not all_data:
        print("No data to save. Use --num-samples or --db.")
        return 1

    random.seed(args.seed)
    random.shuffle(all_data)

    val_size = max(1, int(len(all_data) * args.val_split))
    val_data = all_data[:val_size]
    train_data = all_data[val_size:]

    train_path = Path(args.output)
    val_path = train_path.parent / "val.jsonl"

    save_jsonl(train_data, str(train_path))
    save_jsonl(val_data, str(val_path))

    print(f"\nSaved {len(train_data)} training samples to {train_path}")
    print(f"Saved {len(val_data)} validation samples to {val_path}")

    topics = {}
    for item in all_data:
        t = item.get("topic", "unknown")
        topics[t] = topics.get(t, 0) + 1
    print(f"Topic distribution: {dict(sorted(topics.items()))}")

    return 0


if __name__ == "__main__":
    exit(main() or 0)
