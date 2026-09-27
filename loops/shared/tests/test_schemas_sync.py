"""The schemas the driver uses must stay byte-identical to the contracts (constitution IX)."""
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CONTRACTS_DIR = os.path.join(REPO_ROOT, "specs", "001-reusable-dev-loops", "contracts")
SCHEMAS_DIR = os.path.join(REPO_ROOT, "loops", "shared", "schemas")

SCHEMA_NAMES = [
    "config",
    "plan",
    "checks",
    "validation-result",
    "invocation-record",
    "run-state",
]


def _schema_files(directory):
    return sorted(n for n in os.listdir(directory) if n.endswith(".schema.json"))


@unittest.skipUnless(os.path.isdir(CONTRACTS_DIR), "contracts directory not present")
class SchemasSyncTest(unittest.TestCase):
    def test_each_schema_is_byte_identical_to_its_contract(self):
        for name in SCHEMA_NAMES:
            filename = name + ".schema.json"
            with self.subTest(schema=filename):
                with open(os.path.join(CONTRACTS_DIR, filename), "rb") as f:
                    contract = f.read()
                with open(os.path.join(SCHEMAS_DIR, filename), "rb") as f:
                    copy = f.read()
                self.assertEqual(contract, copy, f"{filename} differs from its contract")

    def test_no_schema_is_missing_or_extra(self):
        expected = sorted(n + ".schema.json" for n in SCHEMA_NAMES)
        self.assertEqual(_schema_files(CONTRACTS_DIR), expected)
        self.assertEqual(_schema_files(SCHEMAS_DIR), expected)


if __name__ == "__main__":
    unittest.main()
