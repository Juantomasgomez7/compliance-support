import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import review_gate as rg  # noqa: E402


class ChangedPathsTests(unittest.TestCase):
    def test_parses_modified_path(self):
        self.assertEqual(
            rg.changed_paths(" M examples/refunds-service/src/api/handlers/refund.py\n"),
            ["examples/refunds-service/src/api/handlers/refund.py"])

    def test_parses_untracked_path(self):
        self.assertEqual(rg.changed_paths("?? scripts/dev_seed.py\n"), ["scripts/dev_seed.py"])

    def test_rename_takes_the_new_path(self):
        self.assertEqual(rg.changed_paths("R  src/old.py -> src/new.py\n"), ["src/new.py"])

    def test_ignores_blank_lines(self):
        self.assertEqual(rg.changed_paths("\n   \n"), [])

    def test_multiple_lines_in_order(self):
        self.assertEqual(rg.changed_paths(" M a.py\n?? b.py\nMM c.py\n"), ["a.py", "b.py", "c.py"])


class InScopePathsTests(unittest.TestCase):
    INCLUDE = ["examples/refunds-service/src/**"]
    EXCLUDE = ["**/scripts/**"]

    def test_keeps_in_scope_path(self):
        p = "examples/refunds-service/src/api/handlers/refund.py"
        self.assertEqual(rg.in_scope_paths([p], self.INCLUDE, self.EXCLUDE), [p])

    def test_drops_out_of_scope_path(self):
        self.assertEqual(rg.in_scope_paths(["README.md"], self.INCLUDE, self.EXCLUDE), [])

    def test_drops_excluded_path_even_if_included(self):
        p = "examples/refunds-service/src/scripts/seed.py"  # under src/** but also **/scripts/**
        self.assertEqual(rg.in_scope_paths([p], self.INCLUDE, self.EXCLUDE), [])

    def test_filters_a_mixed_list(self):
        paths = ["README.md",
                 "examples/refunds-service/src/api/handlers/refund.py",
                 "scripts/dev_seed.py"]
        self.assertEqual(rg.in_scope_paths(paths, self.INCLUDE, self.EXCLUDE),
                         ["examples/refunds-service/src/api/handlers/refund.py"])


class ChangesetIdTests(unittest.TestCase):
    def test_is_order_independent(self):
        self.assertEqual(rg.changeset_id(["a.py", "b.py"]), rg.changeset_id(["b.py", "a.py"]))

    def test_ignores_duplicates(self):
        self.assertEqual(rg.changeset_id(["a.py", "a.py"]), rg.changeset_id(["a.py"]))

    def test_different_sets_differ(self):
        self.assertNotEqual(rg.changeset_id(["a.py"]), rg.changeset_id(["a.py", "b.py"]))


class SentinelTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "last-changeset")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_unseen_changeset_is_not_reviewed(self):
        self.assertFalse(rg.already_reviewed(self.path, "abc"))

    def test_recorded_changeset_is_reviewed(self):
        rg.record_reviewed(self.path, "abc")
        self.assertTrue(rg.already_reviewed(self.path, "abc"))

    def test_a_different_changeset_is_not_reviewed(self):
        rg.record_reviewed(self.path, "abc")
        self.assertFalse(rg.already_reviewed(self.path, "def"))

    def test_recording_into_a_missing_dir_does_not_raise(self):
        missing = os.path.join(self.dir, "nope", "last")
        rg.record_reviewed(missing, "abc")            # best-effort, must not raise
        self.assertFalse(rg.already_reviewed(missing, "abc"))


class BuildReasonTests(unittest.TestCase):
    def test_lists_each_changed_file(self):
        r = rg.build_reason(["a.py", "b.py"])
        self.assertIn("a.py", r)
        self.assertIn("b.py", r)

    def test_names_the_review_agent(self):
        self.assertIn("compliance-review", rg.build_reason(["a.py"]))

    def test_cites_both_judgment_controls(self):
        r = rg.build_reason(["a.py"])
        self.assertIn("CTRL-3", r)
        self.assertIn("CTRL-4", r)


class DecideTests(unittest.TestCase):
    INCLUDE = ["examples/refunds-service/src/**"]
    EXCLUDE = ["**/scripts/**"]
    IN = " M examples/refunds-service/src/api/handlers/refund.py\n"
    OUT = " M README.md\n"

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.sent = os.path.join(self.dir, "last-changeset")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_continuation_stop_is_skipped_even_with_changes(self):
        d = rg.decide({"stop_hook_active": True}, self.IN, self.INCLUDE, self.EXCLUDE, self.sent)
        self.assertIsNone(d)

    def test_no_in_scope_change_is_skipped(self):
        self.assertIsNone(rg.decide({}, self.OUT, self.INCLUDE, self.EXCLUDE, self.sent))

    def test_fresh_in_scope_change_blocks_and_names_the_file(self):
        d = rg.decide({}, self.IN, self.INCLUDE, self.EXCLUDE, self.sent)
        self.assertEqual(d["decision"], "block")
        self.assertIn("refund.py", d["reason"])

    def test_same_change_set_only_nudges_once(self):
        first = rg.decide({}, self.IN, self.INCLUDE, self.EXCLUDE, self.sent)
        second = rg.decide({}, self.IN, self.INCLUDE, self.EXCLUDE, self.sent)
        self.assertIsNotNone(first)
        self.assertIsNone(second)


class MainEndToEndTests(unittest.TestCase):
    """Drives review_gate.py as the hook does: a Stop payload on stdin, run in a
    real (temporary) git repo, output read from stdout."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        with open(os.path.join(self.repo, ".compliance.yml"), "w", encoding="utf-8") as f:
            f.write('scope:\n  include:\n    - "src/**"\n  exclude:\n    - "**/scripts/**"\n')
        os.makedirs(os.path.join(self.repo, "src"))
        with open(os.path.join(self.repo, "src", "refund.py"), "w", encoding="utf-8") as f:
            f.write("amount = 1\n")  # untracked -> an in-scope change

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _run(self, payload):
        script = os.path.join(os.path.dirname(__file__), "..", "scripts", "review_gate.py")
        return subprocess.run([sys.executable, script], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=self.repo)

    def test_blocks_on_in_scope_change_and_names_the_file(self):
        out = self._run({"cwd": self.repo, "hook_event_name": "Stop", "stop_hook_active": False})
        self.assertIn('"decision": "block"', out.stdout)
        self.assertIn("refund.py", out.stdout)

    def test_silent_on_continuation_stop(self):
        out = self._run({"cwd": self.repo, "stop_hook_active": True})
        self.assertEqual(out.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
