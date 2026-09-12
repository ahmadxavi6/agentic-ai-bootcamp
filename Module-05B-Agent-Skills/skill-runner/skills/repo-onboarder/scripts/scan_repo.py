"""scan_repo.py — the eyes for the repo-onboarder skill.

Takes a path on stdin. Prints a factual inventory of what is actually there.

The model is good at explaining a codebase and bad at remembering one. So the
script does the looking and the model does the talking. That split is the whole
design pattern: FACTS FROM CODE, PROSE FROM THE MODEL.
"""

import os
import sys
from collections import Counter
from pathlib import Path

# This script is run as a subprocess and its stdout is piped. On Windows that
# pipe defaults to cp1252, so a single em-dash in someone's README crashes the
# whole scan. Force UTF-8 both ways.
for stream in (sys.stdout, sys.stdin):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SKIP = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".next", ".idea", ".vscode", "site-packages",
}
ENTRY_HINTS = {
    "main.py", "app.py", "__main__.py", "manage.py", "index.js", "main.js",
    "server.js", "index.ts", "main.go", "Program.cs", "Makefile", "Dockerfile",
}
DEP_FILES = {
    "requirements.txt", "pyproject.toml", "package.json", "go.mod",
    "Cargo.toml", "pom.xml", "Gemfile", "environment.yml",
}
MAX_TREE = 60
MAX_EMBED = 2500


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
        for f in filenames:
            yield Path(dirpath) / f


def main() -> None:
    raw = sys.stdin.read().strip().strip('"').strip("'")
    root = Path(raw or ".").expanduser()

    if not root.exists():
        print(f"ERROR: path does not exist: {root}")
        return
    if root.is_file():
        root = root.parent

    files = list(walk(root))
    if not files:
        print(f"ERROR: no readable files under {root}")
        return

    exts = Counter(f.suffix.lower() or "(no ext)" for f in files)
    total_kb = sum(f.stat().st_size for f in files) / 1024

    print(f"REPO SCAN: {root.resolve()}")
    print(f"files: {len(files)}   size: {total_kb:,.0f} KB")

    print("\nLANGUAGES / FILE TYPES (top 10)")
    for ext, n in exts.most_common(10):
        print(f"  {ext:<12} {n}")

    print(f"\nTREE (first {MAX_TREE} files, relative)")
    for f in sorted(files)[:MAX_TREE]:
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = f
        print(f"  {rel}")
    if len(files) > MAX_TREE:
        print(f"  ... and {len(files) - MAX_TREE} more")

    entries = [f for f in files if f.name in ENTRY_HINTS]
    print("\nPOSSIBLE ENTRY POINTS")
    if entries:
        for f in entries:
            print(f"  {f.relative_to(root)}")
    else:
        print("  none found")

    deps = [f for f in files if f.name in DEP_FILES]
    print("\nDEPENDENCY MANIFESTS")
    if deps:
        for f in deps:
            print(f"\n  --- {f.relative_to(root)} ---")
            print("  " + f.read_text(encoding="utf-8", errors="replace")[:MAX_EMBED].replace("\n", "\n  "))
    else:
        print("  none found")

    readmes = [f for f in files if f.name.lower().startswith("readme")]
    print("\nREADME")
    if readmes:
        r = readmes[0]
        print(f"  --- {r.relative_to(root)} ---")
        print("  " + r.read_text(encoding="utf-8", errors="replace")[:MAX_EMBED].replace("\n", "\n  "))
    else:
        print("  none found")


if __name__ == "__main__":
    main()
