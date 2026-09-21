#!/usr/bin/env python3
"""Native consumer qualification of drawing tools and large evidence comparisons.
No installation. File mode qualifies actual file opening; content mode is an
explicit rendering/interaction fallback, not file-origin or durable-storage proof.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from playwright.async_api import async_playwright

async def qualify(args):
    args.output.mkdir(parents=True,exist_ok=True)
    report={'mode':args.mode,'checks':[],'page_errors':[],'network_requests':[],'inputs':{}}
    def check(name,value,detail=None):
        report['checks'].append({'name':name,'passed':bool(value),'detail':detail})
        print(('PASS ' if value else 'FAIL ')+name,flush=True)
        assert value,(name,detail)
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.browser,args=['--no-sandbox'])
        report['browser']=browser.version
        context=await browser.new_context(viewport={'width':1440,'height':1000},offline=True,accept_downloads=True)
        page=await context.new_page();page.set_default_timeout(10000)
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('request',lambda r:report['network_requests'].append(r.url) if r.url.startswith(('http:','https:')) else None)
        async def idle():
            await page.evaluate("Promise.all([...document.querySelectorAll('.av-workspace')].map(e=>AgenticVisuals.enhanceVisuals(e).whenIdle()))")
            await page.wait_for_timeout(180)
        async def load(name):
            raw=(args.previews/(name+'.html')).read_bytes();report['inputs'][name]=hashlib.sha256(raw).hexdigest()
            if args.mode=='file':await page.goto((args.previews/(name+'.html')).resolve().as_uri(),wait_until='load')
            else:await page.set_content(raw.decode(),wait_until='load')
            await idle()
        async def shot(name):await page.screenshot(path=str(args.output/(name+'.png')),animations='disabled')
        async def shown(deck):return await deck.locator('.av-reading-stage>[data-av-object]:not([hidden])').evaluate_all('(es)=>es.map(e=>e.dataset.avObject)')
        async def readable_pressed(locator):
            return await locator.evaluate("""e=>{const c=document.createElement('canvas').getContext('2d');const luminance=color=>{c.clearRect(0,0,1,1);c.fillStyle=color;c.fillRect(0,0,1,1);const p=c.getImageData(0,0,1,1).data;return [.2126,.7152,.0722].reduce((s,w,i)=>{const v=p[i]/255;return s+w*(v<=.04045?v/12.92:((v+.055)/1.055)**2.4)},0)};const s=getComputedStyle(e),a=luminance(s.color),b=luminance(s.backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)}""")
        async def fits(locator):return await locator.evaluate_all('(es)=>es.filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1&&r.top>=-1&&r.bottom<=innerHeight+1})')
        try:
            await load('stress');deck=page.locator('#long-records');await deck.scroll_into_view_if_needed()
            original=await deck.locator('.av-object-body pre').all_text_contents()
            check('No checkbox wall or duplicate record selector',not await deck.locator('.av-artifact-controls').is_visible() and not await deck.locator('.av-explorer-tools').is_visible())
            height=(await deck.locator('.av-reading-stage').bounding_box())['height']
            await deck.locator('[data-av-read-compare]').click();picker=deck.locator('.av-record-picker');check('Searchable record picker fits the viewport',await fits(picker))
            await deck.locator('[data-av-records-all]').click();await deck.locator('[data-av-records-done]').click();await idle()
            check('Twelve selected records do not become twelve columns',await deck.locator('[data-av-compare]:checked').count()==12 and 2<=len(await shown(deck))<=4)
            check('Reading panes retain useful width',await deck.locator('.av-reading-stage>[data-av-object]:not([hidden])').evaluate_all('(es)=>es.every(e=>e.clientWidth>=280)'))
            check('Read and compare retain a stable stage height',abs(height-(await deck.locator('.av-reading-stage').bounding_box())['height'])<2)
            await shot('reading-panes')
            pin=deck.locator('[data-av-pin-record="artifact-1"]');check('Reference control is enabled in the accessible tree',await pin.is_enabled())
            await pin.click();await idle();await deck.locator('[data-av-reader-next]').click();await idle()
            visible=await shown(deck);check('Pinned reference remains beside the next reading window',visible[0]=='artifact-1' and 'artifact-0' not in visible,visible)
            # Select long records in all positions for deterministic independent scroll ranges.
            await deck.locator('[data-av-record-picker]').click();await deck.locator('[data-av-records-clear]').click()
            for key in ['artifact-0','artifact-3','artifact-6','artifact-9']:await deck.locator(f'[data-av-pick-record="{key}"]').check()
            await deck.locator('[data-av-records-done]').click();await idle()
            await deck.locator('[data-av-reader-sync]').click()
            bodies=deck.locator('.av-reading-stage>[data-av-object]:not([hidden])>.av-object-body')
            await bodies.first.evaluate('e=>e.scrollTop=(e.scrollHeight-e.clientHeight)*.43');await page.wait_for_timeout(150)
            ratios=await bodies.evaluate_all('(es)=>es.map(e=>e.scrollTop/Math.max(1,e.scrollHeight-e.clientHeight))')
            check('Scroll together links relative progress',min(ratios)>.4 and max(ratios)-min(ratios)<.015,ratios)
            await bodies.nth(1).evaluate('e=>e.scrollTop=(e.scrollHeight-e.clientHeight)*.68');await page.wait_for_timeout(150)
            ratios=await bodies.evaluate_all('(es)=>es.map(e=>e.scrollTop/Math.max(1,e.scrollHeight-e.clientHeight))')
            check('Either reading pane can lead linked scrolling',min(ratios)>.65 and max(ratios)-min(ratios)<.015,ratios)
            await deck.locator('[data-av-reader-sync]').click();before=await bodies.nth(1).evaluate('e=>e.scrollTop')
            await bodies.first.evaluate('e=>e.scrollTop=10');await page.wait_for_timeout(120)
            check('Unlinking restores independent scrolling',abs(before-await bodies.nth(1).evaluate('e=>e.scrollTop'))<1)
            await deck.locator('[data-av-reader-next]').click();await idle();await deck.locator('[data-av-reader-previous]').click();await idle()
            check('Paging back retains each record reading position',abs(await bodies.first.evaluate('e=>e.scrollTop')-10)<2)
            # Bulk matching keeps a nonmatching selected record rather than replacing the set.
            await deck.locator('[data-av-record-picker]').click();await deck.locator('[data-av-record-search]').fill('Record 12');await deck.locator('[data-av-records-all]').click()
            check('Filtered select-all adds only matching records',await deck.locator('[data-av-compare]:checked').count()==5 and await deck.locator('[data-av-compare="artifact-11"]').is_checked())
            await deck.locator('[data-av-record-search]').fill('no such evidence');check('Empty filter is explicit and does not lose selection','0 records' in await deck.locator('.av-picker-count').inner_text() and await deck.locator('[data-av-compare]:checked').count()==5)
            await deck.locator('[data-av-record-search]').fill('');await deck.locator('[data-av-records-all]').click();await deck.locator('[data-av-records-done]').click();await deck.locator('[data-av-reader-cards]').click();await idle()
            check('All cards lays out the whole selected set in rows',len(await shown(deck))==12 and await deck.locator('.av-reading-stage').evaluate('e=>new Set([...e.children].filter(c=>!c.hidden).map(c=>Math.round(c.getBoundingClientRect().top))).size>1'))
            await deck.scroll_into_view_if_needed();await shot('all-cards')
            await deck.locator('[data-av-reader-cards]').click();await deck.locator('[data-av-pin-record]:visible').first.click();await idle()
            for width in [280,320,390,520,760,1024,1440]:
                await page.set_viewport_size({'width':width,'height':900});await page.wait_for_timeout(180);await deck.scroll_into_view_if_needed()
                positions=[]
                for _ in range(4):
                    positions.append(await deck.evaluate('e=>e.getBoundingClientRect().top+scrollY'));await page.wait_for_timeout(60)
                check(f'Fractional plot fitting settles without downstream jitter at {width}px',max(positions)-min(positions)<.1,positions)
                check(f'Comparison container does not overflow at {width}px',await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                geometry=await deck.locator('.av-reading-stage>[data-av-object]:not([hidden])').evaluate_all('(es)=>es.map(e=>({width:e.clientWidth,parent:e.parentElement.clientWidth}))')
                check(f'Pane capacity is responsive at {width}px',all(r['width']>=275 or abs(r['parent']-r['width'])<4 for r in geometry),geometry)
                if width==390:
                    toggle=deck.locator('[data-av-reader-reference]');check('Narrow comparison offers a reference switch',await toggle.is_visible());await toggle.click();check('Reference is readable at full available width',await deck.locator('.av-reading-stage>[data-av-reference]:not([hidden])').count()==1);await toggle.click();await shot('mobile-reference')
            await page.evaluate("document.documentElement.style.fontSize='200%'")
            # Poll native geometry without Playwright's injected eval loop: the
            # delivered CSP deliberately rejects unsafe-eval.
            for _ in range(100):
                if await deck.evaluate("e=>{const s=e.querySelector('.av-reading-stage');return s.style.getPropertyValue('--av-reader-columns')==='1'&&s.querySelectorAll(':scope>[data-av-object]:not([hidden])').length===1}"):break
                await page.wait_for_timeout(50)
            enlarged=await deck.locator('.av-reading-stage>[data-av-object]:not([hidden])').evaluate_all('(es)=>es.map(e=>e.clientWidth)')
            check('Text enlargement reduces columns instead of crushing text',len(enlarged)==1 and enlarged[0]>500,enlarged)
            await deck.locator('[data-av-record-picker]').click();check('Enlarged picker remains viewport bounded',await fits(picker));await page.keyboard.press('Escape');await page.evaluate("document.documentElement.style.fontSize=''")
            check('All original evidence bytes survive comparison changes',original==await deck.locator('.av-object-body pre').evaluate_all('(es)=>es.sort((a,b)=>Number(a.closest("[data-av-object]").dataset.avObject.split("-")[1])-Number(b.closest("[data-av-object]").dataset.avObject.split("-")[1])).map(e=>e.textContent)'))
            # Actual native record text anchor and portable handoff after DOM reorder.
            await page.wait_for_timeout(180);await deck.locator('[data-av-read-one]').click();await deck.locator('[data-av-record-picker]').click();await deck.locator('[data-av-open-record="artifact-9"]').click();await idle()
            quote=await deck.locator('[data-av-object="artifact-9"] pre').evaluate("e=>{const r=document.createRange();r.setStart(e.firstChild,0);r.setEnd(e.firstChild,9);getSelection().removeAllRanges();getSelection().addRange(r);return r.toString()}")
            await deck.locator(':scope > summary [data-av-review-action="new-note"]').click();editor=page.locator('.av-context-review:not([hidden])');await editor.locator('textarea').fill('Check this exact retained record after comparison.');await editor.get_by_role('button',name='Save note',exact=True).click();await idle()
            await page.locator('[data-av-notebook]>summary').click();await page.locator('[data-av-notebook-tab="share"]').click()
            async with page.expect_download() as future:await page.locator('[data-av-notebook-action="export-handoff"]').click()
            download=await future.value;await download.save_as(args.output/'comparison-handoff.md');handoff=(args.output/'comparison-handoff.md').read_text()
            check('Handoff retains the exact record quotation after pinning and paging',quote in handoff and 'Check this exact retained record' in handoff and 'Attached to the original target' in handoff)
            check('Handoff download leaves the notebook open and usable',await page.get_by_role('button',name='Close notebook',exact=True).is_visible())
            await page.get_by_role('button',name='Close notebook',exact=True).click()
            await page.locator('[data-av-view="diagrams"]').click();await idle();figure=page.locator('#valid-diagram');await figure.scroll_into_view_if_needed();await idle()
            check('No idle selection row under the figure toolbar',not await figure.locator('[data-av-selection-menu]').is_visible() and await figure.locator('.av-selection-help').count()==0)
            before=await figure.locator('.av-plot-scroll').bounding_box();await figure.locator('[data-av-mode-menu]').click();await figure.locator('.av-tool-help>summary').click();after=await figure.locator('.av-plot-scroll').bounding_box()
            check('Selection instructions never expand the report layout',abs(before['y']-after['y'])<1 and abs(before['height']-after['height'])<1)
            check('Drawing tools are contained with a reachable Close',await fits(figure.locator('.av-drawing-tools')));await shot('drawing-tools-help')
            await page.keyboard.press('Escape');check('Escape restores the drawing-tool trigger focus',await figure.locator('[data-av-mode-menu]').evaluate('e=>e===document.activeElement'))
            await figure.locator('[data-av-mode-menu]').click();await figure.locator('[data-av-figure-action="select-items"]').click()
            marks=figure.locator('[data-av-mermaid-item]');await marks.first.click();await marks.nth(1).click(modifiers=['Control']);await figure.locator('[data-av-selection-menu]').click()
            check('Selection chip exposes exact multi-item actions',await figure.locator('[data-av-item-selected]').count()==2 and await figure.locator('[data-av-selection-command="bookmark"]').is_visible())
            await figure.locator('[data-av-selection-command="add"]').click();check('Touch-friendly additive selection is explicit',await figure.locator('[data-av-selection-command="add"]').get_attribute('aria-pressed')=='true');check('Pressed additive-selection action retains readable foreground',await readable_pressed(figure.locator('[data-av-selection-command="add"]'))>=4.5);await page.keyboard.press('Escape');await marks.nth(2).click();check('Additive taps retain earlier selected items',await figure.locator('[data-av-item-selected]').count()==3)
            await figure.locator('[data-av-selection-menu]').click();await figure.locator('[data-av-selection-command="clear"]').click();check('Clear removes contextual actions without a blank row',not await figure.locator('[data-av-selection-menu]').is_visible());check('Clearing selection returns focus to a reachable drawing control',await figure.locator('[data-av-mode-menu]').evaluate('e=>e===document.activeElement'));await shot('drawing-toolbar')
            await figure.locator('[data-av-figure-action="expand"]').click();await page.locator('.av-focus-dialog [data-av-mode-menu]').click();check('Tools stay in the active expanded viewing context',await page.locator('.av-focus-dialog .av-drawing-tools[data-av-open]').count()==1);await page.keyboard.press('Escape');await page.keyboard.press('Escape');check('Expanded return retains the same toolbar nodes',await figure.locator('[data-av-mode-menu]').count()==1)
            # A distinct consumer composition checks the set/reading-window boundary
            # at scale, with duplicate labels, literal hostile text and 120 records.
            await page.evaluate("""() => {
              const records=Array.from({length:120},(_,i)=>({label:i<2?'Repeated name':'Record '+(i+1),mediaType:'text/plain',text:'Source '+i+'\\n<img src=x onerror=alert(1)> 日本語\\n'+'Evidence remains literal. '.repeat(50+i)}));
              const host=document.createElement('div');host.id='large-consumer-host';document.body.appendChild(host);
              host.innerHTML=AgenticVisuals.reportSurface({id:'large-consumer',theme:'dark',body:AgenticVisuals.nativeArtifactViewer({id:'large-records',title:'Original observations',artifacts:records})});
              window.__largeCleanup=AgenticVisuals.enhanceVisuals(host.firstElementChild);
            }""")
            large=page.locator('#large-records');await large.scroll_into_view_if_needed();await large.locator('[data-av-read-compare]').click()
            check('Large picker initially bounds rendered choices',await large.locator('.av-record-option:visible').count()==60 and await large.locator('[data-av-records-more]').is_visible())
            await large.locator('[data-av-records-more]').click();check('Every record remains reachable beyond the initial choice window',await large.locator('.av-record-option:visible').count()==120)
            await large.locator('[data-av-record-search]').fill('Record 120');check('Picker finds records beyond its initial window',await large.locator('.av-record-option:visible').count()==1)
            await large.locator('[data-av-record-search]').fill('');await large.locator('[data-av-records-all]').click();await large.locator('[data-av-records-done]').click()
            check('120 chosen records still use a bounded readable window',await large.locator('[data-av-compare]:checked').count()==120 and len(await shown(large))<=4)
            check('Repeated record labels remain distinguishable',len(set(await large.locator('[data-av-open-record="artifact-0"],[data-av-open-record="artifact-1"]').all_text_contents()))==2)
            check('Markup-like source text is not executed as HTML',await large.locator('img[src="x"]').count()==0 and '<img src=x' in await large.locator('[data-av-object="artifact-0"] pre').text_content())
            await large.locator('[data-av-reader-cards]').click();check('All cards retains all 120 original records',len(await shown(large))==120)
            check('Pressed dark comparison controls retain readable foreground',await readable_pressed(large.locator('[data-av-reader-cards]'))>=4.5)
            await large.evaluate("el=>el.scrollIntoView({block:'start'})")
            await page.screenshot(path=str(args.output/'large-comparison-dark.png'),animations='disabled')
            await page.evaluate("window.__largeCleanup();document.getElementById('large-consumer-host').remove();delete window.__largeCleanup")
            check('Large sibling cleanup removes its controls and panels',await page.locator('#large-records,.av-record-picker[aria-label="Original observations"]').count()==0)
            # Feature fallback: test the documented non-popover path without changing security settings.
            await page.evaluate("HTMLElement.prototype.showPopover=undefined;HTMLElement.prototype.hidePopover=undefined")
            await load('compact');await page.locator('#sensor-note--record [data-av-record-picker]').click();check('Picker has a bounded fallback without native popover',await fits(page.locator('.av-record-picker[data-av-open]')));await page.keyboard.press('Escape')
            before_controls=await page.evaluate("({pickers:document.querySelectorAll('[data-av-record-picker]').length,modes:document.querySelectorAll('[data-av-mode-menu]').length})")
            await page.evaluate("(()=>{const root=document.querySelector('.av-workspace');AgenticVisuals.enhanceVisuals(root)();window.__reader=AgenticVisuals.enhanceVisuals(root);return __reader.whenIdle()})()")
            check('Cleanup and re-enhancement do not duplicate workbenches',before_controls==await page.evaluate("({pickers:document.querySelectorAll('[data-av-record-picker]').length,modes:document.querySelectorAll('[data-av-mode-menu]').length})"))
            check('No page-level runtime errors',not report['page_errors'],report['page_errors']);check('No external runtime requests',not report['network_requests'])
        except Exception:
            report['failure_geometry'] = []
            for _ in range(8):
                report['failure_geometry'].append(await page.evaluate("({width:innerWidth,scrollY,stage:[...document.querySelectorAll('.av-reading-stage')].map(e=>({box:e.getBoundingClientRect().toJSON(),columns:e.style.getPropertyValue('--av-reader-columns')})),figure:[...document.querySelectorAll('.av-plot-scroll')].slice(0,2).map(e=>e.getBoundingClientRect().toJSON())})"))
                await page.wait_for_timeout(60)
            await shot('failure')
            raise
        finally:
            (args.output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            await browser.close()
    print(f"{len(report['checks'])} native comparison checks passed")
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--previews',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--browser',default='/usr/bin/chromium');parser.add_argument('--mode',choices=['file','content'],default='file');args=parser.parse_args();asyncio.run(qualify(args))
