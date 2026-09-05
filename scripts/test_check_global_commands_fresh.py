#!/usr/bin/env python3
"""Fixture tests for scripts/check_global_commands_fresh.py.

Registered in planning/harness.json as `global-commands-fresh-tests` (gates: true — this suite
is dependency-free and touches only tempfile trees, so it is safe to gate even though the
checker it tests is itself non-gating; the checker watches per-machine install state, this
suite watches the checker's own logic).

Every case below builds its own throwaway source dir AND install dir under tempfile.mkdtemp().
Nothing here reads or writes the real .claude/commands/ or the real ~/.claude/commands/, and
no test references Path.home().

Case D is a RUNTIME INVERSION rather than a frozen red baseline (per D68's evidence
requirement, satisfied the way /generate-tasks' own pitfall 6 recommends): it starts from an
in-sync pair, asserts the brain/ exclusion holds, then BREAKS the top-level tree by deleting a
file, observes the checker go red naming exactly that file, then restores it and observes green
again. That proves the exclusion and the drift detection both actually work, every run, rather
than relying on a commit that once was red.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts" / "check_global_commands_fresh.py"


def run_checker(source_dir, install_dir, extra_args=None):
    args = [
        sys.executable,
        str(CHECKER),
        "--source-dir",
        str(source_dir),
        "--install-dir",
        str(install_dir),
        "--quiet",
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True, cwd=str(REPO))


class GlobalCommandsFreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.source = self.tmp / "source"
        self.install = self.tmp / "install"
        self.source.mkdir()
        self.install.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, root, relname, content):
        path = root / relname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_case_a_in_sync(self):
        self._write(self.source, "foo.md", "# Foo\n\nbody\n")
        self._write(self.install, "foo.md", "# Foo\n\nbody\n")
        result = run_checker(self.source, self.install)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_case_b_missing(self):
        self._write(self.source, "foo.md", "# Foo\n\nbody\n")
        self._write(self.source, "bar.md", "# Bar\n\nbody\n")
        self._write(self.install, "foo.md", "# Foo\n\nbody\n")
        # bar.md is absent from install.
        result = run_checker(self.source, self.install)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bar.md", result.stdout)

    def test_case_c_differs(self):
        self._write(self.source, "foo.md", "# Foo\n\nversion one\n")
        self._write(self.install, "foo.md", "# Foo\n\nversion TWO, different\n")
        result = run_checker(self.source, self.install)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("foo.md", result.stdout)

    def test_case_d_brain_ignored_runtime_inversion(self):
        # Start in sync, including a brain/ file present only in source.
        self._write(self.source, "foo.md", "# Foo\n\nbody\n")
        self._write(self.source, "bar.md", "# Bar\n\nbody\n")
        self._write(self.source, "brain/some-ref.md", "# Ref\n\nbrain-only content\n")
        self._write(self.install, "foo.md", "# Foo\n\nbody\n")
        self._write(self.install, "bar.md", "# Bar\n\nbody\n")

        # The exclusion holds: brain/some-ref.md being source-only must not trip drift.
        result = run_checker(self.source, self.install)
        self.assertEqual(
            result.returncode,
            0,
            "brain/ must be excluded from comparison, matching /sync-global-commands' "
            "own --exclude='brain/': " + result.stdout + result.stderr,
        )

        # Break the precondition: delete a real top-level file from the install.
        (self.install / "bar.md").unlink()
        broken = run_checker(self.source, self.install)
        self.assertNotEqual(broken.returncode, 0, "deleting a top-level file must go red")
        self.assertIn("bar.md", broken.stdout)
        self.assertNotIn("some-ref.md", broken.stdout)

        # Restore the precondition: green again.
        self._write(self.install, "bar.md", "# Bar\n\nbody\n")
        restored = run_checker(self.source, self.install)
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)

    def test_case_e_no_install(self):
        self._write(self.source, "foo.md", "# Foo\n\nbody\n")
        no_install = self.tmp / "definitely-does-not-exist"
        result = run_checker(self.source, no_install)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_case_f_extra(self):
        self._write(self.source, "foo.md", "# Foo\n\nbody\n")
        self._write(self.install, "foo.md", "# Foo\n\nbody\n")
        self._write(self.install, "extra.md", "# Extra\n\nnot in source\n")
        result = run_checker(self.source, self.install)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("extra.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
