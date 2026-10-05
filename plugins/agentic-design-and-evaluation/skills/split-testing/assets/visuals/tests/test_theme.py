"""Theme tokens in the shipped stylesheet: both themes define the same colors,
body text meets WCAG contrast in both, and check shading keeps measures neutral."""
from __future__ import annotations

import re
import unittest

from visual_harness import VISUALS

STYLESHEET = VISUALS / "styles" / "agentic-visuals.css"
COMPONENTS = VISUALS / "styles" / "components.css"
# Tokens that do not change with the theme; only :root defines them.
THEME_INDEPENDENT = {"font-display", "font-text", "font-mono", "radius", "radius-sm", "measure", "page", "gutter"}
# (theme, foreground, background): minimum contrast ratio.
REQUIRED_CONTRAST = {
    **{(theme, "ink", ground): 7.0 for theme in ("light", "dark") for ground in ("bg", "surface", "raised")},
    **{(theme, "ink-3", ground): 4.5 for theme in ("light", "dark") for ground in ("bg", "surface", "raised")},
    **{(theme, "ink-2", ground): 4.5 for theme in ("light", "dark") for ground in ("bg", "surface", "raised")},
}
# Known library defects: pairs below their minimum. Each is skipped while it
# reproduces and fails once fixed, so it is removed from this set.
KNOWN_CONTRAST_DEFECTS: set = set()


def declarations(css: str, opener: str) -> dict[str, str]:
    start = css.index(opener) + len(opener)
    return dict(re.findall(r"--av-([\w-]+):([^;]+);", css[start:css.index("}", start)]))


def rule(css: str, selector: str) -> str:
    match = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css, re.M)
    if not match:
        raise AssertionError(f"no {selector} rule")
    return match.group(1)


def luminance(color: str) -> float:
    value = color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise AssertionError(f"not an opaque hex color: {color}")
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ThemeTokensTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.css = STYLESHEET.read_text(encoding="utf-8")
        cls.light = declarations(cls.css, ":root{")
        cls.dark = declarations(cls.css, ':root[data-theme="dark"]{')
        cls.system_dark = declarations(cls.css, '@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){')

    def test_light_and_dark_define_the_same_tokens(self) -> None:
        self.assertGreater(len(self.dark), 30)
        self.assertEqual(set(self.light) - THEME_INDEPENDENT, set(self.dark))
        self.assertFalse(THEME_INDEPENDENT & set(self.dark), "a theme-independent token is redefined by the dark theme")

    def test_system_dark_matches_the_explicit_dark_theme(self) -> None:
        self.assertEqual(self.system_dark, self.dark)

    def test_eight_arm_identities_per_theme(self) -> None:
        for name, palette in (("light", self.light), ("dark", self.dark)):
            with self.subTest(theme=name):
                arms = sorted(k for k in palette if k.startswith("arm-"))
                self.assertEqual(arms, [f"arm-{i}" for i in range(8)])
                self.assertEqual(len({palette[a].lower() for a in arms}), 8, "arm colors repeat")

    def test_every_referenced_token_is_defined(self) -> None:
        defined = set(re.findall(r"(--av-[\w-]+)\s*:", self.css))
        used = set(re.findall(r"var\((--av-[\w-]+)", self.css))
        self.assertGreater(len(used), 10)
        self.assertEqual(used - defined, set())

    def test_text_contrast_meets_wcag(self) -> None:
        palettes = {"light": self.light, "dark": self.dark}
        for (theme, fg, ground), minimum in sorted(REQUIRED_CONTRAST.items()):
            with self.subTest(theme=theme, text=fg, ground=ground):
                ratio = contrast(palettes[theme][fg], palettes[theme][ground])
                known = (theme, fg, ground) in KNOWN_CONTRAST_DEFECTS
                if known and ratio < minimum:
                    self.skipTest(f"known library defect: {theme} --av-{fg} on --av-{ground} is {ratio:.2f}:1, below {minimum}:1")
                if known:
                    self.fail(f"{theme} --av-{fg} on --av-{ground} now meets {minimum}:1; remove it from KNOWN_CONTRAST_DEFECTS")
                self.assertGreaterEqual(ratio, minimum, f"{theme} --av-{fg} on --av-{ground} is {ratio:.2f}:1")


class CheckShadingStyleTest(unittest.TestCase):
    """Required checks shade between pass and fail; measures shade neutrally."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.css = COMPONENTS.read_text(encoding="utf-8")

    def test_required_check_cells_shade_between_pass_and_fail(self) -> None:
        body = rule(self.css, ".av-heat")
        self.assertIn("--av-pass", body)
        self.assertIn("--av-fail", body)

    def test_measure_cells_shade_without_pass_or_fail_colors(self) -> None:
        for selector in (".av-heat--measure", ".av-heat--measure .av-heat-bar span"):
            with self.subTest(selector=selector):
                body = rule(self.css, selector)
                self.assertNotRegex(body, r"--av-(pass|fail)")
                self.assertIn("--av-accent", body)


if __name__ == "__main__":
    unittest.main()
