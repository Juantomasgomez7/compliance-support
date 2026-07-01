import json, os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import scan  # noqa: E402
PATTERNS_JSON = os.path.join(ROOT, "skills", "control-library", "patterns.json")


class PatternsSourcedFromControlLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PATTERNS_JSON, encoding="utf-8") as fh:
            cls.data = json.load(fh)

    def test_file_lives_in_appsec_control_library(self):
        self.assertTrue(os.path.isfile(PATTERNS_JSON))

    def test_three_groups_with_full_metadata(self):
        for group in ("secret", "weak_crypto", "tls_off"):
            g = self.data[group]
            for key in ("control", "maps_to", "what", "fix", "patterns"):
                self.assertIn(key, g)
            self.assertTrue(g["patterns"])

    def test_scan_compiles_exactly_the_library_patterns(self):
        self.assertEqual([p.pattern for p in scan.SECRET_PATTERNS], self.data["secret"]["patterns"])
        self.assertEqual([p.pattern for p in scan.WEAK_CRYPTO_PATTERNS], self.data["weak_crypto"]["patterns"])
        self.assertEqual([p.pattern for p in scan.TLS_OFF_PATTERNS], self.data["tls_off"]["patterns"])

    def test_control_ids_match_the_library(self):
        self.assertEqual(self.data["secret"]["control"], "CTRL-1")
        self.assertEqual(self.data["weak_crypto"]["control"], "CTRL-2")
        self.assertEqual(self.data["tls_off"]["control"], "CTRL-2")


if __name__ == "__main__":
    unittest.main()
