import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import render_report as rr  # noqa: E402


class ScanContentTests(unittest.TestCase):
    def test_flags_provider_format_secret(self):
        hits = rr.scan_content('API = "sk_live_abcd1234efgh5678ij"\n')
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["control"], "CTRL-3")
        self.assertEqual(hits[0]["line"], 1)
        self.assertTrue(hits[0]["fix"])

    def test_flags_assigned_secret_literal_with_line_number(self):
        hits = rr.scan_content('\nPROCESSOR_API_KEY = "9c1f8e2a7b4d6051c3e9f0a2"\n')
        self.assertEqual([h["control"] for h in hits], ["CTRL-3"])
        self.assertEqual(hits[0]["line"], 2)

    def test_flags_weak_crypto_and_tls_off_as_ctrl4(self):
        self.assertEqual(rr.scan_content("hashlib.md5(x)")[0]["control"], "CTRL-4")
        self.assertEqual(rr.scan_content("requests.post(u, verify=False)")[0]["control"], "CTRL-4")

    def test_env_read_and_clean_logging_not_flagged(self):
        clean = 'KEY = os.environ["PROCESSOR_API_KEY"]\nlog.info("ok %s", account_id)\n'
        self.assertEqual(rr.scan_content(clean), [])


class ConfirmatoryFindingsTests(unittest.TestCase):
    def test_missing_file_is_skipped_not_crashed(self):
        findings, scanned = rr.confirmatory_findings(["does/not/exist.py"])
        self.assertEqual(findings, [])
        self.assertEqual(scanned, 0)

    def test_reads_file_and_attaches_path(self):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as t:
            t.write('PROCESSOR_API_KEY = "9c1f8e2a7b4d6051c3e9f0a2"\n')
            name = t.name
        try:
            findings, scanned = rr.confirmatory_findings([name])
            self.assertEqual(scanned, 1)
            self.assertEqual(findings[0]["control"], "CTRL-3")
            self.assertEqual(findings[0]["file"], name)
        finally:
            os.unlink(name)


if __name__ == "__main__":
    unittest.main()
