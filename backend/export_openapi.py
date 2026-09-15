#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema to ``openapi.yaml`` next to this script.

Usage:  python export_openapi.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import yaml  # noqa: E402

from app.main import app  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "openapi.yaml"


def main() -> int:
    schema = app.openapi()
    schema["info"]["x-generated-by"] = "export_openapi.py"
    with OUT.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(schema, fh, sort_keys=False, allow_unicode=True, width=100)
    print(f"openapi.yaml written: {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
