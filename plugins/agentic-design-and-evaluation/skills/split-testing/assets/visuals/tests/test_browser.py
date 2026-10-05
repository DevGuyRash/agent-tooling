"""A real browser mounts report.py output. Skipped when neither
google-chrome-stable nor chromium is on PATH."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest

from visual_harness import EXAMPLES, REPORT, Scratch, run_python, write_hostile_fixtures

BROWSER = next((path for path in map(shutil.which, ("google-chrome-stable", "chromium", "chromium-browser")) if path), None)
SECTIONS = ["verdict", "arms", "cases", "checks", "pairwise", "cost", "invalid", "runs", "plan"]


@unittest.skipUnless(BROWSER, "google-chrome-stable or chromium is not on PATH")
class BrowserRenderTest(unittest.TestCase):
    """Headless rendering of an assembled report, read back with --dump-dom."""

    def setUp(self) -> None:
        self._scratch = Scratch()
        self.dir = self._scratch.__enter__()

    def tearDown(self) -> None:
        self._scratch.__exit__(None, None, None)

    def dump(self, *report_args: object, budget: int = 8000) -> str:
        page = self.dir / "report.html"
        built = run_python(REPORT, *report_args, "--output", page, "--replace")
        self.assertEqual(built.returncode, 0, built.stderr)
        command = [BROWSER, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                   f"--user-data-dir={self.dir / 'profile'}", f"--virtual-time-budget={budget}", "--dump-dom", page.as_uri()]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(1, "--no-sandbox")  # Chrome refuses to run its sandbox as root, as in some CI containers
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("the browser did not finish within 60 seconds")
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("</html>", result.stdout, "the browser printed no document")
        return result.stdout

    def test_trial_report_mounts_with_hostile_text_kept_as_text(self) -> None:
        fixtures = write_hostile_fixtures(self.dir / "fixtures")
        dom = self.dump("--trial", fixtures["trial"], "--narrative", fixtures["narrative"])
        self.assertIn("data-av-mounted", dom)
        self.assertRegex(dom, r'<div class="av-report" data-av-report="" data-av-ready="')
        ids = re.findall(r'<section class="av-section" id="([^"]+)"', dom)
        for section in SECTIONS:
            self.assertIn(section, ids)
        self.assertNotIn("could not render", dom)
        self.assertNotIn("<x-hostile", dom, "supplied text became an element in the browser")
        self.assertIn("&lt;x-hostile", dom, "the supplied text is not visible")

    def test_showcase_draws_its_diagram(self) -> None:
        dom = self.dump("--spec", EXAMPLES / "showcase-spec.json", budget=15000)
        self.assertRegex(dom, r'data-av-ready="')
        self.assertIn('data-av-mermaid-state="ready"', dom)
        self.assertIn("data-av-mermaid-scene", dom)
        self.assertNotIn("av-block-error", dom)


if __name__ == "__main__":
    unittest.main()
