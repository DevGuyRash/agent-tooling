"""Browser-behavior pieces that need no browser: CSV export and the run
drawer's markup, checked against the built bundle in node:vm (enhance.cjs),
and the contrast of status words in the shared stylesheet."""
from __future__ import annotations

import re
import unittest

from visual_harness import VISUALS, NodeCases

STYLESHEET = VISUALS / "styles" / "agentic-visuals.css"


class EnhanceTest(NodeCases):
    """CSV quoting and formula guards, and the drawer's cause, order and escaping."""

    script = "enhance.cjs"
    minimum = 10

    def test_export_and_drawer(self) -> None:
        self.run_script_cases()


def _tokens(css: str, opener: str) -> dict[str, str]:
    start = css.index(opener) + len(opener)
    return dict(re.findall(r"--av-([\w-]+):([^;]+);", css[start:css.index("}", start)]))


def _rgb(color: str) -> tuple[float, float, float]:
    value = color.strip().lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _contrast(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    def lum(c: tuple[float, ...]) -> float:
        lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    high, low = sorted((lum(a), lum(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class StatusTextContrastTest(unittest.TestCase):
    """Status words (Passed, Failed, warnings) on their soft fills keep WCAG AA
    contrast in both themes: components.css deepens each status hue toward the
    ink with color-mix, and this recomputes that mix from the theme tokens."""

    def test_status_text_meets_4_5_to_1_on_its_fill_and_on_raised(self) -> None:
        css = STYLESHEET.read_text(encoding="utf-8")
        mixes = dict(re.findall(r"--st-(pass|fail|warn):\s*color-mix\(in srgb, var\(--av-\1\) (\d+)%, var\(--av-ink\)\)", css))
        self.assertEqual(set(mixes), {"pass", "fail", "warn"}, "the status text colors are not defined as mixes of theme tokens")
        themes = {"light": _tokens(css, ":root{"), "dark": _tokens(css, ':root[data-theme="dark"]{')}
        for theme, palette in themes.items():
            for status, share in mixes.items():
                p = int(share) / 100
                hue, ink = _rgb(palette[status]), _rgb(palette["ink"])
                text = tuple(h * p + k * (1 - p) for h, k in zip(hue, ink))
                for ground in (f"{status}-soft", "raised", "surface"):
                    with self.subTest(theme=theme, status=status, ground=ground):
                        ratio = _contrast(text, _rgb(palette[ground]))
                        self.assertGreaterEqual(ratio, 4.5, f"{theme} {status} text on --av-{ground} is {ratio:.2f}:1")

    def test_badges_and_judge_chips_use_the_status_text_colors(self) -> None:
        css = (VISUALS / "styles" / "components.css").read_text(encoding="utf-8")
        for selector, token in ((".av-badge--pass", "--st-pass"), (".av-badge--fail", "--st-fail"), (".av-chip--warn", "--st-warn")):
            with self.subTest(selector=selector):
                rule = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
                self.assertIsNotNone(rule, f"no {selector} rule")
                self.assertIn(f"color: var({token})", rule.group(1))


if __name__ == "__main__":
    unittest.main()
