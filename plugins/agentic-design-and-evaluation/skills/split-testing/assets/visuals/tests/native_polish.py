#!/usr/bin/env python3
"""Second-pass consumer checks. Requires already installed Playwright/Chromium.
File mode qualifies file opening; explicit content mode does not qualify file
permissions or native persistence. No dependencies are installed by this runner.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, time
from pathlib import Path
from playwright.async_api import async_playwright

async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'mode':args.mode,'checks':[],'errors':[],'network_requests':[], 'inputs':{}}
    started=time.monotonic()
    def check(name, passed, detail=None):
        result['checks'].append({'name':name,'passed':bool(passed),'detail':detail})
        print(f'{time.monotonic()-started:.2f}s '+('PASS ' if passed else 'FAIL ')+name,flush=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=args.browser,args=['--no-sandbox'])
        result['browser']=browser.version
        context=await browser.new_context(viewport={'width':1440,'height':950},accept_downloads=True)
        await context.set_offline(True)
        page=await context.new_page()
        page.on('pageerror',lambda e: result['errors'].append(str(e)))
        page.on('request',lambda r: result['network_requests'].append(r.url[:180]) if r.url.startswith(('https:','http:')) else None)
        async def load(name):
            path=args.previews/(name+'.html');raw=path.read_bytes();result['inputs'][name]=hashlib.sha256(raw).hexdigest()
            if args.mode=='file':await page.goto(path.resolve().as_uri(),wait_until='load')
            else:await page.set_content(raw.decode(),wait_until='load')
            await page.evaluate("Promise.all([...document.querySelectorAll('.av-workspace')].map(e=>AgenticVisuals.enhanceVisuals(e).whenIdle()))")
            await page.evaluate('scrollTo(0,0)');await page.wait_for_timeout(150)
        async def shot(name):
            await page.screenshot(path=str(args.output/(name+'.png')),animations='disabled')
        async def box(selector):return await page.locator(selector).first.bounding_box()
        async def reachable(selector):
            return await page.locator(selector).first.evaluate("e=>{const r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;return r.width>0&&r.height>0&&x>=0&&x<innerWidth&&y>=0&&y<innerHeight&&e.contains(document.elementFromPoint(x,y));}")
        try:
            for width in [280,320,390,520,760,1024,1440]:
                await page.set_viewport_size({'width':width,'height':844 if width<760 else 950})
                await load('field-study')
                views=await page.locator('[data-av-view]').evaluate_all("es=>es.map(e=>e.getAttribute('data-av-view'))")
                for name in views:
                    await page.locator('[data-av-view="'+name+'"]').click();await page.wait_for_timeout(90)
                    check(f'Full composition / {name} fits {width}px',await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                check(f'Reading controls and utilities do not overlap at {width}px',await page.evaluate("(()=>{const a=document.querySelector('.av-reading-mode').getBoundingClientRect(),b=document.querySelector('.av-workspace-utilities').getBoundingClientRect();return Math.min(a.right,b.right)-Math.max(a.left,b.left)<=1||Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)<=1;})()"))
                check(f'Full-report button is reachable at {width}px',await reachable('[data-av-show-all]'))
                if width in [320,760,1440]:
                    await page.locator('[data-av-view="reliability"]').click();await shot(f'reliability-{width}')
                if width in [320,1440]:
                    await page.locator('[data-av-view="uncertainty"]').click()
                    # Opening hidden nested sections exercises their original live commands.
                    closed=page.locator('.av-workspace-panel:not([hidden]) details.av-card:not([open]) > summary')
                    if await closed.count(): await closed.first.click()
                    await page.wait_for_timeout(150)
                    check(f'Initially hidden command labels are bounded at {width}px',await page.evaluate("[...document.querySelectorAll('.av-workspace-panel:not([hidden]) .av-frame-tools')].filter(e=>e.checkVisibility()).every(e=>e.scrollWidth<=e.clientWidth+1)"))
            await page.set_viewport_size({'width':1024,'height':800});await load('field-study')
            await page.locator('[data-av-view="reliability"]').click()
            target='.av-workspace-panel[data-av-panel="reliability"]'
            before=await box(target)
            await page.locator('[data-av-show-all]').click();await page.wait_for_timeout(250)
            after=await box(target)
            check('Section to full report preserves the reading position',abs(after['y']-before['y'])<4,{'before':before,'after':after})
            await page.locator('[data-av-show-single]').click();await page.wait_for_timeout(200)
            check('Full report returns to the section under the reading line',await page.locator(target).is_visible())
            check('Returning to section view preserves the reading position',abs((await box(target))['y']-before['y'])<4)
            # The DOM can be wider than a narrow iframe-style composition.
            await load('embedded')
            await page.set_viewport_size({'width':1440,'height':900})
            await page.locator('#left-study').evaluate("e=>e.style.width='290px'")
            await page.wait_for_timeout(220)
            check('A dynamically narrowed embedded report contains its controls',await page.locator('#left-study .av-workspace-bar').evaluate("e=>e.scrollWidth<=e.clientWidth+1"))
            await shot('dynamic-embed')
            # Real keyboard focus, stacking and annotation drafts.
            await page.set_viewport_size({'width':320,'height':640});await load('compact')
            await page.locator('[data-av-notebook]>summary').click()
            await page.locator('[data-av-notebook-action="new-annotation"]').click();await page.wait_for_timeout(120)
            check('Annotation textarea is reachable above report controls',await reachable('.av-context-review textarea'))
            check('Annotation actions stay visible in a short viewport',await reachable('.av-context-review [data-av-review-action="save"]'))
            note='Retain <script>literal</script> text — λ and an edited draft.'
            await page.locator('.av-context-review textarea').fill(note)
            await page.keyboard.press('Control+Enter');await page.wait_for_timeout(120)
            check('Control+Enter saves the note and closes the editor',not await page.locator('.av-context-review').is_visible())
            check('Saving returns focus to the notebook trigger',await page.locator('[data-av-notebook]>summary').evaluate('e=>e===document.activeElement'))
            await page.locator('[data-av-notebook]>summary').click()
            await page.locator('[data-av-review-action="edit"]').first.click();await page.wait_for_timeout(120)
            check('Editing an existing note closes the obscuring notebook',not await page.locator('.av-notebook-popover').is_visible())
            check('An existing note editor remains clickable',await reachable('.av-context-review textarea'))
            await shot('mobile-note-editor')
            await page.locator('.av-context-review textarea').fill(note+' Modified.')
            await page.keyboard.press('Escape')
            await page.locator('[data-av-notebook]>summary').click()
            check('Draft survives closing an edited note',await page.locator('[data-av-review-entry]').filter(has_text='Modified.').count()>0)
            await shot('notebook-with-draft')
            # Browser resizing must keep the same draft and its footer reachable.
            await page.locator('[data-av-review-action="edit"]').last.click()
            await page.set_viewport_size({'width':760,'height':360});await page.wait_for_timeout(180)
            check('Landscape editor keeps Save and Close reachable',await reachable('.av-context-review [data-av-review-action="save"]') and await reachable('.av-context-review [data-av-review-action="cancel"]'))
            await shot('landscape-editor')
            await page.keyboard.press('Escape')
            await page.locator('[data-av-settings]>summary').click()
            await page.locator('[data-av-setting="theme"][value="dark"]').locator('..').click();await page.wait_for_timeout(100)
            panel=await box('.av-settings-panel')
            check('Display panel stays in the landscape viewport',panel['y']>=0 and panel['y']+panel['height']<=361,panel)
            await shot('landscape-display')
            await page.locator('[data-av-reset-preferences]').focus();await page.keyboard.press('Tab');await page.wait_for_timeout(80)
            check('Tab leaving Display closes the nonmodal panel',not await page.locator('.av-settings-panel').is_visible())
            # Expanded figure -> native source inspection at a small height.
            await page.set_viewport_size({'width':390,'height':620});await load('compact')
            figure=page.locator('[data-av-figure]').first
            expand=figure.locator('[data-av-figure-action="expand"]')
            if not await expand.is_visible():await figure.locator('.av-command-overflow>summary').first.click()
            await expand.click();await page.wait_for_timeout(200)
            check('Expanded figure Close is reachable on a small screen',await reachable('[data-av-close-focus]'))
            source=page.locator('dialog[open] [data-av-figure-action="source"]').first
            if not await source.is_visible():await page.locator('dialog[open] .av-command-overflow>summary').first.click()
            await source.click();await page.wait_for_timeout(120)
            check('Original source is reachable in an expanded figure',await reachable('dialog[open] [data-av-source-panel] textarea'))
            check('Source wraps long lines without changing its text',await page.locator('[data-av-source-panel] textarea').evaluate('e=>e.wrap==="soft"&&e.scrollWidth<=e.clientWidth+2'))
            await page.locator('[data-av-source-wrap]').uncheck()
            check('Source wrapping can be disabled',await page.locator('[data-av-source-panel] textarea').get_attribute('wrap')=='off')
            await page.locator('[data-av-source-wrap]').check()
            await shot('expanded-source-mobile')
            check('Source reader fills useful mobile reading space',await page.locator('[data-av-source-panel] textarea').evaluate('e=>{const r=e.getBoundingClientRect();return r.width>innerWidth*.75&&r.height>innerHeight*.5}'))
            source_text=await page.locator('[data-av-source-panel] textarea').input_value()
            async with page.expect_download() as transfer:
                await page.locator('[data-av-source-panel] [data-av-figure-action="download-source"]').click()
            download=await transfer.value;source_path=args.output/'original-figure-source.txt';await download.save_as(source_path)
            check('Source download retains the exact original text',source_path.read_text()==source_text)
            check('Source action feedback appears in the source reader',await page.locator('[data-av-source-panel] .av-toast').count()>0)
            await page.keyboard.press('Escape');await page.wait_for_timeout(100)
            check('Source feedback returns with the expanded viewing context',await page.locator('.av-focus-dialog>.av-notifications .av-toast').count()>0)
            check('Escape from source returns to the expanded figure',await page.locator('.av-focus-dialog[open]').count()==1 and await page.locator('[data-av-source-panel][open]').count()==0)
            check('Expanded context does not crowd out the drawing',await page.locator('.av-focus-dialog>.av-dialog-header').evaluate('e=>e.getBoundingClientRect().height<innerHeight*.35'))
            await page.locator('.av-dialog-context>summary').click()
            check('Expanded context can be opened without hiding Close',await reachable('[data-av-close-focus]'))
            await page.locator('.av-dialog-context>summary').click()
            await shot('expanded-figure-mobile')
            await page.locator('.av-focus-dialog [data-av-mode-menu]').click()
            await page.locator('.av-focus-dialog [data-av-figure-action="select-items"]').click()
            await page.locator('.av-focus-dialog [data-av-inspect]').first.click();await page.wait_for_timeout(120)
            check('Selecting an expanded item opens its evidence',await page.locator('.av-dialog-context').get_attribute('open') is not None)
            check('Selected evidence retains readable fields instead of flattened text',await page.locator('[data-av-selected-context] :is(dl,table)').count()>0)
            check('Selected numeric fields are visible without immediately scrolling the inspector',await page.locator('[data-av-selected-context]').evaluate('e=>{const viewport=e.closest(".av-dialog-context-body").getBoundingClientRect();return [...e.querySelectorAll("dd")].every(n=>{const r=n.getBoundingClientRect();return r.top>=viewport.top&&r.bottom<=viewport.bottom})}'))
            await shot('expanded-selected-record')
            await page.locator('[data-av-close-focus]').click()
            for toast in await page.locator('.av-toast-close').all():
                if await toast.is_visible():await toast.click()
            # A consumer can insert a initially closed component and enhance that
            # nonoverlapping sibling independently. It must fit on first opening.
            await page.evaluate('''(()=>{const host=document.createElement('div');host.id='deferred-test';document.body.appendChild(host);host.style.width='280px';host.innerHTML=AgenticVisuals.storyPanel({title:'Initially closed panel',open:false,paragraphs:['Exact evidence remains readable.']});window.cleanupDeferred=AgenticVisuals.enhanceVisuals(host);})()''')
            await page.locator('#deferred-test .av-card>summary').click();await page.wait_for_timeout(100)
            check('A newly opened component fits on its first visible layout',await page.locator('#deferred-test .av-frame-tools').evaluate('e=>e.scrollWidth<=e.clientWidth+1'))
            await page.evaluate("window.cleanupDeferred();document.querySelector('#deferred-test').remove()")
            # The original sources are unchanged by cleanup/re-enhancement.
            before=await page.locator('[data-av-layout-input]').first.get_attribute('data-av-layout-input')
            await page.evaluate("(()=>{const e=document.querySelector('.av-workspace');AgenticVisuals.enhanceVisuals(e)();AgenticVisuals.enhanceVisuals(e);})()")
            await page.wait_for_timeout(180)
            check('Cleanup preserves the original geometry recipe',before==await page.locator('[data-av-layout-input]').first.get_attribute('data-av-layout-input'))
            check('Cleanup creates no duplicate report utilities',await page.locator('[data-av-notebook]').count()==1 and await page.locator('[data-av-settings]').count()==1)
            # Emulated coarse input: touch targets are measured, not inferred from CSS text.
            touch=await browser.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
            await touch.set_offline(True);tp=await touch.new_page()
            path=args.previews/'compact.html'
            if args.mode=='file':await tp.goto(path.resolve().as_uri())
            else:await tp.set_content(path.read_text(),wait_until='load')
            await tp.wait_for_timeout(250)
            check('Coarse-pointer figure commands have 44px hit targets',await tp.locator('.av-command[data-av-command-location="inline"]').evaluate_all("es=>es.filter(e=>e.checkVisibility()).every(e=>{const r=e.getBoundingClientRect();return r.width>=43.9&&r.height>=43.9})"))
            check('Coarse-pointer report has no horizontal overflow',await tp.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            await tp.screenshot(path=str(args.output/'touch-compact.png'));await touch.close()
        except Exception as error:
            result['fatal']=str(error)
            await shot('failure')
        finally:
            check('No page-level JavaScript errors',not result['errors'],result['errors'])
            check('No external network requests',not result['network_requests'],result['network_requests'])
            (args.output/'results.json').write_text(json.dumps(result,indent=2))
            await browser.close()
    if result.get('fatal') or any(not c['passed'] for c in result['checks']):raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previews',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--browser',default='/usr/bin/chromium');parser.add_argument('--mode',choices=['file','content'],default='file')
    asyncio.run(run(parser.parse_args()))
