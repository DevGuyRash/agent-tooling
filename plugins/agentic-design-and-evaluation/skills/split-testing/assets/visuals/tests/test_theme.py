"""Theme generation and bounded preference contracts; no browser is rendered."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ThemeTests(unittest.TestCase):
    def test_surface_clipping_survives_background_shorthand(self):
        source = (ROOT / "styles/components.css").read_text()
        checked = []
        for selector, body in re.findall(r"([^{}]+)\{([^{}]+)\}", source):
            if not any(target in selector for target in ['.av-card > .av-card-header', '.av-data > summary', '.av-data[open] > summary', '.av-plot-scroll ', '.av-button', '.av-object-detail']):
                continue
            declarations = [tuple(part.strip() for part in declaration.split(':', 1)) for declaration in body.split(';') if ':' in declaration]
            if not any(name == 'background' for name, value in declarations):
                continue
            # CSS background resets background-clip even when its value omits a box.
            clip = 'border-box'
            for name, value in declarations:
                if name == 'background':
                    clip = 'padding-box' if 'padding-box' in value else 'border-box'
                elif name == 'background-clip':
                    clip = value
            self.assertEqual(clip, 'padding-box', selector.strip())
            checked.append(selector)
        self.assertTrue(checked)

    def test_row_axes_preserve_the_data_viewport_and_source_print_scale(self):
        components = (ROOT / "styles/components.css").read_text()
        screen, printing = components.split("@media print {", 1)
        # Enhanced row identities share the measured fitted allocation; they do not own a horizontal scrollbar.
        natural = re.search(r"(?m)^\.av-row-plot-layout \{([^}]+)\}", screen).group(1)
        enhanced = re.search(r"(?m)^\.av-enhanced \.av-row-plot-layout \{([^}]+)\}", screen).group(1)
        self.assertIn("var(--av-axis-row-width, 185px) max-content", natural)
        self.assertIn("var(--av-axis-row-width, 185px) minmax(0, 1fr)", enhanced)
        self.assertNotIn("35%", enhanced)
        height_rule = next(line for line in screen.splitlines() if ".av-axis-rows-viewport" in line and "max-height:" in line)
        self.assertIn(".av-plot-scroll", height_rule)
        self.assertIn("height: var(--av-plot-fit-height, auto)", height_rule)
        scroll_rule = next(line for line in screen.splitlines() if line.startswith(".av-enhanced .av-row-plot .av-axis-rows-viewport") and "overflow:" in line)
        self.assertIn("overflow: hidden", scroll_rule)
        self.assertIn("min-height: var(--av-axis-x-height, 0px)", screen)
        self.assertNotIn("--av-plot-max-height", screen)
        self.assertIn(".av-plot-scroll::-webkit-scrollbar { display: none; }", screen)
        print_scale = next(line for line in printing.splitlines() if "svg[data-av-axis-layer]" in line)
        self.assertIn(".av-row-plot .av-plot-scroll svg", print_scale)
        for reset in ("width: auto !important", "height: auto !important", "transform: none !important"):
            self.assertIn(reset, print_scale)
        self.assertIn("grid-template-columns: max-content max-content !important", printing)
        self.assertIn(":has(> :is(.av-plot-shell, .av-scatter-scenes)):has(> .av-inspector)", screen)

    def test_builder_uses_only_the_trusted_self_contained_theme(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required")
        self.assertIsNotNone(tsc, "TypeScript is required")
        with tempfile.TemporaryDirectory(prefix="av-theme-build-") as tmp:
            fixture = Path(tmp)
            (fixture / "src").mkdir()
            (fixture / "styles").mkdir()
            (fixture / "src/theme.ts").write_text((ROOT / "src/theme.ts").read_text())
            (fixture / "styles/components.css").write_text("/* fixture components */\n")
            (fixture / "src/index.ts").write_text("throw new Error('Caller browser code must never execute');\n")
            code = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const {generateThemeStyles} = await import(pathToFileURL(process.argv[1]));
const ts = createRequire(process.argv[2])('typescript');
const css = generateThemeStyles(ts, process.argv[3]);
assert(css.endsWith('/* fixture components */\n'));
assert(css.includes('[data-av-canvas="textured"]'));
fs.writeFileSync(process.argv[3]+'/src/theme.ts', 'import "./index"; export function themeCss(){return "body{}";}');
assert.throws(() => generateThemeStyles(ts,process.argv[3]), /imports are not allowed/);
console.log('Pure theme builder isolation passed');
'''
            result = subprocess.run([node, "--input-type=module", "-e", code, str(ROOT / "build-theme.mjs"), str(Path(tsc).resolve()), tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_roles_and_preference_ownership(self):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        self.assertIsNotNone(node, "Node.js is required")
        self.assertIsNotNone(tsc, "TypeScript is required")
        with tempfile.TemporaryDirectory(prefix="av-theme-") as tmp:
            result = subprocess.run([tsc, "--strict", "--target", "ES2020", "--module", "commonjs", "--rootDir", str(ROOT / "src"), "--outDir", tmp, str(ROOT / "src/preferences.ts")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([node, str(ROOT / "tests/theme.cjs"), tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_canvas_and_component_roles_have_one_owner(self):
        components = (ROOT / "styles/components.css").read_text()
        generated = (ROOT / "styles/agentic-visuals.css").read_text()
        self.assertTrue(generated.endswith(components))
        self.assertIn("Generated theme definitions from src/theme.ts", generated)
        self.assertNotIn("--av-brand-main:", components)
        self.assertNotIn("background: var(--av-paper)", components)
        self.assertIn("background-image: var(--av-canvas-image)", generated)
        self.assertIn('[data-av-canvas="textured"]', generated)
        self.assertIn('[data-av-texture="grid"]', generated)
        self.assertIn('[data-av-intensity="moderate"]', generated)
        for role in ("heading", "subheading", "header-surface", "tool-surface", "tool-ink", "inspector-surface", "inspector-ink", "node-surface"):
            self.assertIn("var(--av-" + role + ")", components)
        self.assertIn("--av-plot-fit-height", components)
        self.assertIn("var(--av-scroll-thumb", components)


if __name__ == "__main__":
    unittest.main()
