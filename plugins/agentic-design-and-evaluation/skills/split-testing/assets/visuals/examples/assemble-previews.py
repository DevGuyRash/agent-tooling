#!/usr/bin/env python3
"""Assemble fictional browser-qualification reports using installed tools only.

No dependencies are installed. The generated reports need none of these tools.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

VISUALS = Path(__file__).resolve().parents[1]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler-version', help='Explicit exact installed qualification compiler; otherwise the package pin is required.')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    node, tsc = shutil.which('node'), shutil.which('tsc')
    if not node or not tsc:
        parser.error('Node.js and tsc must already be installed. This command installs nothing.')
    expected = args.compiler_version or json.loads((VISUALS / 'package.json').read_text())['devDependencies']['typescript']
    actual = subprocess.check_output([tsc, '--version'], text=True).strip().removeprefix('Version ')
    if actual != expected:
        parser.error(f'Installed tsc is {actual}; requested {expected}. Select an installed compiler explicitly or use the pinned version.')
    qualification = ['--compiler-version', expected] if args.compiler_version else []
    subprocess.run([node, str(VISUALS / 'build.mjs'), '--check', *qualification], check=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='av-previews-') as temporary:
        work = Path(temporary)
        subprocess.run([tsc, '--strict', '--target', 'ES2020', '--lib', 'ES2020,DOM', '--module', 'commonjs', '--outDir', str(work), str(VISUALS / 'examples/demo.ts'), str(VISUALS / 'examples/reader-cases.ts')], check=True)
        generator = """const fs=require('fs'),path=require('path');
const root=process.argv[1],demo=require(path.join(root,'examples/demo.js')),cases=require(path.join(root,'examples/reader-cases.js'));
for(const [name,render] of Object.entries({'field-study':demo.renderDemo,compact:cases.renderCompact,embedded:cases.renderEmbedded,stress:cases.renderStress})) fs.writeFileSync(path.join(root,name+'.html'),render());
"""
        subprocess.run([node, '-e', generator, str(work)], check=True)
        enhance = work / 'enhance.js'
        enhance.write_text("for (const report of document.querySelectorAll('.av-workspace')) AgenticVisuals.enhanceVisuals(report);\n")
        for name in ['field-study', 'compact', 'embedded', 'stress']:
            subprocess.run(['python3', str(VISUALS / 'assemble.py'), '--body', str(work / (name + '.html')), '--output', str(output / (name + '.html')), '--title', 'Fictional evidence report — ' + name, '--style', str(VISUALS / 'styles/agentic-visuals.css'), '--script', str(VISUALS / 'dist/agentic-visuals.js'), '--script', str(enhance), *(['--replace'] if args.replace else [])], check=True)

if __name__ == '__main__':
    main()
