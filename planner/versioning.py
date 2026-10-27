"""Version parsing, bumping and GitHub release selection. Pure Python (used by app and CI).

Versions: MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-(alpha|beta|rc).N, optional leading "v".
"""
import re

_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?$")
_STAGE = {"alpha": 0, "beta": 1, "rc": 2, None: 3}          # 3 = final release sorts last
_STAGE_NAME = {v: k for k, v in _STAGE.items() if k}


def parse_version(s: str) -> tuple:
    m = _RE.match(s.strip())
    if not m:
        raise ValueError(f"Not a version: {s!r}")
    major, minor, patch, stage, n = m.groups()
    return int(major), int(minor), int(patch), _STAGE[stage], int(n or 0)


def format_version(v: tuple) -> str:
    major, minor, patch, stage, n = v
    base = f"{major}.{minor}.{patch}"
    return base if stage == 3 else f"{base}-{_STAGE_NAME[stage]}.{n}"


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def bump(current: str, kind: str = "patch", channel: str = "stable") -> str:
    """Next version.
    stable: 1.2.0-beta.3 -> 1.2.0 (finalise), else bump kind: 1.2.0 -> 1.2.1 / 1.3.0 / 2.0.0
    beta:   1.2.0-beta.3 -> 1.2.0-beta.4, else bump kind then -beta.1: 1.2.0 -> 1.2.1-beta.1
    """
    major, minor, patch, stage, n = parse_version(current)
    pre = stage != 3
    if pre and channel == "stable":
        return format_version((major, minor, patch, 3, 0))
    if pre and channel == "beta":
        return format_version((major, minor, patch, stage, n + 1))
    if kind == "major":
        base = (major + 1, 0, 0)
    elif kind == "minor":
        base = (major, minor + 1, 0)
    elif kind == "patch":
        base = (major, minor, patch + 1)
    else:
        raise ValueError(f"Unknown bump kind: {kind}")
    return format_version((*base, 1, 1) if channel == "beta" else (*base, 3, 0))


def select_release(releases, current: str, channel: str, asset_pattern: str):
    """Pick the newest installable release newer than `current` from GitHub's
    /releases API payload. Stable channel ignores pre-releases. Returns a dict or None."""
    best = None
    for r in releases or []:
        if r.get("draft") or (r.get("prerelease") and channel != "beta"):
            continue
        try:
            v = parse_version(r.get("tag_name", ""))
        except ValueError:
            continue
        assets = r.get("assets") or []
        setup = next((a for a in assets if re.fullmatch(asset_pattern, a.get("name", ""))), None)
        if not setup:
            continue
        if best is None or v > best[0]:
            best = (v, r, setup, assets)
    if best is None or best[0] <= parse_version(current):
        return None
    v, r, setup, assets = best
    sha = next((a for a in assets if a.get("name") == setup["name"] + ".sha256"), None)
    return {
        "version": format_version(v),
        "tag": r.get("tag_name"),
        "prerelease": bool(r.get("prerelease")),
        "notes": r.get("body") or "",
        "page": r.get("html_url", ""),
        "published": r.get("published_at", ""),
        "asset_name": setup["name"],
        "url": setup["browser_download_url"],
        "size": setup.get("size", 0),
        "sha_url": sha["browser_download_url"] if sha else None,
    }


def manifest_to_info(m: dict, current: str):
    """Validate an update-feed manifest (stable.json / beta.json, written by
    scripts/make_manifest.py). Returns an info dict if it is newer than `current`."""
    if not all(m.get(k) for k in ("version", "asset_name", "url", "sha256")):
        raise ValueError("Incomplete update manifest")
    if len(m["sha256"]) != 64:
        raise ValueError("Bad checksum in update manifest")
    if not is_newer(m["version"], current):
        return None
    return {
        "version": format_version(parse_version(m["version"])),
        "tag": m.get("tag", ""),
        "prerelease": bool(m.get("prerelease")),
        "notes": m.get("notes", ""),
        "page": m.get("page", ""),
        "published": m.get("published", ""),
        "asset_name": m["asset_name"],
        "url": m["url"],
        "size": int(m.get("size") or 0),
        "sha256": m["sha256"].lower(),
        "sha_url": None,
    }
