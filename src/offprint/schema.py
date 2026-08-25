"""Published JSON Schema, derived from the pydantic models."""

from __future__ import annotations

import json
from typing import Any

from offprint.model import Article, RunManifest

ARTICLE_SCHEMA_ID = (
    "https://raw.githubusercontent.com/eugenmihailescu/offprint/main/"
    "schemas/offprint-article.v1.json"
)
RUN_SCHEMA_ID = (
    "https://raw.githubusercontent.com/eugenmihailescu/offprint/main/schemas/offprint-run.v1.json"
)
JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def dump_article_schema() -> dict[str, Any]:
    """JSON Schema for ``offprint-article`` v1 (library; CLI wires this in PR 5)."""
    return _publish(
        Article.model_json_schema(),
        schema_id=ARTICLE_SCHEMA_ID,
        title="Offprint Article",
    )


def dump_run_schema() -> dict[str, Any]:
    """JSON Schema for ``offprint-run`` v1."""
    return _publish(
        RunManifest.model_json_schema(),
        schema_id=RUN_SCHEMA_ID,
        title="Offprint Run Manifest",
    )


def schema_to_json(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def _publish(schema: dict[str, Any], *, schema_id: str, title: str) -> dict[str, Any]:
    published = {
        "$schema": JSON_SCHEMA_DRAFT,
        "$id": schema_id,
        **schema,
    }
    published["title"] = title
    published["additionalProperties"] = True
    _allow_unknown_object_keys(published)
    return published


def _allow_unknown_object_keys(node: object) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = True
        for value in node.values():
            _allow_unknown_object_keys(value)
    elif isinstance(node, list):
        for item in node:
            _allow_unknown_object_keys(item)
