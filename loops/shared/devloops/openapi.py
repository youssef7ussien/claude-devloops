"""OpenAPI 3 parse check (FR-013a) and operation matching (FR-019, FR-024)."""
import json
import re
from urllib.parse import urlsplit

from .state import input_error

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def load_spec(path):
    """Load an OpenAPI 3 JSON document; stop with `invalid-api-spec` if it is not one."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise input_error("missing-input", f"API spec {path} cannot be read: {e.strerror or e}",
                          input="api-spec")
    try:
        spec = json.loads(text)
    except ValueError as e:
        raise input_error("invalid-api-spec", f"API spec {path} is not valid JSON: {e}",
                          input="api-spec")
    if not isinstance(spec, dict):
        raise input_error("invalid-api-spec", f"API spec {path} is not a JSON object",
                          input="api-spec")
    version = spec.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        raise input_error("invalid-api-spec",
                          f"API spec {path} has no 'openapi' field starting with '3.' "
                          f"(found {version!r})", input="api-spec")
    if not isinstance(spec.get("paths"), dict):
        raise input_error("invalid-api-spec", f"API spec {path} has no 'paths' object",
                          input="api-spec")
    return spec


def operations(spec):
    """Return the set of `(METHOD, path_template)` pairs the document declares."""
    ops = set()
    for template, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            if method in item:
                ops.add((method.upper(), template))
    return ops


def _request_path(url_or_path, base_url):
    path = urlsplit(url_or_path).path
    if base_url:
        base_path = urlsplit(base_url).path.rstrip("/")
        if base_path and (path == base_path or path.startswith(base_path + "/")):
            path = path[len(base_path):]
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def _template_regex(template):
    segments = []
    for segment in template.strip("/").split("/"):
        pieces = re.split(r"(\{[^}/]+\})", segment)
        segments.append("".join("[^/]+" if p.startswith("{") and p.endswith("}") else re.escape(p)
                                for p in pieces))
    return re.compile("^/" + "/".join(segments) + "$")


def match(spec, method, url_or_path, base_url=None):
    """Return the `(METHOD, path_template)` a request matches, or None.

    The base URL and the query are stripped first. A `{param}` matches any single path segment.
    When several templates match, the one with the fewest parameters wins (`/users/me` beats
    `/users/{id}`).
    """
    path = _request_path(url_or_path, base_url)
    method = method.upper()
    candidates = []
    for op_method, template in operations(spec):
        if op_method != method:
            continue
        normalized = template if len(template) <= 1 else template.rstrip("/")
        if _template_regex(normalized).match(path):
            candidates.append((template.count("{"), template))
    if not candidates:
        return None
    return method, min(candidates)[1]
