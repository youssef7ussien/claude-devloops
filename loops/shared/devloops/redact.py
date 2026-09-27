"""Secret redaction before anything is written (FR-070, research R-21)."""
import os
import re

MASK = "***"


class Redactor:
    """Replaces configured secret values with `***`.

    The values are `os.environ[name]` for each name in `secrets.env` (unset or empty names are
    skipped) plus every non-empty entry of `secrets.literals`.
    """

    def __init__(self, config=None, environ=None):
        environ = os.environ if environ is None else environ
        secrets = (config or {}).get("secrets") or {}
        values = {environ.get(name) for name in secrets.get("env", [])}
        values.update(secrets.get("literals", []))
        # Longest first, so a secret that contains another secret is masked as a whole.
        self.values = sorted((v for v in values if v), key=len, reverse=True)
        self._pattern = re.compile("|".join(re.escape(v) for v in self.values)) if self.values else None

    def redact(self, text):
        """Return `(redacted_text, changed)`."""
        if self._pattern is None or not isinstance(text, str):
            return text, False
        redacted, count = self._pattern.subn(MASK, text)
        return redacted, count > 0

    def redact_obj(self, obj):
        """Redact every string (keys included) in a JSON-like value; return `(obj, changed)`."""
        if self._pattern is None:
            return obj, False
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, list):
            items = [self.redact_obj(v) for v in obj]
            return [v for v, _ in items], any(c for _, c in items)
        if isinstance(obj, dict):
            out, changed = {}, False
            for key, value in obj.items():
                new_key, key_changed = self.redact(key)
                new_value, value_changed = self.redact_obj(value)
                out[new_key] = new_value
                changed = changed or key_changed or value_changed
            return out, changed
        return obj, False
