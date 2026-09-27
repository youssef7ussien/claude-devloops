import unittest

import helpers  # noqa: F401
from devloops.redact import Redactor


class RedactTest(unittest.TestCase):
    def test_env_and_literal_values(self):
        r = Redactor({"secrets": {"env": ["API_KEY", "UNSET", "EMPTY"], "literals": ["pw123"]}},
                     environ={"API_KEY": "sk-abc", "EMPTY": ""})
        self.assertEqual(r.values, ["sk-abc", "pw123"])
        self.assertEqual(r.redact("key=sk-abc pass=pw123"), ("key=*** pass=***", True))

    def test_no_secrets_is_a_no_op(self):
        r = Redactor({}, environ={})
        self.assertEqual(r.redact("nothing"), ("nothing", False))
        obj = {"a": ["b"]}
        self.assertEqual(r.redact_obj(obj), (obj, False))

    def test_unchanged_text_reports_false(self):
        r = Redactor({"secrets": {"literals": ["zzz"]}})
        self.assertEqual(r.redact("clean"), ("clean", False))

    def test_longest_first(self):
        r = Redactor({"secrets": {"literals": ["abc", "abcdef"]}})
        self.assertEqual(r.redact("x abcdef y abc"), ("x *** y ***", True))

    def test_regex_characters_are_literal(self):
        r = Redactor({"secrets": {"literals": ["a.b*c"]}})
        self.assertEqual(r.redact("axbbc a.b*c"), ("axbbc ***", True))

    def test_redact_obj_recurses_into_keys_and_values(self):
        r = Redactor({"secrets": {"literals": ["tok"]}})
        obj = {"tok-key": ["tok", {"n": 1, "s": "a tok b"}], "flag": True, "none": None}
        out, changed = r.redact_obj(obj)
        self.assertTrue(changed)
        self.assertEqual(out, {"***-key": ["***", {"n": 1, "s": "a *** b"}], "flag": True,
                               "none": None})
        self.assertEqual(obj["tok-key"][0], "tok")  # the input is not mutated

    def test_non_strings_pass_through(self):
        r = Redactor({"secrets": {"literals": ["1"]}})
        self.assertEqual(r.redact(1), (1, False))


if __name__ == "__main__":
    unittest.main()
