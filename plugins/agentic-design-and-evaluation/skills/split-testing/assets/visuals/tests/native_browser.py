#!/usr/bin/env python3
"""Native Chromium qualification of assembled reports; no dependency installation.

Prepare inputs with examples/assemble-previews.py. File mode is the default.
Content mode is an explicit, limited fallback: it exercises Chromium rendering and
interaction, but not file-origin storage, permissions, or operating-system opens.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

VISUALS = Path(__file__).resolve().parents[1]

async def qualify(args) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'mode': args.mode, 'checks': [], 'page_errors': [], 'network_requests': [], 'mermaid': [], 'inputs': {}}
    def check(name, truth, detail=None):
        result['checks'].append({'name': name, 'passed': bool(truth), 'detail': detail})
        assert truth, f'{name}: {detail}'
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=args.browser, args=['--no-sandbox'])
        result['browser'] = browser.version
        context = await browser.new_context(viewport={'width':1440, 'height':1000}, accept_downloads=True)
        await context.set_offline(True)
        page = await context.new_page()
        page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
        page.on('request', lambda request: result['network_requests'].append(request.url[:160]) if request.url.startswith(('https:', 'http:')) else None)
        async def load(name):
            path = args.previews / (name + '.html')
            raw = path.read_bytes();result['inputs'][name] = hashlib.sha256(raw).hexdigest()
            if args.mode == 'file':
                await page.goto(path.resolve().as_uri(), wait_until='load')
            else:
                await page.set_content(raw.decode('utf-8'), wait_until='load')
            await page.evaluate('window.scrollTo(0,0)')
            await page.evaluate("Promise.all([...document.querySelectorAll('.av-workspace')].map(root=>AgenticVisuals.enhanceVisuals(root).whenIdle()))")
            await page.wait_for_timeout(250)
        async def screenshot(name):
            await page.wait_for_timeout(220)
            await page.screenshot(path=str(args.output/(name+'.png')), animations='disabled')
        async def fits(selector):
            return await page.locator(selector).evaluate_all("items=>items.filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1;})")
        try:
            for width in [320,390,760,1440]:
                await page.set_viewport_size({'width':width,'height':1000 if width>500 else 844})
                await load('compact')
                check(f'No page overflow at {width}px', await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
                check(f'Single-view rail omitted at {width}px', not await page.locator('.av-workspace-nav').is_visible())
                check(f'Controls fit at {width}px', await fits('.av-workspace-bar,.av-card-header'))
                await screenshot(f'compact-{width}')
                await page.locator('[data-av-settings] > summary').click()
                await page.wait_for_timeout(100)
                box = await page.locator('.av-settings-panel').bounding_box()
                viewport = page.viewport_size
                check(f'Display panel fits at {width}px', bool(box) and box['x']>=0 and box['y']>=0 and box['x']+box['width']<=viewport['width']+1 and box['y']+box['height']<=viewport['height']+1, box)
                await page.locator('[data-av-setting="theme"][value="dark"]').locator('..').click()
                check(f'Dark appearance applies at {width}px', await page.locator('.av-workspace').get_attribute('data-av-theme')=='dark')
                await screenshot(f'display-dark-{width}')
                await page.keyboard.press('Escape')
                check(f'Escape returns Display focus at {width}px', await page.evaluate("document.activeElement === document.querySelector('[data-av-settings] > summary')"))
            await page.set_viewport_size({'width':1440,'height':1000})
            await load('embedded')
            check('Independent narrow container fits in wide browser', await fits('#left-study .av-workspace-bar,#left-study .av-card-header'))
            await screenshot('independent-themes')
            await page.locator('#left-study [data-av-settings] > summary').click()
            await page.locator('#left-study [data-av-setting="theme"][value="dark"]').locator('..').click()
            check('Sibling theme ownership retained', await page.locator('#right-study').get_attribute('data-av-theme')=='dark')
            await page.locator('#left-study [data-av-setting="theme"][value="light"]').locator('..').click()
            check('Changing left report leaves right dark', await page.locator('#right-study').get_attribute('data-av-theme')=='dark')
            await page.keyboard.press('Escape')
            await page.set_viewport_size({'width':390,'height':844})
            check('Independent report composition stacks on a small screen', await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
            await screenshot('independent-themes-mobile')
            await page.set_viewport_size({'width':1440,'height':1000})
            await load('field-study')
            await page.locator('[data-av-view="tradeoffs"]').click()
            bar = await page.locator('.av-workspace-bar').bounding_box()
            check('Report utilities remain reachable after navigation', bar['y']>=0 and bar['y']<50, bar)
            await screenshot('field-study-tradeoffs')
            chart = page.locator('.av-workspace-panel:not([hidden]) [data-av-figure]').first
            menu = chart.locator('.av-command-overflow > summary').first
            await menu.click();await page.mouse.move(5,5);await page.wait_for_timeout(300)
            check('Pointer transit does not dismiss a menu', await chart.locator('.av-command-overflow').first.get_attribute('open') is not None)
            await menu.focus();await page.keyboard.press('ArrowDown')
            check('Arrow key enters a visible command', await page.evaluate("document.activeElement.matches('.av-command-menu button') && document.activeElement.getClientRects().length>0"))
            await page.keyboard.press('Escape')
            check('Menu Escape restores trigger focus', await menu.evaluate('e=>e===document.activeElement'))
            # Native mouse click must not jump the page down to the inspector.
            await chart.locator('[data-av-figure-action="select-items"]').click()
            mark = chart.locator('[data-av-inspect]').last
            await mark.scroll_into_view_if_needed()
            before = await page.evaluate('scrollY')
            await mark.click()
            check('Pointer item inspection preserves page position', abs(await page.evaluate('scrollY')-before)<3)
            async def figure_download(figure, action, filename):
                button = figure.locator('[data-av-figure-action="'+action+'"]').first
                if not await button.is_visible():
                    await figure.locator('.av-command-overflow > summary').first.click()
                async with page.expect_download(timeout=20000) as pending:
                    await button.click()
                download = await pending.value
                path = args.output / filename
                await download.save_as(str(path))
                return path
            # Exercise the reader command, not a private export helper. The full
            # source drawing and context must be independent of its live zoom.
            before_svg = ET.parse(await figure_download(chart, 'svg', 'figure-fitted.svg')).getroot()
            await chart.locator('[data-av-zoom-in]').click()
            await chart.locator('[data-av-zoom-in]').click()
            await chart.locator('.av-plot-scroll').evaluate('e=>{e.scrollLeft=80;e.scrollTop=40;}')
            after_svg = ET.parse(await figure_download(chart, 'svg', 'figure-zoomed.svg')).getroot()
            check('SVG export retains full bounds at non-default zoom', before_svg.get('viewBox') == after_svg.get('viewBox'))
            check('SVG export retains figure context', all(text in ''.join(after_svg.itertext()) for text in ['Fast capture, or less work later?', 'Handoff preparation', 'Capture time']))
            check('SVG export retains all drawing elements', len(list(before_svg.iter())) == len(list(after_svg.iter())))
            png = (await figure_download(chart, 'png', 'figure-zoomed.png')).read_bytes()
            size = [int.from_bytes(png[16:20], 'big'), int.from_bytes(png[20:24], 'big')]
            check('PNG download is a complete image', png[:8] == b'\x89PNG\r\n\x1a\n' and size == [int(float(after_svg.get('width'))), int(float(after_svg.get('height')))], size)
            await chart.locator('[data-av-zoom-reset]').click()
            # Searching reads retained evidence without changing the current view.
            before = await page.locator('[data-av-view="tradeoffs"]').get_attribute('aria-current')
            await page.locator('[data-av-search]').fill('pending')
            check('Search finds retained evidence', await page.locator('[data-av-search-hit]').count()>0)
            check('Search retains current view', await page.locator('[data-av-view="tradeoffs"]').get_attribute('aria-current')==before)
            await screenshot('search-evidence')
            await page.keyboard.press('Escape')
            await load('stress')
            start = time.perf_counter()
            await page.locator('[data-av-search]').fill('qualification')
            check('Large search finds long evidence', await page.locator('[data-av-search-hit]').count()>0, {'elapsed_ms':round((time.perf_counter()-start)*1000,2)})
            await page.keyboard.press('Escape')
            records = page.locator('#long-records')
            await records.scroll_into_view_if_needed()
            select = records.locator('[data-av-select]')
            before = await records.locator('.av-collection-stage').bounding_box()
            scroll = await page.evaluate('scrollY')
            await select.select_option('artifact-1')
            after = await records.locator('.av-collection-stage').bounding_box()
            check('Long/short records keep a stable reading stage', abs(before['height']-after['height'])<2)
            check('Record selection preserves page position', abs(await page.evaluate('scrollY')-scroll)<3)
            await records.locator('[data-av-compare="artifact-0"]').check()
            await records.locator('[data-av-compare="artifact-1"]').check()
            check('Comparison presents both selected originals', await records.locator('[data-av-object]:not([hidden])').count()==2)
            await screenshot('long-record-comparison')
            await page.locator('[data-av-view="diagrams"]').click()
            check('Valid Mermaid diagram rendered', await page.locator('#valid-diagram [data-av-mermaid]').get_attribute('data-av-mermaid-state')=='ready')
            await page.wait_for_function("document.querySelector('#failed-diagram [data-av-mermaid]').getAttribute('data-av-mermaid-state')==='error'")
            await page.locator('#failed-diagram .av-diagram-source > summary').click()
            check('Invalid Mermaid source remains visible', await page.locator('#failed-diagram [data-av-mermaid]').get_attribute('data-av-mermaid-state')=='error' and 'intentionally' in await page.locator('#failed-diagram pre').inner_text())
            await page.locator('#diagram-parent > summary [data-av-focus]').click()
            check('Expanded parent named', 'Source, check and result' in await page.locator('dialog[open]').get_attribute('aria-label'))
            await page.locator('#diagram-child > summary [data-av-focus]').click()
            check('Nested view offers Back', await page.locator('[data-av-close-focus]').inner_text()=='Back')
            await screenshot('nested-expanded')
            await page.locator('[data-av-close-focus]').click()
            check('Return restores parent accessible name', 'Source, check and result' in await page.locator('dialog[open]').get_attribute('aria-label'))
            check('Outermost view offers Close', await page.locator('[data-av-close-focus]').inner_text()=='Close')
            await page.keyboard.press('Escape')
            check('Escape exits expanded stack', await page.locator('dialog[open]').count()==0)
            await load('compact')
            root = page.locator('.av-workspace')
            commands = await page.locator('[data-av-command]').count()
            await page.evaluate("() => { AgenticVisuals.enhanceVisuals(document.querySelector('.av-workspace')); }")
            check('Notebook uses the report heading, not a nested figure title', await page.locator('[data-av-notebook-target] option').first.text_content() == 'A cooler housing, an open question')
            check('Repeated enhancement creates no duplicate commands', await page.locator('[data-av-command]').count()==commands)
            record = page.locator('#sensor-note--record')
            check('Repeated record names are distinguishable', len(set(await record.locator('[data-av-object] > summary').all_text_contents())) == 3)
            await record.locator('[data-av-select]').select_option('artifact-2')
            passage = 'operator note: <script> is literal evidence text.'
            await record.locator('[data-av-object="artifact-2"] pre').evaluate("""(pre,quote)=>{const text=pre.firstChild,start=text.textContent.indexOf(quote),range=document.createRange();range.setStart(text,start);range.setEnd(text,start+quote.length);getSelection().removeAllRanges();getSelection().addRange(range);}""",passage)
            await record.locator(':scope > summary [data-av-review-action="new-note"]').click()
            check('Native text range anchors the exact passage', passage in await page.locator('.av-context-review blockquote').inner_text())
            await page.locator('.av-context-review textarea').fill('Check the interrupted run.')
            await page.locator('.av-context-review [data-av-review-action="save"]').click()
            await page.locator('[data-av-notebook] > summary').click()
            await page.locator('[data-av-notebook-target]').select_option('sensor-note--plot')
            await page.locator('[data-av-notebook-action="new-annotation"]').click()
            exact = 'Keep this exact note: <script>text only</script>\n`````\n# Not a heading\nOriginal 日本語 / e\u0301 / 👩🏽‍🚀'
            await page.locator('.av-context-review textarea').fill(exact)
            await page.keyboard.press('Escape')
            check('Escape retains draft and closes editor', not await page.locator('.av-context-review').is_visible())
            await page.locator('[data-av-notebook] > summary').click()
            await page.locator('.av-notebook-popover').wait_for(state='visible')
            check('Aggregate notebook shows anchored draft', exact in await page.locator('[data-av-notebook-notes]').inner_text())
            await screenshot('anchored-notebook')
            async with page.expect_download() as pending:
                await page.locator('[data-av-notebook-action="export-report"]').click()
            download = await pending.value;reviewed=args.output/'reviewed-report.html';await download.save_as(str(reviewed))
            # A native download can move focus outside and dismiss the utility.
            if not await page.locator('[data-av-notebook-action="export-handoff"]').is_visible():
                await page.locator('[data-av-notebook] > summary').click()
            async with page.expect_download() as pending:
                await page.locator('[data-av-notebook-action="export-handoff"]').click()
            download = await pending.value;handoff=args.output/'review-handoff.md';await download.save_as(str(handoff))
            check('Handoff retains exact feedback', exact in handoff.read_text())
            await page.evaluate("AgenticVisuals.enhanceVisuals(document.querySelector('.av-workspace'))()")
            check('Cleanup removes command and popup layers', await page.locator('.av-command-bar,[data-av-utility-layer],.av-context-review').count()==0)
            await page.evaluate("() => { AgenticVisuals.enhanceVisuals(document.querySelector('.av-workspace')); }")
            await page.locator('[data-av-notebook] > summary').click()
            check('Re-enhancement recovers session draft', exact in await page.locator('[data-av-notebook-notes]').inner_text())
            # Fresh page, original embedded recipe: no serialized live dialogs,
            # duplicated controls or discarded draft in a reviewed HTML copy.
            await page.close()
            page = await context.new_page()
            page.on('pageerror', lambda error: result['page_errors'].append(str(error)))
            page.on('request', lambda request: result['network_requests'].append(request.url[:160]) if request.url.startswith(('https:', 'http:')) else None)
            if args.mode=='file': await page.goto(reviewed.resolve().as_uri())
            else: await page.set_content(reviewed.read_text())
            await page.evaluate("AgenticVisuals.enhanceVisuals(document.querySelector('.av-workspace')).whenIdle()")
            await page.locator('[data-av-notebook] > summary').click()
            check('Reviewed HTML reopens with exact draft', exact in await page.locator('[data-av-notebook-notes]').inner_text())
            check('Reviewed HTML starts without transient dialogs', await page.locator('dialog[open],.av-context-review').count()==0)
            check('Reviewed HTML has one command set', await page.locator('[data-av-command]').count()==commands)
            # Respect operating-system motion preferences in the actual browser.
            await page.emulate_media(reduced_motion='reduce')
            check('Reduced-motion animation is disabled', await page.locator('.av-workspace').evaluate("e=>getComputedStyle(e).animationDuration==='0s'"))
            if args.mermaid:
                await load('stress')
                fixtures=json.loads((VISUALS/'tests/mermaid-fixtures/index.json').read_text())
                for fixture in fixtures:
                    source=(VISUALS/'tests/mermaid-fixtures'/fixture['file']).read_text()
                    outcome=await page.evaluate("""async ({source,index})=>{
                      const host=document.createElement('div');host.innerHTML=AgenticVisuals.reportSurface({id:'fixture-'+index,body:AgenticVisuals.mermaidDiagram({id:'diagram-'+index,title:'Renderer fixture '+index,source})});document.body.appendChild(host);
                      const scope=host.firstElementChild,cleanup=AgenticVisuals.enhanceVisuals(scope);await cleanup.whenIdle();
                      const diagram=scope.querySelector('[data-av-mermaid]');const result={state:diagram.getAttribute('data-av-mermaid-state'),message:diagram.querySelector('[data-av-mermaid-status]').textContent,svgCount:scope.querySelectorAll('[data-av-mermaid-output] svg').length};cleanup();host.remove();return result;
                    }""", {'source':source,'index':len(result['mermaid'])})
                    result['mermaid'].append({**fixture,**outcome});print('Mermaid',fixture['file'],outcome['state'],flush=True)
            check('No page-level JavaScript errors', not result['page_errors'], result['page_errors'])
            check('No network requests', not result['network_requests'], result['network_requests'])
            result['status']='passed'
        except Exception as error:
            result['status']='failed';result['failure']=str(error)
            await screenshot('failure')
            raise
        finally:
            (args.output/'native-results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
            await browser.close()
    print(f"{len(result['checks'])} native checks passed; results: {args.output}")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previews',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--browser',default='/usr/bin/chromium')
    parser.add_argument('--mode',choices=['file','content'],default='file')
    parser.add_argument('--mermaid',action='store_true',help='Render every supplied Mermaid fixture and record individual outcomes.')
    args=parser.parse_args();asyncio.run(qualify(args))

if __name__=='__main__':main()
