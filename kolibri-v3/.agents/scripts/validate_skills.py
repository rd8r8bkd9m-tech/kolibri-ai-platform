from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
expected = int(sys.argv[1]) if len(sys.argv) > 1 else 250

all_files = sorted((root / "skills").rglob("SKILL.md"))


def parts_of(path):
    return path.relative_to(root / "skills").parts


# Package: grouped skills `<NN-*>/<skill>/SKILL.md` with the strict execution
# contract. Flat project skills (assistant-ui, expo-*, kolibri-*, ...) only
# need frontmatter.
package = [
    p
    for p in all_files
    if len(parts_of(p)) == 3 and re.match(r"^\d{2}-", parts_of(p)[0])
]
flat = [p for p in all_files if p not in package]

errors = []
for p in package:
    s = p.read_text()
    if not s.startswith("---\n"):
        errors.append(f"{p}: missing frontmatter")
    for key in ("name:", "description:", "version:"):
        if re.search(r"^" + re.escape(key), s, re.M) is None:
            errors.append(f"{p}: missing {key}")
    for section in (
        "## Development-first execution contract",
        "### Mandatory order",
        "### Anti-loop rules",
        "### Completion gate",
        "### Failure gate",
    ):
        if section not in s:
            errors.append(f"{p}: missing {section}")

if len(package) != expected:
    errors.append(f"package count={len(package)} expected={expected}")

for p in flat:
    s = p.read_text()
    if not s.startswith("---\n"):
        errors.append(f"{p}: missing frontmatter")
    for key in ("name:", "description:"):
        if re.search(r"^" + re.escape(key), s, re.M) is None:
            errors.append(f"{p}: missing {key}")

if errors:
    print("\n".join(errors[:25]))
    print(f"... total errors: {len(errors)}")
    sys.exit(1)

print(f"OK: package={len(package)} flat={len(flat)} skills validated")
