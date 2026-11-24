#!/usr/bin/env python3
"""Check that the docs keep up with the code. Python 3 standard library only.

    python scripts/docs/docs-check.py                 # all checks
    python scripts/docs/docs-check.py --no-changelog  # skip the CHANGELOG check

Checks:
  (a) FAIL if a generated block is stale (scripts/docs/gen_docs.py --check).
  (b) FAIL if code or config changed since CHANGELOG.md was last committed and CHANGELOG.md is not
      changed in the working tree as well.
  (c) WARN if docs/handbook mentions an ADR-NNNN or EXP-NNN id that has no file.

Run it by hand (or in CI). It is deliberately not a git hook.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

CODE_PREFIXES = ("backend/", "web/", "gpu_engine_v1/", "scripts/")
EXCLUDED_PREFIXES = ("scripts/docs/",)
CONFIG_PATTERNS = (
    "docker-compose*.yml", "docker-compose*.yaml", "Caddyfile*", ".env.example", "*.env.example",
    ".gitignore", ".gitattributes", ".githooks/*", "requirements*.txt", "package.json", "dev.ps1",
)


def git(root: Path, *args: str) -> str:
    res = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def repo_root() -> Path:
    here = Path(__file__).resolve().parent
    res = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit("docs-check: not inside a git repository")
    return Path(res.stdout.strip())


def is_code(path: str) -> bool:
    p = path.replace("\\", "/").strip().strip('"')
    if p.startswith(EXCLUDED_PREFIXES):
        return False
    if p.startswith(CODE_PREFIXES):
        return True
    return any(fnmatch.fnmatch(p, pat) for pat in CONFIG_PATTERNS)


def porcelain_paths(root: Path) -> list[str]:
    paths = []
    for line in git(root, "status", "--porcelain", "--untracked-files=all").splitlines():
        if len(line) < 4:
            continue
        p = line[3:]
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        paths.append(p.strip().strip('"'))
    return paths


def check_generated(root: Path) -> bool:
    res = subprocess.run([sys.executable, str(root / "scripts" / "docs" / "gen_docs.py"), "--check"],
                         capture_output=True, text=True)
    out = (res.stdout + res.stderr).strip()
    if res.returncode == 0:
        print("OK   generated blocks are up to date")
        return True
    print("FAIL generated blocks are stale; run scripts/docs/gen_docs.py (or gen-docs.ps1)")
    for line in out.splitlines():
        print("     " + line)
    return False


def check_changelog(root: Path) -> bool:
    dirty = porcelain_paths(root)
    if "CHANGELOG.md" in dirty:
        print("OK   CHANGELOG.md is changed in the working tree")
        return True
    last = git(root, "log", "-1", "--format=%H", "--", "CHANGELOG.md").strip()
    if not last:
        print("FAIL CHANGELOG.md has never been committed and is not in the working tree")
        return False
    changed = set(p for p in git(root, "log", f"{last}..HEAD", "--name-only", "--format=").splitlines() if p)
    changed.update(dirty)
    code = sorted(p for p in changed if is_code(p))
    if not code:
        print(f"OK   no code or config changed since CHANGELOG.md was last edited ({last[:7]})")
        return True
    print(f"FAIL code or config changed since CHANGELOG.md was last edited ({last[:7]}); "
          "add an entry under [Unreleased]:")
    for p in code[:30]:
        print("     " + p)
    if len(code) > 30:
        print(f"     ... and {len(code) - 30} more")
    return False


def check_ids(root: Path) -> None:
    hb = root / "docs" / "handbook"
    if not hb.exists():
        print("WARN docs/handbook does not exist")
        return
    missing: dict[str, set[str]] = {}
    for f in sorted(hb.rglob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = f.relative_to(root).as_posix()
        for m in re.finditer(r"ADR-(\d{4})", text):
            if not list((hb / "adr").glob(f"{m.group(1)}-*.md")):
                missing.setdefault(m.group(0), set()).add(rel)
        for m in re.finditer(r"EXP-(\d{3})", text):
            if not list((hb / "experiments").glob(f"{m.group(0)}-*.md")):
                missing.setdefault(m.group(0), set()).add(rel)
    if not missing:
        print("OK   every ADR/EXP id in docs/handbook has a file")
        return
    for ident in sorted(missing):
        where = ", ".join(sorted(missing[ident])[:3])
        print(f"WARN {ident} has no file (mentioned in {where})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-changelog", action="store_true", help="skip the CHANGELOG check")
    args = ap.parse_args()
    root = repo_root()
    ok = check_generated(root)
    if args.no_changelog:
        print("SKIP CHANGELOG check (--no-changelog)")
    else:
        ok = check_changelog(root) and ok
    check_ids(root)
    print("docs-check: " + ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
