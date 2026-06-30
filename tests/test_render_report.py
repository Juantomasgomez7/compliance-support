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


class LogoTests(unittest.TestCase):
    def test_embeds_as_data_uri_when_present(self):
        self.assertIn("data:image/png;base64,", rr.logo_tag())

    def test_falls_back_to_wordmark_when_missing(self):
        original = rr.LOGO_PATH
        rr.LOGO_PATH = "no/such/logo.png"
        try:
            tag = rr.logo_tag()
        finally:
            rr.LOGO_PATH = original
        self.assertIn("wordmark", tag)
        self.assertIn(rr.ORG_NAME, tag)


class RenderHtmlTests(unittest.TestCase):
    def test_all_four_controls_in_coverage(self):
        h = rr.render_html([], ["a.py"], [], 1)
        for cid in ("CTRL-1", "CTRL-2", "CTRL-3", "CTRL-4"):
            self.assertIn(cid, h)

    def test_all_clear_banner_when_no_findings(self):
        h = rr.render_html([], ["a.py"], [], 1)
        self.assertIn("All clear", h)
        self.assertIn("banner ok", h)

    def test_warn_banner_for_agent_findings(self):
        f = [{"file": "a.py", "control": "CTRL-1", "line": 3, "evidence": "x", "fix": "y"}]
        h = rr.render_html(f, [], [], 1)
        self.assertIn("banner warn", h)
        self.assertIn("Needs review", h)

    def test_bad_banner_and_block_card_for_confirmatory_finding(self):
        c = [{"file": "a.py", "control": "CTRL-3", "line": 1, "evidence": "k='sk_live_x'",
              "fix": "env"}]
        h = rr.render_html([], [], c, 1)
        self.assertIn("banner bad", h)
        self.assertIn("Auto-blocked", h)

    def test_glossary_and_title_present(self):
        h = rr.render_html([], [], [], 0)
        self.assertIn("How to read this report", h)
        self.assertIn("Data-Protection Compliance Review", h)

    def test_self_contained_no_external_http(self):
        h = rr.render_html([], ["a.py"], [], 1)
        self.assertNotIn("http://", h)
        self.assertNotIn("https://", h)


class MarkdownTests(unittest.TestCase):
    def test_markdown_has_no_branding_or_html(self):
        m = rr.render_markdown([], ["a.py"])
        self.assertNotIn("Capital One", m)
        self.assertNotIn("<", m)
        self.assertIn("Reviewed and clean", m)


if __name__ == "__main__":
    unittest.main()
