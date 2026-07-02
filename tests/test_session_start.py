"""Golden tests for the SessionStart banner (scripts/session_start.sh).

The banner is a static signal, so the tests pin it exactly: valid JSON, a
systemMessage and nothing else (no additionalContext -- the banner must never
leak into the model context), armed wording when .compliance.yml is present in
the working directory, and the wrong-directory wording when it is not.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "session_start.sh")
BASH = shutil.which("bash")


def run_banner(cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, SCRIPT], cwd=cwd, capture_output=True, text=True, timeout=15
    )


@unittest.skipIf(BASH is None, "bash not available")
class TestSessionBanner(unittest.TestCase):
    def test_armed_banner_when_scope_file_present(self):
        result = run_banner(REPO_ROOT)  # repo root has .compliance.yml
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(sorted(payload.keys()), ["systemMessage"])
        self.assertIn("armed", payload["systemMessage"])
        self.assertIn(".compliance.yml", payload["systemMessage"])

    def test_unarmed_banner_when_scope_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_banner(tmp)
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(sorted(payload.keys()), ["systemMessage"])
            self.assertIn("no .compliance.yml", payload["systemMessage"])
            self.assertIn("stay silent", payload["systemMessage"])

    def test_never_blocks_the_session(self):
        # Both branches must exit 0: a banner is never allowed to break startup.
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_banner(tmp).returncode, 0)
        self.assertEqual(run_banner(REPO_ROOT).returncode, 0)


if __name__ == "__main__":
    unittest.main()
