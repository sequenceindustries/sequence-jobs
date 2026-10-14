"""Development-only connector that reads a local JSON file.

Records produced through a source with is_dev_data = true are flagged in the database and are
never shown as real vacancies in production (see api.py). Fixture data is SYNTHETIC.
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import BaseConnector, FetchResult
from .json_feed import map_item
from .registry import register


@register
class FixtureConnector(BaseConnector):
    key = "fixture"

    def fetch(self) -> FetchResult:
        path = Path(self.config["path"])
        fmap = self.config["field_map"]
        data = json.loads(path.read_text())
        records, errors = [], []
        for it in data:
            try:
                records.append(map_item(it, fmap, f"file://{path.name}"))
            except Exception as e:
                errors.append((str(it.get("id", "?")), f"map error: {e}"))
        return FetchResult(records, complete_snapshot=bool(self.config.get("complete_snapshot", True))
                           and not errors, parse_errors=errors)
