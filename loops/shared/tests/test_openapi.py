import json
import os
import tempfile
import unittest

import helpers  # noqa: F401
from devloops import openapi, state

SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "t", "version": "1"},
    "paths": {
        "/items": {"get": {}, "post": {}, "parameters": []},
        "/items/{id}": {"get": {}, "delete": {}, "summary": "one item"},
        "/items/me": {"get": {}},
        "/files/{name}.{ext}": {"get": {}},
        "/": {"get": {}},
    },
}


class LoadSpecTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, content):
        path = os.path.join(self.tmp.name, "openapi.json")
        with open(path, "w") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
        return path

    def assert_invalid(self, content, code="invalid-api-spec"):
        with self.assertRaises(state.StopRun) as cm:
            openapi.load_spec(self.write(content))
        self.assertEqual((cm.exception.status, cm.exception.code), ("stopped-on-input-error", code))
        self.assertEqual(cm.exception.details, {"input": "api-spec"})

    def test_valid(self):
        self.assertEqual(openapi.load_spec(self.write(SPEC))["openapi"], "3.0.3")
        openapi.load_spec(self.write({"openapi": "3.1.0", "paths": {}}))

    def test_invalid(self):
        self.assert_invalid("{not json")
        self.assert_invalid([])
        self.assert_invalid({"swagger": "2.0", "paths": {}})
        self.assert_invalid({"openapi": 3.0, "paths": {}})
        self.assert_invalid({"openapi": "2.0", "paths": {}})
        self.assert_invalid({"openapi": "3.0.0"})
        self.assert_invalid({"openapi": "3.0.0", "paths": []})

    def test_missing_file(self):
        with self.assertRaises(state.StopRun) as cm:
            openapi.load_spec(os.path.join(self.tmp.name, "none.json"))
        self.assertEqual(cm.exception.code, "missing-input")


class OperationsTest(unittest.TestCase):
    def test_operations_ignore_non_method_keys(self):
        self.assertEqual(openapi.operations(SPEC), {
            ("GET", "/items"), ("POST", "/items"), ("GET", "/items/{id}"),
            ("DELETE", "/items/{id}"), ("GET", "/items/me"), ("GET", "/files/{name}.{ext}"),
            ("GET", "/"),
        })


class MatchTest(unittest.TestCase):
    def test_literal_and_param_segments(self):
        self.assertEqual(openapi.match(SPEC, "get", "/items"), ("GET", "/items"))
        self.assertEqual(openapi.match(SPEC, "GET", "/items/42"), ("GET", "/items/{id}"))
        self.assertEqual(openapi.match(SPEC, "DELETE", "/items/42"), ("DELETE", "/items/{id}"))
        self.assertEqual(openapi.match(SPEC, "GET", "/files/a.txt"), ("GET", "/files/{name}.{ext}"))

    def test_fewest_params_wins(self):
        self.assertEqual(openapi.match(SPEC, "GET", "/items/me"), ("GET", "/items/me"))

    def test_no_match(self):
        self.assertIsNone(openapi.match(SPEC, "PUT", "/items/1"))
        self.assertIsNone(openapi.match(SPEC, "GET", "/items/1/extra"))
        self.assertIsNone(openapi.match(SPEC, "GET", "/other"))

    def test_query_fragment_and_trailing_slash(self):
        self.assertEqual(openapi.match(SPEC, "GET", "/items?page=2#top"), ("GET", "/items"))
        self.assertEqual(openapi.match(SPEC, "GET", "/items/"), ("GET", "/items"))
        self.assertEqual(openapi.match(SPEC, "GET", "/"), ("GET", "/"))

    def test_base_url_is_stripped(self):
        self.assertEqual(openapi.match(SPEC, "GET", "http://127.0.0.1:8000/items/7?x=1",
                                       base_url="http://127.0.0.1:8000"), ("GET", "/items/{id}"))
        self.assertEqual(openapi.match(SPEC, "GET", "http://h/api/items",
                                       base_url="http://h/api/"), ("GET", "/items"))
        self.assertEqual(openapi.match(SPEC, "GET", "/api/items", base_url="http://h/api"),
                         ("GET", "/items"))
        self.assertEqual(openapi.match(SPEC, "GET", "http://h/items"), ("GET", "/items"))


if __name__ == "__main__":
    unittest.main()
