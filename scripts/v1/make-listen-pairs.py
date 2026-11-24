"""Build the pairs folder of the blind listening test (/listen-test) from two folders of same-named clips.

  backend\\.venv\\Scripts\\python.exe scripts\\v1\\make-listen-pairs.py FOLDER_A FOLDER_B \\
      --system-a indicf5 --system-b other [--lang ta-IN] [--texts lines.json] [--name "what this set is"] \\
      [--out data-v1\\listen\\pairs] [--add]

Every file name that is in both folders (.wav, .mp3, .ogg, .flac) becomes one pair: the clip from FOLDER_A is
system A's, the one from FOLDER_B is system B's. The clips are copied into OUT/a/ and OUT/b/ under numbered names
(the listener never sees a name, but nothing in the folder should give the system away either) and
OUT/manifest.json is written. `--texts` is a JSON object {"<file name without its ending>": "the words the clip
should say"}; `--lang` may also be read from a name that starts with a language code ("ta-IN_003.wav").
`--add` keeps the pairs already in OUT and adds these; without it OUT must be empty or absent.

The manifest format is in docs/v1/RUNBOOK.md and in backend/app/v1/listen.py. Nothing here goes into the repository:
OUT is in the data folder.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

KINDS = (".wav", ".mp3", ".ogg", ".flac")
LANG = re.compile(r"^([a-z]{2}-[A-Z]{2})[_-]")


def build(a: Path, b: Path, out: Path, system_a: str, system_b: str, *, lang: str = "", texts: dict[str, str] | None = None,
          name: str = "", add: bool = False) -> dict:
    if not system_a or not system_b or system_a == system_b:
        raise ValueError("the two systems need two different names")
    fa = {f.name: f for f in sorted(a.iterdir()) if f.suffix.lower() in KINDS}
    fb = {f.name: f for f in sorted(b.iterdir()) if f.suffix.lower() in KINDS}
    both = [n for n in fa if n in fb]
    if not both:
        raise ValueError("no file name is in both folders")
    man_file = out / "manifest.json"
    man = {"name": name, "pairs": []}
    if man_file.exists():
        if not add:
            raise ValueError(f"{man_file} exists: use --add to add to it, or another --out")
        man = json.loads(man_file.read_text(encoding="utf-8"))
        man["name"] = name or man.get("name", "")
    n0 = len(man["pairs"])
    (out / "a").mkdir(parents=True, exist_ok=True)
    (out / "b").mkdir(parents=True, exist_ok=True)
    for i, fname in enumerate(both, start=n0 + 1):
        stem, end = Path(fname).stem, Path(fname).suffix.lower()
        shutil.copyfile(fa[fname], out / "a" / f"{i:04d}{end}")
        shutil.copyfile(fb[fname], out / "b" / f"{i:04d}{end}")
        m = LANG.match(fname)
        pair = {"id": f"p{i:04d}", "a": f"a/{i:04d}{end}", "b": f"b/{i:04d}{end}", "system_a": system_a,
                "system_b": system_b, "lang": lang or (m.group(1) if m else "")}
        if texts and texts.get(stem):
            pair["text"] = texts[stem]
        man["pairs"].append(pair)
    man_file.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"out": str(out), "pairs_added": len(both), "pairs": len(man["pairs"]),
            "only_in_a": sorted(set(fa) - set(fb)), "only_in_b": sorted(set(fb) - set(fa))}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder_a")
    ap.add_argument("folder_b")
    ap.add_argument("--system-a", required=True)
    ap.add_argument("--system-b", required=True)
    ap.add_argument("--lang", default="")
    ap.add_argument("--texts", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--out", default=str(root / "data-v1" / "listen" / "pairs"))
    ap.add_argument("--add", action="store_true")
    a = ap.parse_args()
    texts = json.loads(Path(a.texts).read_text(encoding="utf-8")) if a.texts else None
    try:
        res = build(Path(a.folder_a), Path(a.folder_b), Path(a.out), a.system_a, a.system_b, lang=a.lang, texts=texts,
                    name=a.name, add=a.add)
    except (ValueError, OSError) as e:
        sys.exit(f"not built: {e}")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
