import os
import unittest

import helpers  # noqa: F401  (puts the package on sys.path)
import samples
from devloops import schema


class EverySchemaFileTest(unittest.TestCase):
    """One valid and one invalid sample for each schema file."""

    CASES = {
        "config.schema.json": (samples.config, lambda d: d.update(max_trials=0)),
        "plan.schema.json": (samples.plan, lambda d: d["milestones"][0].update(id="X1")),
        "checks.schema.json": (samples.checks,
                               lambda d: d["checks"][0]["request"].update(method="FETCH")),
        "validation-result.schema.json": (samples.validation_result, lambda d: d.pop("boundary")),
        "invocation-record.schema.json": (samples.invocation_record,
                                          lambda d: d["tokens"].update(input=-1)),
        "run-state.schema.json": (samples.run_state, lambda d: d.update(status="running")),
    }

    def test_cases_cover_every_schema_file(self):
        files = sorted(n for n in os.listdir(schema.SCHEMAS_DIR) if n.endswith(".schema.json"))
        self.assertEqual(sorted(self.CASES), files)

    def test_valid_samples_pass(self):
        for name, (make, _) in self.CASES.items():
            with self.subTest(schema=name):
                self.assertEqual(schema.validate(make(), name), [])

    def test_invalid_samples_fail(self):
        for name, (make, mutate) in self.CASES.items():
            with self.subTest(schema=name):
                doc = make()
                mutate(doc)
                self.assertNotEqual(schema.validate(doc, name), [])


class KeywordTest(unittest.TestCase):
    def check(self, value, sch):
        return schema.check(value, sch)

    def test_type_lists_and_null(self):
        sch = {"type": ["string", "null"]}
        self.assertEqual(self.check(None, sch), [])
        self.assertEqual(self.check("x", sch), [])
        self.assertEqual(len(self.check(3, sch)), 1)

    def test_booleans_are_not_numbers(self):
        self.assertNotEqual(self.check(True, {"type": "integer"}), [])
        self.assertNotEqual(self.check(False, {"type": "number"}), [])
        self.assertEqual(self.check(2.0, {"type": "integer"}), [])
        self.assertNotEqual(self.check(2.5, {"type": "integer"}), [])

    def test_enum_and_const_use_json_equality(self):
        self.assertNotEqual(self.check(True, {"enum": [1]}), [])
        self.assertEqual(self.check(None, {"enum": ["a", None]}), [])
        self.assertNotEqual(self.check(1, {"const": True}), [])
        self.assertEqual(self.check({"a": [1]}, {"const": {"a": [1]}}), [])

    def test_required_properties_and_additional(self):
        sch = {"type": "object", "required": ["a"], "properties": {"a": {"type": "string"}},
               "additionalProperties": False}
        self.assertEqual(self.check({"a": "x"}, sch), [])
        errors = self.check({"b": 1}, sch)
        self.assertIn("$: missing required property 'a'", errors)
        self.assertIn("$: unexpected property 'b'", errors)
        typed = {"type": "object", "additionalProperties": {"type": "string"}}
        self.assertEqual(self.check({"k": 1}, typed), ["$.k: expected string, got number"])

    def test_items_min_items_min_length_pattern_minimum(self):
        sch = {"type": "array", "minItems": 1,
               "items": {"type": "string", "minLength": 2, "pattern": "^M[0-9]{2}$"}}
        self.assertEqual(self.check(["M01"], sch), [])
        self.assertEqual(len(self.check([], sch)), 1)
        errors = self.check(["M"], sch)
        self.assertTrue(any("shorter" in e for e in errors))
        self.assertTrue(any("pattern" in e for e in errors))
        self.assertEqual(len(self.check(0, {"type": "integer", "minimum": 1})), 1)

    def test_error_paths_point_at_the_value(self):
        doc = samples.plan()
        doc["milestones"][1]["tasks"][0]["requirement_refs"] = []
        errors = schema.validate(doc, "plan.schema.json")
        self.assertEqual(errors, ["$.milestones[1].tasks[0].requirement_refs: needs at least 1 "
                                  "item(s), got 0"])

    def test_ref_to_sibling_file(self):
        run = samples.run_state()
        run["effective_config"] = {"max_trials": "three"}
        errors = schema.validate(run, "run-state.schema.json")
        self.assertEqual(errors, ["$.effective_config.max_trials: expected integer, got string"])

    def test_local_ref(self):
        sch = {"definitions": {"id": {"type": "string"}}, "type": "array",
               "items": {"$ref": "#/definitions/id"}}
        self.assertEqual(self.check(["a"], sch), [])
        self.assertEqual(len(self.check([1], sch)), 1)


if __name__ == "__main__":
    unittest.main()
