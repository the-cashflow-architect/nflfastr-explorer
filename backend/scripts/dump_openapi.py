"""Write the API's OpenAPI schema to a file: `python -m scripts.dump_openapi`.

The frontend's request and response types are generated from this rather than
hand-written. Hand-written types agree with the server exactly once — the moment
they are typed — and after that every backend change is a silent lie that
typechecks. Generating them means a renamed field is a build failure on the side
that has to care.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Importing the app must not start a download or touch the real database.
os.environ.setdefault("PRELOAD_ON_STARTUP", "false")
os.environ.setdefault("DUCKDB_PATH", str(Path(os.environ.get("TMPDIR", "/tmp")) / "openapi-scratch.duckdb"))

from app.main import app  # noqa: E402


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../frontend/openapi.json")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    paths = len(schema.get("paths", {}))
    print(f"Wrote {target} — {paths} paths, {len(schema.get('components', {}).get('schemas', {}))} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
