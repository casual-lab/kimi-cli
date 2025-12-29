from __future__ import annotations

from typing import Any

import jsonschema

SCENARIO_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["meta", "steps"],
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "meta": {
            "type": "object",
            "required": ["command"],
            "properties": {
                "id": {"type": "string"},
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "cwd": {"type": "string"},
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "pty": {
                    "type": "object",
                    "properties": {
                        "rows": {"type": "integer", "minimum": 1},
                        "cols": {"type": "integer", "minimum": 1},
                    },
                    "required": ["rows", "cols"],
                },
                "timeout": {"type": "number", "minimum": 0},
                "read_timeout": {"type": "number", "minimum": 0},
                "output_dir": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "oneOf": [
                    {
                        "type": "object",
                        "required": ["type", "run"],
                        "properties": {
                            "type": {"const": "command"},
                            "run": {"type": "string"},
                            "mark": {"type": "string"},
                            "expect": {"$ref": "#/definitions/expectation"},
                            "timeout": {"type": "number", "minimum": 0},
                            "delay": {"type": "number", "minimum": 0},
                            "send_newline": {"type": "boolean"},
                        },
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "required": ["type", "expect"],
                        "properties": {
                            "type": {"const": "wait"},
                            "expect": {"$ref": "#/definitions/expectation"},
                            "timeout": {"type": "number", "minimum": 0},
                        },
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "required": ["type", "label"],
                        "properties": {
                            "type": {"const": "snapshot"},
                            "label": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "required": ["type", "rows", "cols"],
                        "properties": {
                            "type": {"const": "resize"},
                            "rows": {"type": "integer", "minimum": 1},
                            "cols": {"type": "integer", "minimum": 1},
                        },
                        "additionalProperties": False,
                    },
                ]
            },
        },
    },
    "additionalProperties": False,
    "definitions": {
        "expectation": {
            "type": "object",
            "properties": {
                "contains": {"type": "string"},
                "regex": {"type": "string"},
            },
            "minProperties": 1,
            "additionalProperties": False,
        }
    },
}


def validate_scenario(payload: dict[str, Any]) -> None:
    jsonschema.validate(instance=payload, schema=SCENARIO_SCHEMA)
