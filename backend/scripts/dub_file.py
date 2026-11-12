"""Run the Studio pipeline on a local video without the web server (M2 acceptance check).

    cd backend
    python -m scripts.dub_file my_reel.mp4 --langs ta-IN
    python -m scripts.dub_file my_reel.mp4 --langs ta-IN --no-separate   # skip Demucs

Prints stage timings and the output paths. Run it twice to see the cache skip STT.
"""
import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.studio.runner import StudioRunner  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--langs", default="ta-IN")
    ap.add_argument("--no-separate", action="store_true")
    a = ap.parse_args()

    s = get_settings()
    if a.no_separate:
        s = s.model_copy(update={"studio_separate": False})
    runner = StudioRunner(settings=s)
    tmp = Path(tempfile.mkdtemp()) / Path(a.video).name
    shutil.copyfile(a.video, tmp)
    job = await runner.create_job(tmp, Path(a.video).name, [x.strip() for x in a.langs.split(",") if x.strip()])
    print(f"job {job['id']} ({job['duration_s']:.1f} s)")
    await runner.run(job["id"])
    job = await runner.store.get("jobs", job["id"])
    print(f"status: {job['status']}  {job.get('error') or ''}")
    print(json.dumps(job["stage_timings"], indent=1, ensure_ascii=False))
    for r in await runner.store.select("renders", job_id=job["id"]):
        print(f"[{r['lang']}] {runner.job_dir(job['id']) / 'out' / r['mp4_path']}")


if __name__ == "__main__":
    asyncio.run(main())
