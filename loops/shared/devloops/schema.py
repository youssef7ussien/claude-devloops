"""A stdlib validator for the JSON Schema subset used by `loops/shared/schemas/`.

Supported keywords: `type` (including lists and `null`), `enum`, `const`, `required`,
`properties`, `additionalProperties` (bool or schema), `items`, `minItems`, `minLength`,
`pattern`, `minimum`, and `$ref` to a sibling schema file or a local `#/...` pointer.
Annotation keywords (`$schema`, `$id`, `title`, `description`, `default`, `format`) are ignored.
"""
import json
import os
import re

from .kit import Kit

SCHEMAS_DIR = Kit.resolve().path("shared", "schemas")

_cache = {}


def load(schema_name, schemas_dir=SCHEMAS_DIR):
    path = os.path.join(schemas_dir, schema_name)
    if path not in _cache:
        with open(path, encoding="utf-8") as f:
            _cache[path] = json.load(f)
    return _cache[path]


def validate(instance, schema_name, schemas_dir=SCHEMAS_DIR):
    """Validate against a schema file by name; return a list of `"<path>: <problem>"` errors."""
    schema = load(schema_name, schemas_dir)
    return check(instance, schema, schemas_dir=schemas_dir)


def check(instance, schema, schemas_dir=SCHEMAS_DIR, root=None):
    """Validate against an in-memory schema; `$ref`s resolve relative to `schemas_dir`."""
    errors = []
    _validate(instance, schema, "$", root if root is not None else schema, schemas_dir, errors)
    return errors


def _type_ok(value, name):
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise ValueError(f"unsupported schema type: {name!r}")


def _equal(a, b):
    """JSON equality: unlike Python, `true != 1`."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return a == b


def _resolve_ref(ref, root, schemas_dir):
    filename, _, pointer = ref.partition("#")
    target = load(filename, schemas_dir) if filename else root
    for part in [p for p in pointer.split("/") if p]:
        target = target[part.replace("~1", "/").replace("~0", "~")]
    return target, (load(filename, schemas_dir) if filename else root)


def _validate(value, schema, path, root, schemas_dir, errors):
    if schema is True or schema == {}:
        return
    if schema is False:
        errors.append(f"{path}: no value is allowed here")
        return

    if "$ref" in schema:
        target, target_root = _resolve_ref(schema["$ref"], root, schemas_dir)
        _validate(value, target, path, target_root, schemas_dir, errors)

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in types):
            errors.append(f"{path}: expected {' or '.join(types)}, got {_json_type(value)}")
            return

    if "const" in schema and not _equal(value, schema["const"]):
        errors.append(f"{path}: must equal {json.dumps(schema['const'])}")
    if "enum" in schema and not any(_equal(value, e) for e in schema["enum"]):
        errors.append(f"{path}: {json.dumps(value)} is not one of {json.dumps(schema['enum'])}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match pattern {schema['pattern']!r}")

    if _type_ok(value, "number") and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: {value} is less than the minimum {schema['minimum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: needs at least {schema['minItems']} item(s), got {len(value)}")
        if "items" in schema:
            for i, item in enumerate(value):
                _validate(item, schema["items"], f"{path}[{i}]", root, schemas_dir, errors)

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], f"{path}.{key}", root, schemas_dir, errors)
            elif additional is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(additional, dict):
                _validate(item, additional, f"{path}.{key}", root, schemas_dir, errors)


def _json_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"
