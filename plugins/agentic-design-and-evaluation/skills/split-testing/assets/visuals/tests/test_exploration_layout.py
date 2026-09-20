"""Evaluate the declared flex sizing; native CSS layout remains a separate check."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def css_length(expression, variables, width, rem):
    expression = re.sub(r"var\((--[\w-]+)\)", lambda match: variables[match[1]], expression)
    expression = re.sub(r"(\d+(?:\.\d+)?)(rem|px|%)", lambda match: str(float(match[1]) * {"rem": rem, "px": 1, "%": width / 100}[match[2]]), expression)

    def value(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            args = [value(arg) for arg in node.args]
            if node.func.id == "min":
                return min(args)
            if node.func.id == "max":
                return max(args)
            if node.func.id == "calc" and len(args) == 1:
                return args[0]
        if isinstance(node, ast.BinOp):
            left, right = value(node.left), value(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
        raise AssertionError(f"Unsupported length expression: {ast.dump(node)}")

    return value(ast.parse(expression, mode="eval").body)


class ExplorationLayoutTests(unittest.TestCase):
    def test_inspector_wrapping_preserves_canvas_width_across_the_transition(self):
        css = (ROOT / "styles/components.css").read_text()
        rules = dict(re.findall(r"([^{}]+)\{([^{}]+)\}", css))
        layout = next(body for selector, body in rules.items()
                      if "--av-exploration-canvas:" in body)
        variables = dict(re.findall(r"(--av-exploration-[\w-]+):\s*([^;]+);", layout))
        self.assertIn("flex-wrap: wrap", layout)
        plot = next(body for selector, body in rules.items()
                    if selector.strip() == ".av-explorer:has(> .av-inspector) > :is(.av-plot-shell, .av-scatter-scenes)")
        # Shrink/grow are zero: the authored expression determines the canvas.
        expression = re.search(r"flex:\s*0\s+0\s+(.+?);", plot).group(1)
        for rem in (12, 16, 24):
            floor = css_length(variables["--av-exploration-canvas"], variables, 0, rem)
            inspector = css_length(variables["--av-exploration-inspector"], variables, 0, rem)
            gap = css_length(variables["--av-exploration-gap"], variables, 0, rem)
            transition = floor + inspector + gap
            widths = sorted(set([x * rem / 4 for x in range(1, 801)] +
                                [transition - .01, transition, transition + .01]))
            previous_width = previous_canvas = 0
            for width in widths:
                canvas = css_length(expression, variables, width, rem)
                self.assertGreater(canvas, 0)
                self.assertLessEqual(canvas, width + 1e-8)
                self.assertGreaterEqual(canvas + 1e-8, previous_canvas,
                                        f"Canvas shrank at explorer width {width}")
                self.assertLessEqual(canvas - previous_canvas, width - previous_width + 1e-8)
                if width <= floor:
                    self.assertAlmostEqual(canvas, width)
                if canvas + inspector + gap <= width:
                    self.assertGreaterEqual(canvas, floor)
                    self.assertAlmostEqual(canvas + inspector + gap, width)
                previous_width, previous_canvas = width, canvas
            before = css_length(expression, variables, transition - .01, rem)
            after = css_length(expression, variables, transition + .01, rem)
            self.assertLessEqual(after - before, .02 + 1e-8)


if __name__ == "__main__":
    unittest.main()
