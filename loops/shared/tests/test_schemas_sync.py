"""The schemas the driver uses must stay byte-identical to the contracts (constitution IX)."""
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SPECS_DIR = os.path.join(REPO_ROOT, "specs")
SCHEMAS_DIR = os.path.join(REPO_ROOT, "loops", "shared", "schemas")

# Schema name -> the feature whose contracts/ directory owns it.
SCHEMA_NAMES = {
    "config": "001-reusable-dev-loops",
    "plan": "001-reusable-dev-loops",
    "checks": "001-reusable-dev-loops",
    "validation-result": "001-reusable-dev-loops",
    "invocation-record": "001-reusable-dev-loops",
    "run-state": "001-reusable-dev-loops",
    "project-config": "002-devloops-init",
    "manifest": "002-devloops-init",
}
CONTRACTS_DIRS = sorted({os.path.join(SPECS_DIR, feature, "contracts")
                         for feature in SCHEMA_NAMES.values()})


def _schema_files(directory):
    return sorted(n for n in os.listdir(directory) if n.endswith(".schema.json"))


@unittest.skipUnless(all(os.path.isdir(d) for d in CONTRACTS_DIRS),
                     "contracts directories not present")
class SchemasSyncTest(unittest.TestCase):
    def test_each_schema_is_byte_identical_to_its_contract(self):
        for name, feature in SCHEMA_NAMES.items():
            filename = name + ".schema.json"
            with self.subTest(schema=filename):
                with open(os.path.join(SPECS_DIR, feature, "contracts", filename), "rb") as f:
                    contract = f.read()
                with open(os.path.join(SCHEMAS_DIR, filename), "rb") as f:
                    copy = f.read()
                self.assertEqual(contract, copy, f"{filename} differs from its contract")

    def test_no_schema_is_missing_or_extra(self):
        expected = sorted(n + ".schema.json" for n in SCHEMA_NAMES)
        contracts = sorted(n for d in CONTRACTS_DIRS for n in _schema_files(d))
        self.assertEqual(contracts, expected)
        self.assertEqual(_schema_files(SCHEMAS_DIR), expected)


if __name__ == "__main__":
    unittest.main()
