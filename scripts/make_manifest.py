"""Write the update-feed manifests the app polls (stable.json / beta.json).

    python scripts/make_manifest.py --repo owner/name --version 1.2.0 --tag v1.2.0 \
        --installer dist/installer/ZuqongtechPlanner-Setup-1.2.0.exe \
        --notes notes.md --channel stable --feed feed/

Stable releases update stable.json, and beta.json too if newer (beta users also get stable
releases). Beta releases only update beta.json. A manifest is never replaced by an older version.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from planner.versioning import is_newer  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--installer", required=True)
    ap.add_argument("--channel", choices=["stable", "beta"], required=True)
    ap.add_argument("--feed", required=True, help="folder holding current stable.json / beta.json")
    ap.add_argument("--notes", help="markdown release notes file")
    ap.add_argument("--base-url", help="override download base URL (testing)")
    a = ap.parse_args()

    inst = Path(a.installer)
    base = a.base_url or f"https://github.com/{a.repo}/releases/download/{a.tag}"
    notes = Path(a.notes).read_text(encoding="utf-8") if a.notes and Path(a.notes).exists() else ""
    manifest = {
        "schema": 1,
        "version": a.version,
        "tag": a.tag,
        "prerelease": a.channel == "beta",
        "published": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notes": notes,
        "page": f"https://github.com/{a.repo}/releases/tag/{a.tag}",
        "asset_name": inst.name,
        "url": f"{base}/{inst.name}",
        "size": inst.stat().st_size,
        "sha256": sha256(inst),
    }
    feed = Path(a.feed)
    feed.mkdir(parents=True, exist_ok=True)
    for channel in (["stable", "beta"] if a.channel == "stable" else ["beta"]):
        f = feed / f"{channel}.json"
        if f.exists():
            try:
                current = json.loads(f.read_text(encoding="utf-8"))["version"]
            except (ValueError, KeyError):
                current = None
            if current and not is_newer(a.version, current):
                print(f"{f.name}: keeps {current} (not older than {a.version})")
                continue
        f.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"{f.name}: -> {a.version}")


if __name__ == "__main__":
    main()
