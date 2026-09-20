"""Evaluate declared sRGB text pairs; these checks do not render a browser."""
from pathlib import Path
import re
import unittest

CSS = Path(__file__).resolve().parents[1] / 'styles/agentic-visuals.css'


def arguments(value):
    result, depth, start = [], 0, 0
    for index, character in enumerate(value):
        if character == '(': depth += 1
        elif character == ')': depth -= 1
        elif character == ',' and depth == 0:
            result.append(value[start:index].strip()); start = index + 1
    return [*result, value[start:].strip()]


def color(value, tokens, mode):
    value = value.strip()
    if re.fullmatch(r'#[0-9a-fA-F]{6}', value): return [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    if value.startswith('var('):
        parts = arguments(value[4:-1]); return color(tokens.get(parts[0], parts[1] if len(parts) > 1 else ''), tokens, mode)
    if value.startswith('light-dark('): return color(arguments(value[11:-1])[mode], tokens, mode)
    if value.startswith('color-mix('):
        space, first, second = arguments(value[10:-1]); assert space == 'in srgb'
        match = re.fullmatch(r'(.*) (\d+(?:\.\d+)?)%', first); assert match, first
        ratio = float(match[2]) / 100
        return [a * ratio + b * (1 - ratio) for a, b in zip(color(match[1], tokens, mode), color(second, tokens, mode))]
    raise AssertionError('Unsupported color expression: ' + value)


def luminance(channels):
    channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(channels, (.2126, .7152, .0722)))


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + .05) / (low + .05)


class PresentationColorTests(unittest.TestCase):
    def test_generated_preset_text_against_the_actual_role_surfaces(self):
        css = CSS.read_text()
        tokens = dict(re.findall(r'^  (--av-[\w-]+): ([^;]+);', css[:css.index('[data-av-theme=')], re.M))
        presets = {name: dict(re.findall(r'(--av-[\w-]+): ([^;]+);', body)) for name, body in re.findall(r'\[data-av-palette="([a-z]+)"\] \{([^}]+)\}', css)}
        self.assertEqual(set(presets), {'indigo', 'ocean', 'graphite', 'aurora', 'citrus', 'rose'})
        # Custom colors run through the same pure generator in theme.cjs. Substituting
        # only raw brand variables here would not evaluate their generated tones.
        for palette, definitions in presets.items():
            values = {**tokens, **definitions}
            for mode in (0, 1):
                cases = [(text, paper) for text in ('ink', 'muted', 'accent', 'secondary', 'tertiary', 'heading', 'subheading', 'tool-ink', 'inspector-ink') for paper in ('paper', 'sheet', 'white', 'subtle', 'header-surface', 'tool-surface', 'inspector-surface', 'node-surface')]
                cases += [(text, 'sheet') for text in ('sage', 'brass', 'failure')]
                cases += [(text, text + '-pale') for text in ('sage', 'brass', 'failure', 'uncertain', 'accent')]
                cases += [('heat-ink', background) for background in ('heat-low', 'heat-high')]
                for foreground, background in cases:
                    with self.subTest(palette=palette, mode=('light', 'dark')[mode], foreground=foreground, background=background):
                        self.assertGreaterEqual(contrast(color('var(--av-' + foreground + ')', values, mode), color('var(--av-' + background + ')', values, mode)), 4.5)
