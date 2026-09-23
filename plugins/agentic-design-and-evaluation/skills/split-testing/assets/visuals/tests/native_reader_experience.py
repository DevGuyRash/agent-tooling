#!/usr/bin/env python3
"""Native reader journeys, plus an explicitly modeled delayed-storage first paint.

Default: direct file opening. --mode content is a constrained fallback; it does
not qualify file-origin permissions or native persistence. No installs/network.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, re, time
from pathlib import Path
from playwright.async_api import async_playwright
VISUALS=Path(__file__).resolve().parents[1]

async def qualify(args):
    args.output.mkdir(parents=True,exist_ok=True)
    report={'mode':args.mode,'checks':[],'page_errors':[],'network_requests':[],'inputs':{},'storage':'Native UI; delayed-storage phase uses an explicit in-memory IndexedDB double, not native persistence.'}
    def check(name,value,detail=None):
        report['checks'].append({'name':name,'passed':bool(value),'detail':detail});print(('PASS ' if value else 'FAIL ')+name,flush=True)
        assert value, f'{name}: {detail}'
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=args.browser,args=['--no-sandbox'])
        report['browser']=browser.version
        context=await browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
        await context.set_offline(True)
        async def new_page():
            page=await context.new_page()
            page.on('pageerror',lambda error:report['page_errors'].append(str(error)))
            page.on('request',lambda req:report['network_requests'].append(req.url[:200]) if req.url.startswith(('http:','https:')) else None)
            return page
        async def idle(page):
            await page.evaluate("Promise.all([...document.querySelectorAll('.av-workspace')].map(root=>AgenticVisuals.enhanceVisuals(root).whenIdle()))")
            await page.wait_for_timeout(120)
        async def load(page,name):
            path=args.previews/(name+'.html');raw=path.read_bytes();report['inputs'][name]=hashlib.sha256(raw).hexdigest()
            if args.mode=='file':await page.goto(path.resolve().as_uri(),wait_until='load')
            else:await page.set_content(raw.decode(),wait_until='load')
            await idle(page)
        async def shot(page,name):
            await page.screenshot(path=str(args.output/(name+'.png')),animations='disabled')
        async def download(page,action,name):
            async with page.expect_download() as future:await action.click()
            value=await future.value;await value.save_as(args.output/name);await idle(page);return (args.output/name).read_bytes()
        async def notebook(page,tab='notes'):
            if await page.locator('[data-av-notebook]').get_attribute('open') is None:
                await page.locator('[data-av-notebook]>summary').click()
            await page.locator(f'[data-av-notebook-tab="{tab}"]').click();await page.wait_for_timeout(80)
        async def close_notebook(page):
            await page.get_by_role('button',name='Close notebook',exact=True).click()
        try:
            page=await new_page();await load(page,'field-study')
            check('Initial readiness gate releases',not await page.locator('html').get_attribute('data-av-starting') and await page.locator('.av-workspace').get_attribute('data-av-ready') is not None)
            search=page.locator('[data-av-search]');results=page.locator('[data-av-search-results]')
            await search.fill('the');await idle(page)
            kinds=await results.locator('[data-av-search-kind]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.avSearchKind)')
            check('Grouped search exposes several result types','text' in kinds and 'items' in kinds and len(kinds)>=3,kinds)
            check('Every mixed-result category initially shows at most three',await results.locator('.av-search-group').evaluate_all('(nodes)=>nodes.every(n=>n.querySelectorAll("[data-av-search-result]").length<=3)'))
            more=results.get_by_role('button',name=re.compile('^Show .* more')).first
            check('Long result categories offer more',await more.count()>0)
            await more.click();check('One category expands without hiding the others',await results.locator('.av-search-group').evaluate_all('(nodes)=>nodes.length>1&&nodes.some(n=>n.querySelectorAll("[data-av-search-result]").length>3)'))
            await results.locator('[data-av-search-kind="items"]').click();check('Type filter contains only the chosen category',await results.locator('.av-search-group').count()==1)
            await search.fill('offline');await page.locator('.av-search-regex').click();await search.fill('/off.*line/i');await idle(page)
            check('Native regex worker returns matches',await results.locator('[data-av-search-result]').count()>0)
            await shot(page,'grouped-regex-search')
            await search.fill('[');await idle(page);check('Malformed regex is visible without a page exception','Invalid expression' in await results.inner_text())
            await page.evaluate("(()=>{const p=document.createElement('p');p.id='regex-stress-only';p.textContent='a'.repeat(24000)+'!';document.querySelector('[data-av-panel]').appendChild(p);window.__heartbeats=0;window.__pulse=setInterval(()=>window.__heartbeats++,25);})()")
            start=time.monotonic();await search.fill('(a+)+$');await idle(page)
            check('Pathological regex is terminated and main thread remains responsive','took too long' in await results.inner_text() and await page.evaluate('window.__heartbeats')>10,{'elapsed':time.monotonic()-start,'heartbeats':await page.evaluate('window.__heartbeats')})
            await page.evaluate("clearInterval(window.__pulse);document.getElementById('regex-stress-only').remove()")
            await page.locator('.av-search-regex').click();await search.fill('offline');await idle(page);check('Literal search recovers after a terminated expression',await results.locator('[data-av-search-result]').count()>0)
            await page.keyboard.press('Escape');check('Escape closes results and returns search focus',not await results.is_visible() and await search.evaluate('(e)=>document.activeElement===e'))

            await page.locator('[data-av-view="evidence"]').click();await idle(page)
            graph=page.locator('.av-card').filter(has=page.get_by_role('heading',name='Follow a claim back to its grounds',exact=True))
            # Only the direct figure for this card, not other relationship diagrams.
            fig=graph.locator('[data-av-figure]').first;await fig.scroll_into_view_if_needed();await idle(page)
            marks=fig.locator('.av-graph-node[data-av-inspect]');check('Representative graph contains independently identified items',await marks.count()>=4)
            await marks.nth(0).click();check('Pan taps do not select nodes',await fig.locator('[data-av-item-selected]').count()==0)
            await fig.locator('[data-av-mode-menu]').click();await fig.get_by_role('button',name='Select items',exact=True).click();await marks.nth(0).click();await marks.nth(1).click(modifiers=['Control']);check('Control-click adds an item',await fig.locator('[data-av-item-selected]').count()==2)
            await marks.nth(3).click(modifiers=['Shift']);check('Shift chooses the source-order range',await fig.locator('[data-av-item-selected]').count()==3)
            await marks.nth(0).click(modifiers=['Control','Shift']);check('Control-Shift adds a range',await fig.locator('[data-av-item-selected]').count()==4)
            await marks.nth(0).click(modifiers=['Control']);check('Control-click removes only that item',await fig.locator('[data-av-item-selected]').count()==3)
            await fig.locator('[data-av-selection-menu]').click();await fig.locator('[data-av-selection-command="inspect"]').click();await idle(page)
            check('Inspect does not return to the last deselected node',await graph.locator('.av-inspector [data-av-object].av-selected').get_attribute('data-av-object')==await marks.nth(1).get_attribute('data-av-inspect'))
            await graph.locator('[data-av-inspector-pin]').click();await idle(page)
            geometry=await graph.evaluate("e=>{const reader=e.querySelector('.av-inspector'),plot=e.querySelector('.av-plot-scroll');const a=reader.getBoundingClientRect(),b=plot.getBoundingClientRect();return{top:a.top-b.top,height:a.height,plotHeight:b.height,layout:reader.parentElement.dataset.avInspectorLayout,outline:getComputedStyle(e.querySelector('[data-av-item-selected]')).outlineStyle}}")
            check('Explicitly pinned inspector stays alongside the drawing with useful height',geometry['layout']=='side' and geometry['top']>=-4 and geometry['height']>=200,geometry)
            widths=await graph.evaluate("e=>{const explorer=e.querySelector('.av-explorer'),toolbar=explorer.querySelector('.av-plot-toolbar'),canvas=explorer.querySelector('[data-av-inspector-canvas]');return{explorer:explorer.getBoundingClientRect().width,toolbar:toolbar.getBoundingClientRect().width,canvas:canvas.getBoundingClientRect().width}}")
            check('Inspector reserves width only beside the drawing',abs(widths['toolbar']-widths['explorer'])<2 and widths['canvas']<widths['toolbar'],widths)
            check('Selection does not add the old white outline',geometry['outline']=='none',geometry)
            await shot(page,'graph-selection-inspector')
            await graph.get_by_role('button',name='Close evidence reader',exact=True).click();await idle(page)
            section_expand=graph.locator(':scope > summary [data-av-focus]')
            await section_expand.click();await idle(page)
            await page.locator('[data-av-close-focus]').click();await idle(page)
            check('Closing the outer expanded section restores its original keyboard trigger',await section_expand.evaluate('e=>document.activeElement===e'))
            await page.set_viewport_size({'width':760,'height':1000});await idle(page)
            reader_opener=fig.locator('.av-inspector-opener')
            if not await reader_opener.is_visible():await fig.locator('.av-command-overflow>summary').click()
            await reader_opener.click();await idle(page)
            await page.set_viewport_size({'width':1440,'height':1000});await idle(page)
            check('Resizing an open evidence drawer keeps focus with its docked evidence',await graph.evaluate("e=>e.querySelector('.av-inspector').contains(document.activeElement)&&!e.querySelector('.av-inspector-dialog').open"))
            focused_evidence=await page.evaluate_handle('document.activeElement')
            await page.set_viewport_size({'width':760,'height':1000});await idle(page)
            check('Narrowing while reading keeps the same evidence focused in an open drawer',await focused_evidence.evaluate("e=>document.activeElement===e&&e.closest('.av-inspector-dialog').open"))
            await page.keyboard.press('Escape');await idle(page)
            check('Closing the resized drawer returns to its reachable opener',await reader_opener.evaluate('e=>document.activeElement===e||document.activeElement===e.closest(".av-command-overflow")?.querySelector("summary")'))
            await page.set_viewport_size({'width':1440,'height':1000});await idle(page)
            await section_expand.focus()
            await page.set_viewport_size({'width':760,'height':1000});await idle(page)
            check('Narrowing elsewhere does not open an evidence drawer',not await graph.locator('.av-inspector-dialog').evaluate('e=>e.open'))
            await page.set_viewport_size({'width':1440,'height':1000});await idle(page)
            await focused_evidence.dispose()
            await fig.locator('[data-av-selection-menu]').click();await fig.locator('[data-av-selection-command="note"]').click();editor=page.locator('.av-context-review:not([hidden])')
            await editor.locator('textarea').fill('Group feedback: inspect these three exact relationships.');await editor.get_by_role('button',name='Save note',exact=True).click();await idle(page)
            await fig.locator('[data-av-selection-menu]').click();await fig.locator('[data-av-selection-command="bookmark"]').click();await idle(page)
            await fig.locator('[data-av-mode-menu]').click();await fig.get_by_role('button',name='Select text',exact=True).click();await page.evaluate('getSelection().removeAllRanges()');await page.wait_for_timeout(80)
            check('Text mode does not silently annotate an earlier node selection',await fig.locator('[data-av-selection-command="note"]').is_disabled())
            quote=await marks.nth(0).evaluate("e=>{const w=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){if(n.parentElement.tagName.toLowerCase()!=='title'&&n.textContent.trim()){const r=document.createRange();r.selectNodeContents(n);getSelection().removeAllRanges();getSelection().addRange(r);return r.toString();}}throw Error('No visible text');}")
            await page.wait_for_timeout(80);check('Native SVG passage selection enables an exact-text note',not await fig.locator('[data-av-selection-command="note"]').is_disabled())
            await fig.locator('[data-av-selection-menu]').click();await fig.locator('[data-av-selection-command="note"]').click();await editor.locator('textarea').fill('Passage feedback: retain the literal wording <script> and ``` fences.');await editor.get_by_role('button',name='Save note',exact=True).click();await idle(page)
            await notebook(page)
            check('Notebook unifies group and text annotations',await page.locator('[data-av-review-entry]').count()==2)
            await page.locator('[data-av-review-entry] .av-review-original').first.locator('summary').click()
            await page.locator('[data-av-review-entry]').first.evaluate('e=>window.__savedCard=e')
            await page.locator('[data-av-notebook-tab="activity"]').click();await page.locator('[data-av-notebook-tab="notes"]').click()
            check('Reading a different notebook tab retains record DOM and evidence disclosure',await page.locator('[data-av-review-entry]').first.evaluate('e=>e===window.__savedCard&&e.querySelector("details").open'))
            await page.get_by_role('searchbox',name='Filter notes and bookmarks').fill('not present in this notebook')
            check('Notebook filter gives an explicit empty result',await page.get_by_text('No entries match these filters.',exact=True).is_visible())
            await page.get_by_role('searchbox',name='Filter notes and bookmarks').fill('')
            await notebook(page,'bookmarks');check('Group bookmark has direct navigation, annotation and removal',await page.locator('[data-av-review-bookmark]').count()==1 and await page.locator('[data-av-review-bookmark] [data-av-review-action]').count()==3)
            await page.locator('[data-av-review-bookmark] [data-av-review-action="note-bookmark"]').click();await editor.locator('textarea').fill('Bookmark follow-up: same original group.');await editor.get_by_role('button',name='Save note',exact=True).click();await idle(page)
            await notebook(page,'bookmarks');await page.locator('[data-av-review-action="remove-bookmark"]').click();await idle(page)
            check('Bookmark removal keeps the notebook open with reachable focus',await page.locator('[data-av-notebook]').get_attribute('open') is not None and await page.evaluate('!!document.activeElement.closest("[data-av-notebook]")'))
            await notebook(page,'activity');check('Activity is human-readable and retains exact timestamps',await page.locator('.av-activity-list time').evaluate_all('(nodes)=>nodes.length>0&&nodes.every(n=>n.dateTime&&n.title===n.dateTime&&!n.textContent.includes("T"))'))
            activity_text=await page.locator('.av-activity-list').inner_text()
            check('Committed notes and bookmarks appear in the activity timeline',all(value in activity_text for value in ['Saved a note','Bookmarked']),activity_text)
            await page.locator('.av-notebook-body').evaluate('(e)=>e.scrollTop=e.scrollHeight')
            check('Notebook close remains reachable at the bottom of activity',await page.get_by_role('button',name='Close notebook',exact=True).is_visible())
            await shot(page,'notebook-activity')

            await notebook(page,'share')
            await page.locator('.av-share-selection > summary').click()
            include=page.locator('.av-review-inclusions input').first;await include.uncheck();await idle(page)
            reviewed=await download(page,page.locator('[data-av-notebook-action="export-report"]'),'reviewed.html')
            await notebook(page,'share')
            handoff=(await download(page,page.locator('[data-av-notebook-action="export-handoff"]'),'handoff.md')).decode()
            await notebook(page,'share');await page.locator('[data-av-notebook-action="export"]').click();await idle(page)
            backup_raw=await download(page,page.locator('[data-av-notebook-action="download"]'),'notebook.json');backup=json.loads(backup_raw)
            seed_match=re.search(r'<script type="application/json" id="av-review-seed">(.*?)</script>',reviewed.decode(),re.S);seed=json.loads(seed_match[1]);seed_book=next(iter(seed['reports'].values()))
            check('Annotated report excludes the chosen feedback and recovery-only bytes','Group feedback:' not in reviewed.decode() and seed_book['originals']==[] and seed_book.get('reviewImports',[])==[])
            check('Readable handoff carries exact passage and context, not excluded feedback',quote in handoff and 'Passage feedback:' in handoff and 'Group feedback:' not in handoff and 'Original evidence' in handoff and 'Attachment:' in handoff)
            check('Backup retains all annotation groups despite share exclusions',len({v['annotationId'] for v in backup['review']['versions'] if v['text'] is not None})==3)
            group=next(v['anchor'] for v in backup['review']['versions'] if v['text'] and v['text'].startswith('Group feedback:'))
            passage=next(v['anchor'] for v in backup['review']['versions'] if v['text'] and v['text'].startswith('Passage feedback:'))
            check('Native group and passage anchors record exact selected evidence',group['kind']=='items' and len(group['items'])==3 and passage['kind']=='text' and passage['quote']==quote)
            recipe=lambda raw:json.loads(re.search(r'<script type="application/json" id="av-report-recipe">(.*?)</script>',raw,re.S)[1])
            original_recipe=recipe((args.previews/'field-study.html').read_text());review_recipe=recipe(reviewed.decode())
            check('Reviewed copy retains the exact original recipe and early startup',review_recipe==original_recipe and review_recipe.get('headScripts')==['av-startup'])
            check('Temporary editors are not serialized into the report recipe','av-context-review' not in review_recipe['body'] and 'data-av-expanded-figure' not in review_recipe['body'])
            reopened=await new_page()
            if args.mode=='file':await reopened.goto((args.output/'reviewed.html').resolve().as_uri(),wait_until='load')
            else:await reopened.set_content(reviewed.decode(),wait_until='load')
            await idle(reopened);await notebook(reopened)
            check('Annotated HTML reopens with only included notes and no duplicate notebook',await reopened.locator('[data-av-review-entry]').count()==2 and await reopened.locator('[data-av-notebook-header]').count()==0 and await reopened.locator('.av-notebook-header').count()==1)
            check('Reopened exact anchors remain attached',await reopened.locator('[data-av-review-entry] .av-review-warning').count()==0)
            await shot(reopened,'reviewed-notebook');await reopened.close()

            await close_notebook(page)
            for width in [280,390,760,1440]:
                await page.set_viewport_size({'width':width,'height':844 if width<500 else 1000});await idle(page)
                diagram=page.locator('#handoff-sequence');await diagram.scroll_into_view_if_needed();await idle(page)
                contained=await diagram.locator('[data-av-mermaid-output] svg[data-av-zoom-target]').evaluate("s=>{const v=s.viewBox.baseVal,b=s.getBBox();return{ok:b.x>=v.x-.5&&b.y>=v.y-.5&&b.x+b.width<=v.x+v.width+.5&&b.y+b.height<=v.y+v.height+.5,width:v.width,height:v.height};}")
                check(f'Mermaid retains intrinsic drawing bounds at {width}px',contained['ok'],contained)
                note_fit=await diagram.locator('svg[data-av-mermaid-scene]').evaluate("s=>{const a=s.querySelector('.noteText').getBBox(),b=s.querySelector('rect.note').getBBox();return{left:a.x-b.x,right:b.x+b.width-a.x-a.width,top:a.y-b.y,bottom:b.y+b.height-a.y-a.height};}")
                check(f'Mermaid note text stays inside its own background at {width}px',all(value>=-0.5 for value in note_fit.values()),note_fit)
                check(f'Mermaid has the figure title as its accessible name at {width}px',await diagram.locator('svg[data-av-mermaid-scene]').get_attribute('aria-label')=='Capture locally, then hand over the complete bundle')
                check(f'Report does not overflow at {width}px',await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                if width==390:
                    await shot(page,'mermaid-mobile')
                    await fig.scroll_into_view_if_needed()
                    if not await reader_opener.is_visible():await fig.locator('.av-command-overflow>summary').click()
                    await reader_opener.click();await idle(page)
                    drawer=page.locator('.av-inspector-dialog[open]');check('Narrow evidence reader uses a separate reachable drawer',await drawer.count()==1 and await drawer.get_by_role('button',name='Close evidence reader',exact=True).is_visible())
                    await shot(page,'evidence-drawer-mobile');await page.keyboard.press('Escape');check('Evidence reader returns to its originating control',await reader_opener.evaluate('e=>document.activeElement===e||document.activeElement===e.closest(".av-command-overflow")?.querySelector("summary")'))
            await page.set_viewport_size({'width':1440,'height':1000});await idle(page)
            diagram=page.locator('#handoff-sequence');await diagram.scroll_into_view_if_needed();await idle(page)
            await diagram.locator('[data-av-zoom-in]').click()
            async def figure_download(action,name):
                await diagram.locator('.av-command-overflow>summary').click()
                return await download(page,diagram.locator(f'[data-av-figure-action="{action}"]'),name)
            svg=await figure_download('svg','sequence.svg');png=await figure_download('png','sequence.png');source=await figure_download('download-source','sequence.mmd')
            check('Mermaid SVG download retains full last-note wording',b'Verify the received records before relying on them' in svg)
            check('Mermaid PNG is an actual decoded export',png.startswith(b'\x89PNG\r\n\x1a\n') and len(png)>1000)
            check('Mermaid source download is exact',source.decode()==await diagram.locator('[data-av-mermaid-source]').get_attribute('data-av-mermaid-source'))

            # A separate live consumer exercises retained author paint and native
            # editable controls. It is not inserted into an already-owned root.
            await page.evaluate("""(()=>{const root=document.createElement('section');root.id='paint-consumer';root.className='av-report';root.innerHTML=AgenticVisuals.visualFigure({id:'paint-figure',title:'Retained author paint',body:'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="180" viewBox="0 0 500 180"><defs><filter id="native-paint"><feGaussianBlur stdDeviation="0.2"/></filter></defs><g data-av-inspect="paint-a" role="button" tabindex="0" style="filter:url(#native-paint)" aria-label="Paint A"><rect x="20" y="20" width="180" height="70" fill="#4488aa"/><text x="30" y="60">Paint A</text></g><g data-av-inspect="paint-b" role="button" tabindex="0" aria-label="Paint B"><rect x="240" y="20" width="180" height="70" fill="#7755aa"/><text x="250" y="60">Paint B</text></g><foreignObject data-av-review-ui="" x="20" y="120" width="300" height="45"><div xmlns="http://www.w3.org/1999/xhtml"><input aria-label="Native editable content" value="Edit this text"/></div></foreignObject></svg>'});document.body.appendChild(root);window.__paintCleanup=AgenticVisuals.enhanceVisuals(root);})()""")
            custom=page.locator('#paint-figure');await custom.scroll_into_view_if_needed();await page.wait_for_timeout(120)
            await custom.locator('[data-av-mode-menu]').click();await custom.get_by_role('button',name='Select items',exact=True).click();await custom.locator('[data-av-inspect="paint-a"]').click()
            native_input=custom.get_by_role('textbox',name='Native editable content');await native_input.click();await page.keyboard.press('Control+a')
            check('Native editable controls keep their own selection shortcuts',await native_input.evaluate('e=>e.selectionStart===0&&e.selectionEnd===e.value.length') and await custom.locator('[data-av-item-selected]').count()==1)
            check('Item selection composes rather than removes authored SVG filters','native-paint' in await custom.locator('[data-av-inspect="paint-a"]').evaluate('e=>getComputedStyle(e).filter'))
            await custom.locator('.av-command-overflow>summary').click();paint_svg=await download(page,custom.locator('[data-av-figure-action="svg"]'),'author-filter.svg')
            paint_state=await page.evaluate("""text=>{const doc=new DOMParser().parseFromString(text,'image/svg+xml');const mark=doc.querySelector('[data-av-inspect="paint-a"]');return{filter:mark?.style.filter,selected:!!doc.querySelector('[data-av-item-selected]'),internal:text.includes('--av-item-filter-chain')||text.includes('--av-item-base-filter'),definition:!!doc.getElementById('native-paint')};}""",paint_svg.decode())
            check('Snapshot keeps original filter definition and excludes transient selection paint',bool(paint_state['filter']) and 'native-paint' in paint_state['filter'] and paint_state['definition'] and not paint_state['selected'] and not paint_state['internal'],paint_state)
            await page.evaluate('window.__paintCleanup()')
            check('Cleanup restores renderer paint and removes selection chrome',await custom.locator('[data-av-inspect="paint-a"]').evaluate("e=>e.style.filter.includes('native-paint')&&!e.style.getPropertyValue('--av-item-filter-chain')") and await custom.locator('.av-item-selection').count()==0)
            await page.evaluate("document.getElementById('paint-consumer').remove();delete window.__paintCleanup")

            # Hybrid native-DOM qualification: actual rendering and event loop,
            # explicitly modeled storage. This is not a file-origin durability test.
            hybrid=await new_page()
            model=(VISUALS/'tests/reader-storage.cjs').read_text().split('function indexedDBDouble()',1)[1].split('function storageWindow',1)[0]
            factory='function indexedDBDouble()'+model
            injection="""(seed)=>{const assert={equal(a,b){if(a!==b)throw Error('Double mismatch')},ok(v){if(!v)throw Error('Double mismatch')}};const copy=v=>v===undefined?v:structuredClone(v);const setImmediate=fn=>setTimeout(fn,1);FACTORY
              const db=indexedDBDouble();db.paused=true;
              Object.defineProperty(window,'indexedDB',{configurable:true,value:db});
              Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:()=>null,setItem(){throw Error('Unexpected legacy write')}}});
              window.__db=db;for(const [key,value]of seed)db.records.set(key,value);
              window.__frames=[];window.__sampling=true;const tick=()=>{const r=document.querySelector('.av-workspace');if(r)window.__frames.push({visible:getComputedStyle(r).visibility!=='hidden',theme:r.dataset.avTheme,palette:r.dataset.avPalette,view:r.querySelector('[data-av-view][aria-current="page"]')?.dataset.avView});if(window.__sampling)requestAnimationFrame(tick)};requestAnimationFrame(tick);
            }""".replace('FACTORY',factory)
            keys=await page.locator('.av-workspace').evaluate("r=>({id:r.id,prefs:r.dataset.avStorageKey,key:r.querySelector('[data-av-notebook]').dataset.avNotebookStorageKey})")
            choices={'theme':'dark','palette':'citrus','spacing':'compact','sections':'multiple','canvas':'plain','texture':'grain','intensity':'low'}
            seeds=[[keys['prefs'],{'version':1,'owner':{'kind':'preferences','reportId':keys['id'],'revision':'1'},'value':choices}],[keys['key'],{'version':1,'owner':{'kind':'notebook','reportId':keys['id'],'revision':backup['state']['revision']},'value':backup}]]
            await hybrid.evaluate(injection,seeds)
            await hybrid.set_content((args.previews/'field-study.html').read_text(),wait_until='load');await hybrid.wait_for_timeout(180)
            check('Delayed owned restoration does not expose authored defaults',not any(frame['visible'] for frame in await hybrid.evaluate('window.__frames')))
            await hybrid.evaluate('window.__db.resume()');await idle(hybrid);await hybrid.wait_for_timeout(120)
            frames=await hybrid.evaluate('window.__sampling=false;window.__frames');visible=[f for f in frames if f['visible']]
            check('First visible frame uses restored appearance and reading section',bool(visible) and all(f['theme']=='dark' and f['palette']=='citrus' and f['view']==backup['state']['viewId'] for f in visible),visible[:5])
            await hybrid.locator('[data-av-settings]>summary').click()
            await hybrid.evaluate("(()=>{for(const theme of ['light','dark','light','dark'])document.querySelector('[data-av-setting=theme][value='+theme+']').click();for(const palette of ['indigo','ocean','citrus'])document.querySelector('[data-av-setting=palette][value='+palette+']').click();})()")
            await idle(hybrid);check('Rapid preference changes retain the latest local choices after modeled commits',await hybrid.locator('.av-workspace').get_attribute('data-av-theme')=='dark' and await hybrid.locator('.av-workspace').get_attribute('data-av-palette')=='citrus')
            await shot(hybrid,'restored-appearance');await hybrid.close()
            # Missing author enhancement still fails open; no-JavaScript static
            # consumers never receive the runtime visibility gate.
            fallback=await new_page();static=(args.previews/'compact.html').read_text()
            static=re.sub(r'<script id="av-script-\d+" src="[^"]*"></script>','',static)
            await fallback.set_content(static,wait_until='load');await fallback.wait_for_timeout(2150)
            check('Missing enhancement fails open instead of hiding the report',await fallback.locator('.av-workspace').is_visible() and await fallback.locator('html').get_attribute('data-av-starting') is None and await fallback.locator('.av-workspace').get_attribute('data-av-ready') is None)
            await fallback.close()
            static_context=await browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844});await static_context.set_offline(True);static_page=await static_context.new_page()
            if args.mode=='file':await static_page.goto((args.previews/'compact.html').resolve().as_uri(),wait_until='load')
            else:await static_page.set_content((args.previews/'compact.html').read_text(),wait_until='load')
            check('JavaScript-disabled report retains readable static evidence',await static_page.locator('.av-workspace').is_visible() and await static_page.locator('[data-av-panel]').first.is_visible())
            await static_context.close()
            check('No native page-level exceptions',not report['page_errors'],report['page_errors'])
            check('No HTTP(S) runtime requests',not report['network_requests'],report['network_requests'])
        finally:
            (args.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
            await browser.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--previews',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--browser',required=True);parser.add_argument('--mode',choices=['file','content'],default='file');asyncio.run(qualify(parser.parse_args()))
