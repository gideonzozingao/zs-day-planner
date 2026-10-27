"""Bump planner.__version__ and print the new version.

    python scripts/bump_version.py patch stable     1.0.0 -> 1.0.1
    python scripts/bump_version.py minor beta       1.0.1 -> 1.1.0-beta.1
    python scripts/bump_version.py patch beta       1.1.0-beta.1 -> 1.1.0-beta.2
    python scripts/bump_version.py patch stable     1.1.0-beta.2 -> 1.1.0
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from planner.versioning import bump  # noqa: E402

INIT = ROOT / "planner" / "__init__.py"


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "patch"
    channel = sys.argv[2] if len(sys.argv) > 2 else "stable"
    text = INIT.read_text(encoding="utf-8")
    current = re.search(r'__version__ = "([^"]+)"', text).group(1)
    new = bump(current, kind, channel)
    INIT.write_text(text.replace(f'__version__ = "{current}"', f'__version__ = "{new}"'), encoding="utf-8")
    print(new)


if __name__ == "__main__":
    main()
