#!/usr/bin/env python3
"""Generate synthetic QA training data for Qwen2.5-1.5B distillation.

Generates a simple JSONL dataset with instruction-response pairs.
Uses only stdlib — no external dependencies required.
"""

import json
import random
import argparse
from pathlib import Path

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
    ],
    "linux": [
        ("How do you list files in Linux?", "Use the ls command to list files. ls -la shows all files including hidden ones with detailed information like permissions, owner, size, and date."),
        ("How do you change file permissions?", "Use chmod to change permissions: chmod 755 file gives read/write/execute to owner and read/execute to group and others. You can also use symbolic mode: chmod u+x file."),
        ("What is a symbolic link?", "A symbolic link (symlink) is a file that points to another file or directory. Create it with: ln -s target_path link_name. It acts as a shortcut."),
        ("How do you search for text in files?", "Use grep to search: grep -r 'pattern' /path/ searches recursively. grep -i makes it case-insensitive. grep -n shows line numbers."),
        ("How do you check disk usage?", "Use df -h to see filesystem disk usage in human-readable format. Use du -sh /path/ to check the size of a specific directory."),
        ("What is systemctl?", "systemctl is used to manage systemd services: systemctl start/stop/restart/status service_name. systemctl enable service_name makes a service start at boot."),
        ("How do you find files in Linux?", "Use find: find /path -name '*.txt' searches by name. find /path -type f -size +100M finds files larger than 100MB. locate uses a database for faster searching."),
    ],
    "networking": [
        ("What is an IP address?", "An IP address is a unique numerical identifier for a device on a network. IPv4 uses 4 octets (e.g., 192.168.1.1), IPv6 uses 8 groups of hexadecimal numbers."),
        ("What is DNS?", "DNS (Domain Name System) translates domain names to IP addresses. When you type a URL, a DNS resolver queries root servers, then TLD servers, then authoritative servers to find the IP."),
        ("What is TCP vs UDP?", "TCP is connection-oriented, reliable, ordered — used for HTTP, email. UDP is connectionless, faster, no guarantee of delivery — used for video streaming, gaming, DNS queries."),
        ("What is a firewall?", "A firewall monitors and controls network traffic based on security rules. It can be hardware or software-based and filters packets by IP, port, protocol, and content."),
        ("What is SSH?", "SSH (Secure Shell) is a protocol for secure remote access. It encrypts all traffic between client and server. Default port is 22. Usage: ssh user@hostname."),
    ],
    "math": [
        ("What is the Pythagorean theorem?", "In a right triangle, the square of the hypotenuse equals the sum of squares of the other two sides: a² + b² = c², where c is the hypotenuse."),
        ("What is a prime number?", "A prime number is a natural number greater than 1 that has no positive divisors other than 1 and itself. Examples: 2, 3, 5, 7, 11, 13, 17, 19, 23, 29."),
        ("What is the derivative of x²?", "The derivative of x² is 2x. Using the power rule: d/dx(x^n) = n*x^(n-1). So d/dx(x²) = 2*x^(2-1) = 2x."),
        ("What is the area of a circle?", "The area of a circle is A = πr², where r is the radius and π ≈ 3.14159. The circumference is C = 2πr."),
    ],
    "science": [
        ("What is photosynthesis?", "Photosynthesis is the process by which plants convert sunlight, water, and CO2 into glucose and oxygen: 6CO2 + 6H2O + light → C6H12O6 + 6O2."),
        ("What is the speed of light?", "The speed of light in vacuum is approximately 299,792,458 meters per second (about 3 × 10⁸ m/s). It is denoted by c and is the universal speed limit."),
        ("What is DNA?", "DNA (deoxyribonucleic acid) is a molecule that carries genetic instructions for life. It has a double helix structure made of nucleotides containing bases: A, T, G, C."),
    ],
}

SYSTEM_PROMPT = "You are a helpful, concise assistant. Answer questions accurately and clearly."


def generate_qa_pairs(n_samples, seed=42):
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


def save_jsonl(data, path):
    with open(path, "w") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic QA training data")
    parser.add_argument("-n", "--num-samples", type=int, default=100, help="Number of samples to generate")
    parser.add_argument("-o", "--output", type=str, default="data/train.jsonl", help="Output JSONL path")
    parser.add_argument("--val-split", type=float, default=0.1, help="Validation split ratio")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    output_dir = Path(args.output).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {args.num_samples} QA pairs (seed={args.seed})...")
    data = generate_qa_pairs(args.num_samples, args.seed)

    val_size = max(1, int(len(data) * args.val_split))
    val_data = data[:val_size]
    train_data = data[val_size:]

    train_path = Path(args.output)
    val_path = train_path.parent / "val.jsonl"

    save_jsonl(train_data, train_path)
    save_jsonl(val_data, val_path)

    print(f"Saved {len(train_data)} training samples to {train_path}")
    print(f"Saved {len(val_data)} validation samples to {val_path}")

    topics = {}
    for item in data:
        t = item["topic"]
        topics[t] = topics.get(t, 0) + 1
    print("Topic distribution:", dict(sorted(topics.items())))


if __name__ == "__main__":
    main()
