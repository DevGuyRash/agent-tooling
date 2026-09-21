"""Exercise actual build/export interfaces without shipping a fixture renderer."""

from __future__ import annotations

import base64
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


class Document(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.json = {}
        self.active_json = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if tag == "script" and attributes.get("type") == "application/json":
            self.active_json = attributes["id"]
            self.json[self.active_json] = ""

    def handle_data(self, value):
        if self.active_json is not None:
            self.json[self.active_json] += value

    def handle_endtag(self, tag):
        if tag == "script":
            self.active_json = None

    def resources(self, tag, attribute):
        return [attrs[attribute] for name, attrs in self.tags if name == tag and attribute in attrs]


def decoded(value: str) -> bytes:
    prefix, content = value.split(",", 1)
    assert prefix.startswith("data:") and prefix.endswith(";base64")
    return base64.b64decode(content, validate=True)


class Files(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="av-packaging-test-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def write(self, name, content):
        filename = self.root / name
        filename.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            filename.write_bytes(content)
        else:
            filename.write_text(content, encoding="utf-8", newline="\n")
        return filename

    def invoke(self, command, *, succeeds=True):
        compiler = os.environ.get('AV_TEST_COMPILER_VERSION')
        if compiler and any(str(part).endswith('build.mjs') for part in command) and '--compiler-version' not in command:
            command = [*command, '--compiler-version', compiler]
        result = subprocess.run([str(part) for part in command], cwd=self.root, text=True, capture_output=True, timeout=45)
        if succeeds:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("    at ", result.stderr)
        return result


class BuildTests(Files):
    @classmethod
    def setUpClass(cls):
        if not NODE:
            raise RuntimeError("build tests require Node.js; provide node on PATH")

    def build(self, *arguments, succeeds=True):
        return self.invoke([NODE, TOOLS / "build.mjs", "--entry", self.root / "src/index.ts", "--output", self.root / "library.js", *arguments], succeeds=succeeds)

    def execute(self, assertion, filename="library.js"):
        runner = self.write("runner.mjs", "import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';\nconst context = vm.createContext({});\nvm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);\n" + assertion)
        self.invoke([NODE, runner, self.root / filename])

    def test_local_module_graph_exports_are_live_and_private(self):
        self.write("src/nested/value.ts", 'export let count = 2; export function increment() { count += 1; }\nexport const label = "</script><!--<script>& Unicode: λ";\n')
        self.write("src/nested/index.ts", 'export * from "./value.js";\n')
        self.write("src/index.ts", 'export * from "./nested";\nimport { count } from "./nested";\nexport function twice() { return count * 2; }\n')
        self.build()
        self.execute('assert.equal(context.AgenticVisuals.twice(), 4); context.AgenticVisuals.increment(); assert.equal(context.AgenticVisuals.count, 3); assert.equal(context.AgenticVisuals.twice(), 6); assert.equal(context.AgenticVisuals.label, "</script><!--<script>& Unicode: λ"); for (const key of ["define", "require", "modules", "exports"]) assert.equal(context[key], undefined);')

    def test_changed_source_requires_explicit_replacement_and_check_detects_drift(self):
        self.write("src/index.ts", 'export const answer = "before";\n')
        self.build()
        original = (self.root / "library.js").read_bytes()
        self.assertIn("unchanged", self.build().stdout)
        self.build("--check")
        self.write("src/index.ts", 'export const answer = "after";\n')
        self.assertIn("bundle differs", self.build("--check", succeeds=False).stderr)
        self.assertEqual((self.root / "library.js").read_bytes(), original)
        self.assertIn("--replace", self.build(succeeds=False).stderr)
        self.build("--replace")
        self.build("--check")
        self.execute('assert.equal(context.AgenticVisuals.answer, "after");')
        self.assertFalse(list(self.root.glob(".av-build-*")))

    def test_example_entry_can_import_library_without_polluting_its_exports(self):
        self.write("src/index.ts", 'export function render(label: string) { return label; }\n')
        entry = self.write("examples/demo.ts", 'import { render } from "../src/index"; export function renderDemo() { return render("illustrative"); }\n')
        self.build()
        self.invoke([NODE, TOOLS / "build.mjs", "--entry", entry, "--root", self.root, "--output", self.root / "demo.js", "--global", "AgenticVisualsDemo"])
        self.execute('assert.equal(context.AgenticVisualsDemo.renderDemo(), "illustrative"); assert.equal(context.AgenticVisuals, undefined);', "demo.js")
        self.execute('assert.equal(context.AgenticVisuals.renderDemo, undefined);')

    def test_external_and_dynamic_dependencies_fail_before_output(self):
        cases = [
            ('import { value } from "external"; export { value };', "external module dependencies"),
            ('export async function load() { return import("./other"); }', "dynamic imports"),
            ('declare const require: (name: string) => unknown; export const value = require("./other");', "require calls"),
            ('import other = require("./other"); export { other };', "CommonJS"),
        ]
        self.write("src/other.ts", "export const value = 1;\n")
        for source, message in cases:
            with self.subTest(message=message):
                self.write("src/index.ts", source)
                self.assertIn(message, self.build(succeeds=False).stderr)
                self.assertFalse((self.root / "library.js").exists())

    def test_compiler_errors_preserve_prior_output(self):
        self.write("src/index.ts", "export const value: string = 1;\n")
        output = self.write("library.js", "previous output\n")
        result = self.build("--replace", succeeds=False)
        self.assertIn("TS2322", result.stderr)
        self.assertEqual(output.read_text(), "previous output\n")

    def test_build_collects_factories_without_executing_browser_code(self):
        self.write("src/index.ts", 'export const element = document.querySelector("#report");\n')
        self.build()
        self.assertTrue((self.root / "library.js").is_file())

    def test_generated_bundle_and_composition_execute_after_standalone_assembly(self):
        self.write("src/index.ts", 'export function render(label: string) { return "received: " + label; }\n')
        self.build()
        body = self.write("body.html", '<main id="report"></main>')
        label = '</script><!--<script> λ & "quote"'
        data = self.write("data.json", json.dumps({"label": label}, ensure_ascii=False))
        first = self.write("first.js", 'const reportData = JSON.parse(document.getElementById("data").textContent);\n')
        second = self.write("second.js", 'globalThis.rendered = AgenticVisuals.render(reportData.label);\n')
        output = self.root / "report.html"
        self.invoke([sys.executable, TOOLS / "assemble.py", "--body", body, "--script", self.root / "library.js", "--data", f"data={data}", "--script", first, "--script", second, "--output", output])
        document = Document(output.read_text())
        payload = self.write("payload.json", json.dumps({"scripts": [decoded(value).decode() for value in document.resources("script", "src")], "data": document.json["data"], "label": label}))
        runner = self.write("assembled.mjs", 'import fs from "node:fs"; import vm from "node:vm"; import assert from "node:assert/strict"; const p = JSON.parse(fs.readFileSync(process.argv[2], "utf8")); const context = vm.createContext({document:{getElementById: () => ({textContent:p.data})}}); for (const script of p.scripts) vm.runInContext(script, context); assert.equal(context.rendered, "received: " + p.label); assert.equal(context.define, undefined);')
        self.invoke([NODE, runner, payload])

    def test_ambient_external_dependency_is_not_silently_dropped(self):
        self.write("src/external.d.ts", 'declare module "external" { export const value: string; }')
        self.write("src/index.ts", '/// <reference path="./external.d.ts" />\nexport { value } from "external";')
        self.assertIn("external module dependencies", self.build(succeeds=False).stderr)

    def test_actual_renderer_svg_titles_survive_standalone_assembly(self):
        bundle = self.root / "actual-renderers.js"
        self.invoke([NODE, TOOLS / "build.mjs", "--output", bundle])
        body = self.root / "rendered-body.html"
        runner = self.write("render.mjs", 'import fs from "node:fs"; import vm from "node:vm"; const c = vm.createContext({}); vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), c); const v = c.AgenticVisuals; const paired = v.pairedComparison({title:"Accessible pairs", axis:"Observation", leftLabel:"A", rightLabel:"B", pairs:[{label:"Pair </title> & Unicode λ",left:1,right:2}]}); const intervals = v.intervalPlot({title:"Accessible intervals", axis:"Observation", intervalLabel:"Supplied bounds",items:[{label:"Interval",low:1,high:3,estimate:2}]}); fs.writeFileSync(process.argv[3], "<main>" + paired + intervals + "</main>");')
        self.invoke([NODE, runner, bundle, body])
        source = body.read_text()
        source_titles = sum(tag == "title" for tag, _ in Document(source).tags)
        self.assertGreater(source_titles, 0, "actual renderer fixture must exercise SVG accessibility titles")
        self.assertIn("<svg", source)
        output = self.root / "assembled.html"
        self.invoke([sys.executable, TOOLS / "assemble.py", "--body", body, "--style", TOOLS / "styles/agentic-visuals.css", "--script", bundle, "--output", output])
        assembled = output.read_text()
        self.assertIn(source, assembled, "assembly must retain the renderer's accessible SVG markup")
        self.assertEqual(sum(tag == "title" for tag, _ in Document(assembled).tags), source_titles + 1)


class AssemblyTests(Files):
    def setUp(self):
        super().setUp()
        self.body = self.write("body.html", '<main id="report"><p>A &amp; B — λ</p></main>')
        self.output = self.root / "report.html"

    def assemble(self, *arguments, succeeds=True):
        return self.invoke([sys.executable, TOOLS / "assemble.py", "--body", self.body, "--output", self.output, *arguments], succeeds=succeeds)

    def test_hostile_data_title_scripts_and_styles_keep_their_meaning(self):
        hostile = '</script><img src="https://invalid.example" onerror="bad()"><!--<script> λ\u2028\u2029 & </ScRiPt>'
        data = self.write("data.json", '{"label":' + json.dumps(hostile, ensure_ascii=False) + ',"precise":123456789012345678901,"decimal":0.1234567890123456789}')
        script_text = 'globalThis.raw = String.raw`</script><!--<script>\\n`; globalThis.label = JSON.parse(document.getElementById("evidence").textContent).label;\n'
        script = self.write("compose.js", script_text)
        style_text = '.sample::after { content: "</style><script>content</script>"; } /* url(https://example.invalid) */\n'
        style = self.write("style.css", style_text)
        self.assemble("--title", '</title><script>bad()</script>', "--data", f"evidence={data}", "--style", style, "--script", script)
        rendered = self.output.read_text()
        document = Document(rendered)
        self.assertEqual(decoded(document.resources("script", "src")[-1]).decode(), script_text)
        self.assertEqual(decoded(document.resources("link", "href")[0]).decode(), style_text)
        self.assertEqual(json.loads(document.json["evidence"])["label"], hostile)
        self.assertIn("123456789012345678901", document.json["evidence"])
        self.assertIn("0.1234567890123456789", document.json["evidence"])
        self.assertEqual(sum(tag == "script" and attrs.get("id") not in ("av-report-recipe", "av-startup") for tag, attrs in document.tags), 2)
        self.assertEqual(sum(tag == "title" for tag, _ in document.tags), 1)
        self.assertFalse(document.resources("img", "src"))
        csp = next(attrs["content"] for tag, attrs in document.tags if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy")
        self.assertIn("connect-src 'none'", csp)
        self.assertIn("script-src data:", csp)
        self.assertIsNotNone(NODE, "script embedding verification requires Node.js")
        payload = self.write("payload.json", json.dumps({"script": script_text, "data": document.json["evidence"], "hostile": hostile}))
        runner = self.write("execute.mjs", 'import fs from "node:fs"; import vm from "node:vm"; import assert from "node:assert/strict"; const p = JSON.parse(fs.readFileSync(process.argv[2], "utf8")); const context = vm.createContext({document:{getElementById: () => ({textContent:p.data})}}); vm.runInContext(p.script, context); assert.equal(context.label, p.hostile); assert.equal(context.raw, String.raw`</script><!--<script>\\n`);')
        self.invoke([NODE, runner, payload])

    def test_embeds_local_images_fonts_and_assets_used_in_data(self):
        logo_bytes = b"\x89PNG\r\n\x1a\nfixture image bytes"
        logo = self.write("logo.png", logo_bytes)
        font = self.write("font.woff2", b"fixture font bytes")
        self.write("body.html", '<main><img alt="Logo" src="{{asset:logo}}"><a href="https://example.invalid/source">Source</a></main>')
        style = self.write("style.css", '@font-face { font-family: Custom; src: url("{{asset:font}}"); }')
        data = self.write("data.json", '{"image":"{{asset:logo}}"}')
        self.assemble("--asset", f"logo={logo}", "--asset", f"font={font}", "--style", style, "--data", f"data={data}")
        document = Document(self.output.read_text())
        self.assertEqual(decoded(document.resources("img", "src")[0]), logo_bytes)
        self.assertEqual(decoded(json.loads(document.json["data"])["image"]), logo_bytes)
        embedded_css = decoded(document.resources("link", "href")[0]).decode()
        self.assertIn(base64.b64encode(font.read_bytes()).decode(), embedded_css)
        self.assertEqual(document.resources("a", "href"), ["https://example.invalid/source"])

    def test_css_dependencies_fail_without_writing_output(self):
        cases = [
            '@import "local.css";',
            '@\\69mport "https://invalid.example";',
            '.image { background: url("local.png"); }',
            '.image { background: u\\72l("https://invalid.example"); }',
            '.image { background: image-set("remote.png" 1x); }',
        ]
        for source in cases:
            with self.subTest(source=source):
                style = self.write("style.css", source)
                self.assemble("--style", style, succeeds=False)
                self.assertFalse(self.output.exists())

    def test_html_dependencies_and_csp_incompatible_composition_are_rejected(self):
        cases = [
            '<img src="local.png">',
            '<img src="https://invalid.example/logo.png">',
            '<img srcset="data:image/png;base64,AA== 1x">',
            '<svg><image href="local.svg"/></svg>',
            '<script src="local.js"></script>',
            '<button onclick="doSomething()">Go</button>',
            '<div style="background:url(local.png)">Content</div>',
            '</body><body>escaped fragment',
            '<a href="local-evidence.pdf">Evidence</a>',
            '<main>Unclosed element',
            '<main><!--unfinished comment',
            '<textarea>Unclosed raw text',
            '<textarea/>Unclosed raw text',
            '<p title="unterminated attribute',
            '<plaintext>Never closes',
            '<title>HTML document title</title>',
            '<div><title>Nested HTML document title</title></div>',
            '<svg><foreignObject><title>HTML title in foreign content</title></foreignObject></svg>',
            '<svg><title><title>HTML title inside an SVG integration point</title></title></svg>',
            '<svg><title>SVG title</title></svg><title>HTML title after SVG</title>',
        ]
        for body in cases:
            with self.subTest(body=body):
                self.write("body.html", body)
                self.assemble(succeeds=False)
                self.assertFalse(self.output.exists())

    def test_svg_namespace_resumes_inside_nested_svg(self):
        body = '<svg><title>Outer accessible title</title><foreignObject><div><svg><title>Inner accessible title</title></svg></div></foreignObject></svg>'
        self.write("body.html", body)
        self.assemble()
        self.assertIn(body, self.output.read_text())

    def test_svg_presentation_dependencies_fail_before_output(self):
        cases = [
            ('fill', 'url(https://example.invalid/colors.svg#paint) red'),
            ('stroke', r'u\72l("remote-paints.svg#stroke")'),
            ('filter', 'blur(1px) url(local-filters.svg#soften)'),
            ('clip-path', 'URL(&quot;remote-clips.svg#crop&quot;)'),
            ('mask', 'url(#local-mask), url(https://example.invalid/masks.svg#mask)'),
            ('marker', 'url(markers.svg#arrow)'),
            ('marker-start', 'url(markers.svg#start)'),
            ('marker-mid', "url('markers.svg#mid')"),
            ('marker-end', r'url(\6d arkers.svg#end)'),
            ('cursor', "url('pointer.cur') 4 4, pointer"),
            ('color-profile', 'url(profiles.icc)'),
            ('fill', 'src("remote-paints.svg#paint")'),
            ('mask', 'image-set("remote-mask.png" 1x)'),
            ('fill', 'url(\u00a0data:image/svg+xml,paint)'),
            ('stroke', 'url(\\64\u00a0ata:image/svg+xml,paint)'),
        ]
        for number, (attribute, value) in enumerate(cases):
            with self.subTest(attribute=attribute, value=value):
                self.output = self.root / f"rejected-svg-{number}.html"
                value = value.replace('"', '&quot;')
                self.write("body.html", f'<main><svg><path d="M0 0L20 20" {attribute}="{value}"/></svg></main>')
                result = self.assemble(succeeds=False)
                self.assertIn(f"path[{attribute}]", result.stderr)
                self.assertFalse(self.output.exists())

    def test_svg_local_presentation_resources_and_non_css_metadata_survive(self):
        body = r'''<main><svg aria-label="Paint url(remote.svg) isn't a dependency" data-note="A backslash \ and url(remote.svg)">
<defs><linearGradient id="paint"><stop stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient><filter id="soft"><feGaussianBlur stdDeviation="1"/></filter><clipPath id="crop"><rect width="20" height="20"/></clipPath><mask id="local-mask"><rect width="20" height="20" fill="white"/></mask><marker id="arrow"><path d="M0 0L2 1L0 2"/></marker></defs>
<path d="M0 0L20 20" fill="u\72l(\23 paint) currentColor" stroke="url(&quot;#paint&quot;) blue" filter="url(#soft)" clip-path="url('#crop')" mask="url(#local-mask)" marker-start="none" marker-mid="url(#arrow)" marker-end="url(#arrow)"/>
<foreignObject><div fill="url(ordinary-html-metadata)">A non-SVG attribute</div><svg><rect fill="url(#paint)"/></svg></foreignObject>
</svg></main>'''
        self.write("body.html", body)
        self.assemble()
        self.assertIn(body, self.output.read_text())

    def test_svg_presentation_assets_embed_bytes_and_reject_undeclared_tokens(self):
        svg = self.write("paints.svg", '<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="paint"><stop stop-color="red"/></linearGradient></defs></svg>')
        image_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aVFAAAAAASUVORK5CYII=")
        image = self.write("pointer.png", image_bytes)
        self.write("body.html", '<svg><rect fill="url(&quot;{{asset:paints}}#paint&quot;)" cursor="url({{asset:pointer}}) 0 0, auto"/></svg>')
        self.assertIn("asset 'paints' is undeclared", self.assemble(succeeds=False).stderr)
        self.assertFalse(self.output.exists())
        self.assemble("--asset", f"paints={svg}", "--asset", f"pointer={image}")
        document = Document(self.output.read_text())
        rect = next(attrs for tag, attrs in document.tags if tag == "rect")
        self.assertEqual(decoded(rect["fill"][5:-2].removesuffix("#paint")), svg.read_bytes())
        self.assertEqual(decoded(rect["cursor"][4:].split(")", 1)[0]), image_bytes)

    def test_asset_and_data_errors_are_explicit(self):
        image = self.write("image.png", b"bytes")
        data = self.write("data.json", '{"x":1,"x":2}')
        self.assertIn("unused assets", self.assemble("--asset", f"image={image}", succeeds=False).stderr)
        self.assertIn("duplicate object key", self.assemble("--data", f"data={data}", succeeds=False).stderr)
        self.write("data.json", '{"value":NaN}')
        self.assertIn("non-JSON number", self.assemble("--data", f"data={data}", succeeds=False).stderr)
        self.write("data.json", '{}')
        self.assertIn("already exists", self.assemble("--data", f"report={data}", succeeds=False).stderr)
        self.write("body.html", '<img src="{{asset:missing}}">')
        self.assertIn("is undeclared", self.assemble(succeeds=False).stderr)

    def test_svg_assets_must_be_self_contained(self):
        self.write("body.html", '<img src="{{asset:logo}}">')
        for content, message in [
            ('<image href="remote.png"/>', "non-embedded reference"),
            ('<rect fill="url(remote.svg#paint)"/>', "non-embedded reference"),
            ('<rect mask="image-set(&quot;remote-mask.png&quot; 1x)"/>', "image-set() is unsupported"),
        ]:
            with self.subTest(content=content):
                svg = self.write("logo.svg", f'<svg xmlns="http://www.w3.org/2000/svg">{content}</svg>')
                self.assertIn(message, self.assemble("--asset", f"logo={svg}", succeeds=False).stderr)
                self.assertFalse(self.output.exists())
        self.write("logo.svg", '<svg xmlns="http://www.w3.org/2000/svg"><style>.x{fill:url(#color)}</style><path class="x" d="M0 0"/></svg>')
        self.assemble("--asset", f"logo={svg}")
        document = Document(self.output.read_text())
        self.assertEqual(decoded(document.resources("img", "src")[0]), svg.read_bytes())

    def test_mermaid_declarations_embed_one_runtime_before_consumers_and_retain_notices(self):
        runtime = TOOLS / "vendor/mermaid/mermaid.min.js"
        script = self.write("compose.js", 'globalThis.ready = typeof mermaid;')
        for index, (body, feature) in enumerate([
            ('<main><div data-av-requires = "mermaid">First</div><div data-av-requires="mermaid">Second</div></main>', []),
            ('<main>Runtime composition</main>', ["--feature", "mermaid"]),
        ]):
            self.write("body.html", body)
            self.output = self.root / f"mermaid-{index}.html"
            self.assemble(*feature, "--script", script, "--script", runtime, "--script", runtime)
            document = Document(self.output.read_text())
            embedded = [decoded(value) for value in document.resources("script", "src")]
            self.assertEqual(embedded, [(TOOLS / "dist/agentic-startup.js").read_bytes(), runtime.read_bytes(), script.read_bytes()])
            self.assertEqual(json.loads(document.json["av-report-recipe"])["headScripts"], ["av-startup"])
            self.assertIn("av-mermaid-notices", document.json)
            notices = json.loads(document.json["av-mermaid-notices"])
            self.assertIn("Mermaid", json.dumps(notices))
            self.assertIn("av-mermaid-notices", json.loads(document.json["av-report-recipe"])["data"])
            self.assertEqual(json.loads(document.json["av-report-recipe"])["body"], body)

    def test_repeat_and_replace_behavior_preserves_work_and_cleans_scratch(self):
        self.assemble()
        original = self.output.read_bytes()
        self.assertIn("unchanged", self.assemble().stdout)
        self.write("body.html", "<main>Changed body</main>")
        self.assertIn("--replace", self.assemble(succeeds=False).stderr)
        self.assertEqual(self.output.read_bytes(), original)
        self.assemble("--replace")
        changed = self.output.read_bytes()
        self.write("body.html", '<img src="missing.png">')
        self.assemble("--replace", succeeds=False)
        self.assertEqual(self.output.read_bytes(), changed)
        self.assertFalse(list(self.root.glob(".av-assemble-*")))

    def test_outputs_cannot_replace_inputs_or_follow_symlinks(self):
        result = self.assemble("--output", self.body, "--replace", succeeds=False)
        self.assertIn("overwrite an input", result.stderr)
        target = self.write("target.html", "keep")
        self.output.symlink_to(target)
        self.assertIn("not a regular file", self.assemble("--replace", succeeds=False).stderr)
        self.assertEqual(target.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
