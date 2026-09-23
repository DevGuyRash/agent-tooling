import { attachFloatingPanel, FloatingPanel } from './floating-panel';
import { figureOf, figureSource, figureTitle, visualAdapter, retainFigureOrigin } from './figures';
import { exportFigureSvg, exportFigurePng, downloadBlob, copyFigureImage, copyFigureSource } from './figure-export';
import { attachCommandBar, CommandBar, CommandOptions, commandIcon, focusCommand } from './command-bar';
import { NotificationMessage } from './notifications';
export interface FigureTools {
  figures: readonly HTMLElement[];
  dock(): void;
  refresh(within?: Element): void;
  toolbar(figure: HTMLElement): HTMLElement | null;
  command(figure: HTMLElement, control: HTMLButtonElement, options: CommandOptions): void;
  updateCommand(figure: HTMLElement, control: HTMLButtonElement, options: Partial<CommandOptions>): void;
  click(target: Element): boolean;
  whenIdle(): Promise<void>;
  cleanup(): void;
}
const icons:Record<string,string>={expand:'M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5',png:'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',copy:'M8 8h13v13H8zM16 8V3H3v13h5','copy-source':'m8 5-6 7 6 7m8-14 6 7-6 7m-3-16-2 18',pan:'M8 12V5a2 2 0 0 1 4 0v6-7a2 2 0 0 1 4 0v7-5a2 2 0 0 1 4 0v9c0 4-2 6-6 6h-2c-2 0-3-1-4-3l-4-5c-1-2 1-4 3-2l1 1','select-items':'M5 3v17l5-5 4 7 3-2-4-7h7L5 3','select-text':'M8 3h8M12 3v18M8 21h8M4 8v8M20 8v8',note:'M4 3h16v14l-5 4H4zM8 8h8M8 12h6',bookmark:'M6 3h12v18l-6-4-6 4z'};
icons.svg = icons.png;
icons['download-source'] = icons.png;
icons.source = 'M3 4h18v16H3zM7 8h10M7 12h10M7 16h6';
export function attachFigureTools(root: HTMLElement, expand: (figure: HTMLElement, trigger: HTMLElement) => void, notify: (message:NotificationMessage)=>void = ()=>{}, contextChanged: ()=>void = ()=>{}): FigureTools {
  const document=root.ownerDocument,undo:(()=>void)[]=[],owners=new Map<Element,HTMLElement>(),bars=new Map<HTMLElement,HTMLElement>(),commands=new Map<HTMLElement,CommandBar>(),jobs=new Set<Promise<void>>();let stopped=false;
  const candidates=[...(root.matches('[data-av-figure]')?[root]:[]),...Array.from(root.querySelectorAll<HTMLElement>('[data-av-figure]'))];
  const figures=candidates.filter(figure=>figureOf(figure)===figure);
  const expansions = new Map<HTMLElement, HTMLButtonElement>(), modesByFigure = new Map<HTMLElement, HTMLButtonElement[]>();
  const modePanels = new Map<HTMLElement,FloatingPanel>(), modeTriggers = new Map<HTMLElement,HTMLButtonElement>();
  const initialBounds = new Map<HTMLElement, {width: number; height: number}>();
  // Preflight every adapter before moving any of the author's live content.
  // A bad adapter must not strand half-created toolbars or native plot wrappers.
  for (const figure of figures) {
    const adapter = visualAdapter(figure);
    if (adapter) {
      const bounds = adapter.bounds(figure);
      if (!Number.isFinite(bounds.width) || !Number.isFinite(bounds.height) || bounds.width <= 0 || bounds.height <= 0) throw new Error('Figure adapter returned invalid bounds.');
      initialBounds.set(figure, bounds);
    }
    figureSource(figure);
  }
  for(const figure of figures){
    retainFigureOrigin(figure);const selectionMode=figure.getAttribute('data-av-selection-mode');if(!selectionMode)figure.setAttribute('data-av-selection-mode','pan');undo.push(()=>{if(selectionMode===null)figure.removeAttribute('data-av-selection-mode');else figure.setAttribute('data-av-selection-mode',selectionMode);});
    let toolbar=figure.querySelector<HTMLElement>('.av-plot-toolbar');
    if(!toolbar){toolbar=document.createElement('div');toolbar.className='av-plot-toolbar';toolbar.setAttribute('data-av-controls','');figure.insertBefore(toolbar,figure.firstChild);undo.push(()=>toolbar!.remove());}
    bars.set(figure,toolbar);
    const adapter=visualAdapter(figure);let native=Array.from(figure.querySelectorAll<SVGElement|HTMLElement>('svg,canvas,img')).find(node=>!node.hasAttribute('aria-hidden')&&!node.closest('[data-av-controls]'));
    if(!native&&adapter){const body=figure.querySelector<HTMLElement>('[data-av-figure-body]');if(body){const media=document.createElement('div');media.setAttribute('data-av-custom-media','');body.parentNode!.insertBefore(media,body);media.appendChild(body);native=media;undo.push(()=>{media.parentNode?.replaceChild(body,media);});}}
    if(native&&!native.closest('[data-av-plot]')){
      const media=native;
      const originalAttributes=['data-av-zoom-target','width','height'].map(name=>[name,media.getAttribute(name)] as const);
      const parent=media.parentNode!,marker=document.createComment('av-native-figure');parent.insertBefore(marker,media);
      const plot=document.createElement('div');plot.className='av-plot-shell';plot.setAttribute('data-av-plot','');const scroll=document.createElement('div');scroll.className='av-plot-scroll';scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',figureTitle(figure));plot.appendChild(scroll);parent.insertBefore(plot,media);scroll.appendChild(media);media.setAttribute('data-av-zoom-target','');
      if(adapter){const bounds=initialBounds.get(figure)!;media.setAttribute('width',String(bounds.width));media.setAttribute('height',String(bounds.height));}
      const key='av-native-'+figures.indexOf(figure);plot.setAttribute('data-av-plot-key',key);const previousFor=toolbar.getAttribute('data-av-plot-for');toolbar.setAttribute('data-av-plot-for',key);undo.push(()=>{if(previousFor===null)toolbar!.removeAttribute('data-av-plot-for');else toolbar!.setAttribute('data-av-plot-for',previousFor);});
      const controls=document.createElement('div');controls.className='av-button-group';for(const[key,label]of [['out','−'],['reset','Reset'],['in','+']]){const button=document.createElement('button');button.type='button';button.className='av-button';button.setAttribute('data-av-zoom-'+key,'');button.textContent=label;controls.appendChild(button);}toolbar.insertBefore(controls,toolbar.firstChild);undo.push(()=>controls.remove());
      undo.push(()=>{marker.parentNode?.replaceChild(media,marker);plot.remove();for(const[name,value]of originalAttributes){if(value===null)media.removeAttribute(name);else media.setAttribute(name,value);}});
    }
    const bar=attachCommandBar(toolbar,'Visualization actions');commands.set(figure,bar);
    const make=(action:string,label:string,priority:number,menuOnly=false,group?:string)=>{const button=document.createElement('button');button.type='button';button.className='av-button';button.setAttribute('data-av-figure-action',action);button.textContent=label;toolbar!.appendChild(button);owners.set(button,figure);bar.add(button,{label,priority,menuOnly,group,icon:icons[action]});undo.push(()=>button.remove());return button;};
    const modeTrigger = document.createElement('button'); modeTrigger.type = 'button'; modeTrigger.className = 'av-button';
    modeTrigger.setAttribute('data-av-mode-menu',''); toolbar.appendChild(modeTrigger); modeTriggers.set(figure,modeTrigger);
    const modePanel = attachFloatingPanel(modeTrigger,figure,'Drawing tools'); modePanel.element.classList.add('av-drawing-tools'); modePanels.set(figure,modePanel);
    const modeButtons: HTMLButtonElement[]=[]; modesByFigure.set(figure,modeButtons);
    const modeChoices = document.createElement('div'); modeChoices.className = 'av-mode-choices'; modeChoices.setAttribute('role','group'); modeChoices.setAttribute('aria-label','Drawing interaction'); modePanel.body.appendChild(modeChoices);
    const modes=[['pan','Pan','Move around the drawing'],['select-items','Select','Inspect and annotate items'],...(figure.querySelector('svg text,[data-av-mermaid],[data-av-custom-media]')?[['select-text','Text','Select an exact passage']]:[])];
    for (const [action,label,description] of modes) {
      const button=document.createElement('button'); button.type='button'; button.className='av-mode-choice'; button.setAttribute('data-av-figure-action',action);
      button.setAttribute('aria-label',action==='pan'?'Pan canvas':action==='select-items'?'Select items':'Select text');
      button.appendChild(commandIcon(document,icons[action]));
      const words=document.createElement('span'),name=document.createElement('strong'),hint=document.createElement('small'); name.textContent=label;hint.textContent=description;words.append(name,hint);button.appendChild(words);
      modeChoices.appendChild(button);owners.set(button,figure);modeButtons.push(button);
      button.setAttribute('aria-pressed',String(figure.getAttribute('data-av-selection-mode')===(action==='select-text'?'text':action==='select-items'?'select':'pan')));
    }
    const help = document.createElement('details'); help.className='av-tool-help';
    const summary=document.createElement('summary');summary.textContent='Keyboard & touch';help.appendChild(summary);
    const shortcuts=document.createElement('dl');
    for(const[key,description]of [['Click / tap','Choose one item.'],['Ctrl / ⌘ + click','Add or remove an item.'],['Shift + click','Select a range in source order. Add Ctrl / ⌘ to keep the previous selection.'],['Arrow keys','Pan in Pan mode, or move between items in Select mode. Shift extends item selection.'],['Space + drag','Focus the drawing, then hold Space while dragging to pan without leaving Select or Text mode.'],['Escape','Clear items, or close this panel.'],['Touch','Choose an item, then turn on Add to selection in its selection menu.'],['Text','Drag across a passage, then open Passage to annotate or bookmark it.']]){const term=document.createElement('dt'),definition=document.createElement('dd');term.textContent=key;definition.textContent=description;shortcuts.append(term,definition);}
    help.appendChild(shortcuts);modePanel.body.appendChild(help);
    const initialMode=figure.getAttribute('data-av-selection-mode'),initialAction=initialMode==='text'?'select-text':initialMode==='select'?'select-items':'pan';
    bar.add(modeTrigger,{label:initialMode==='text'?'Text':initialMode==='select'?'Select':'Pan',labelled:true,icon:icons[initialAction],priority:0,group:'mode'});
    undo.push(()=>modeTrigger.remove());
    for(const control of Array.from(toolbar.querySelectorAll<HTMLButtonElement>('[data-av-zoom-out],[data-av-zoom-reset],[data-av-zoom-in]'))){const label=control.hasAttribute('data-av-zoom-reset')?'Reset view':control.hasAttribute('data-av-zoom-out')?'Zoom out':'Zoom in';bar.add(control,{label,priority:10,group:'zoom',width:control.hasAttribute('data-av-zoom-reset')?52:36});}
    expansions.set(figure,make('expand','Expand visualization',20));make('copy','Copy image',40,true);make('png','Download PNG',40,true);make('svg','Download SVG',80,true);
    if(figureSource(figure)){make('copy-source','Copy source',50,true);make('source','View source',90,true);make('download-source','Download source',90,true);}
  }
  const sourceReaders = new Map<HTMLElement, { panel: HTMLElement; open(trigger: HTMLElement): void; cleanup(): void }>();
  function sourceReader(figure: HTMLElement) {
    const existing = sourceReaders.get(figure);
    if (existing) return existing;
    const source = figureSource(figure);
    if (!source) return null;
    const candidate = document.createElement('dialog');
    const modal = typeof candidate.showModal === 'function';
    const panel = modal ? candidate : document.createElement('details');
    panel.className = 'av-source-panel';
    panel.setAttribute('data-av-source-panel', '');
    panel.setAttribute('data-av-review-ui', '');
    panel.setAttribute('aria-label', `Original source: ${figureTitle(figure)}`);
    const header = document.createElement(modal ? 'header' : 'summary');
    header.className = 'av-source-header';
    const title = document.createElement('strong');
    title.textContent = `Original ${source.language === 'json' ? 'JSON' : source.language} source`;
    header.appendChild(title); panel.appendChild(header);
    const text = document.createElement('textarea');
    text.readOnly = true; text.value = source.text; text.rows = 16;
    text.setAttribute('aria-label', 'Original source');
    text.setAttribute('spellcheck', 'false'); text.setAttribute('wrap', 'soft');
    panel.appendChild(text);
    const controls = document.createElement('div'); controls.className = 'av-button-group'; panel.appendChild(controls);
    for (const [action, label] of [['copy-source', 'Copy source'], ['download-source', 'Download source']]) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'av-button';
      button.setAttribute('data-av-figure-action', action); button.textContent = label;
      controls.appendChild(button); owners.set(button, figure);
    }
    const wrapLabel = document.createElement('label'); wrapLabel.className = 'av-source-wrap';
    const wrap = document.createElement('input'); wrap.type = 'checkbox'; wrap.checked = true; wrap.setAttribute('data-av-source-wrap', '');
    wrapLabel.appendChild(wrap); wrapLabel.appendChild(document.createTextNode('Wrap lines')); controls.appendChild(wrapLabel);
    const wrapChanged = () => text.setAttribute('wrap', wrap.checked ? 'soft' : 'off');
    wrap.addEventListener('change', wrapChanged);
    let trigger: HTMLElement | null = null;
    const close = document.createElement('button'); close.type = 'button'; close.className = 'av-button'; close.textContent = 'Close';
    close.setAttribute('aria-label', 'Close source'); (modal ? header : controls).appendChild(close);
    function dismiss(restore = true) {
      if (modal && candidate.open) candidate.close(); else panel.removeAttribute('open');
      if (restore && trigger?.isConnected) focusCommand(trigger);
      if (restore) contextChanged();
    }
    const clicked = (event: Event) => { event.preventDefault(); event.stopPropagation(); dismiss(); };
    const cancelled = (event: Event) => { event.preventDefault(); event.stopPropagation(); dismiss(); };
    close.addEventListener('click', clicked); panel.addEventListener('cancel', cancelled);
    figure.appendChild(panel);
    const reader = {
      panel,
      open(from: HTMLElement) {
        trigger = from;
        // Reopening uses the current source, never an edited textarea value.
        const current=figureSource(figure);if(!current)throw new Error('Original source is no longer available.');
        text.value = current.text;title.textContent=`Original ${current.language==='json'?'JSON':current.language} source`;
        if (modal && !candidate.open) candidate.showModal(); else panel.setAttribute('open', '');
        text.focus({ preventScroll: true });
      },
      cleanup() { dismiss(false); wrap.removeEventListener('change', wrapChanged); close.removeEventListener('click', clicked); panel.removeEventListener('cancel', cancelled); panel.remove(); }
    };
    sourceReaders.set(figure, reader); return reader;
  }
  function registerReview(figure:HTMLElement):void{const toolbar=bars.get(figure),bar=commands.get(figure);if(!toolbar||!bar)return;for(const control of Array.from(toolbar.querySelectorAll<HTMLButtonElement>('[data-av-review-action]'))){const bookmark=control.getAttribute('data-av-review-action')==='bookmark';bar.add(control,{label:bookmark?'Bookmark figure':'Note on figure',priority:60,menuOnly:true,icon:bookmark?icons.bookmark:icons.note});}}
  return {
    figures,
    dock(){for(const figure of figures){const toolbar=bars.get(figure);if(!toolbar)continue;const plot=figure.hasAttribute('data-av-plot')?figure:figure.querySelector<HTMLElement>('[data-av-plot]');if(plot&&toolbar.parentElement!==plot){const marker=document.createComment('av-canvas-toolbar');toolbar.parentNode?.insertBefore(marker,toolbar);plot.insertBefore(toolbar,plot.firstChild);undo.push(()=>marker.parentNode?.replaceChild(toolbar,marker));}registerReview(figure);commands.get(figure)?.refresh();}},
    refresh(within){for(const figure of figures){if(within&&!within.contains(figure)&&within!==figure)continue;registerReview(figure);const expand=expansions.get(figure);if(expand)expand.hidden=figure.hasAttribute('data-av-expanded-figure');commands.get(figure)?.refresh();}},
    toolbar:figure=>bars.get(figure)||null,
    command(figure,control,options){commands.get(figure)?.add(control,options);},
    updateCommand(figure,control,options){commands.get(figure)?.update(control,options);},
    click(target){
      const control=target.closest<HTMLButtonElement>('[data-av-figure-action]'),figure=control&&owners.get(control);if(!control||!figure||stopped)return false;
      const action=control.getAttribute('data-av-figure-action');
      if(['pan','select-items','select-text'].includes(action||'')){
        const mode=action==='select-text'?'text':action==='select-items'?'select':'pan';figure.setAttribute('data-av-selection-mode',mode);
        for(const button of modesByFigure.get(figure)||[])button.setAttribute('aria-pressed',String(button===control));
        const trigger=modeTriggers.get(figure);if(trigger)commands.get(figure)?.update(trigger,{label:mode==='text'?'Text':mode==='select'?'Select':'Pan',icon:icons[action!]});
        modePanels.get(figure)?.close(true);
        const EventType=document.defaultView?.CustomEvent;if(EventType)for(const plot of [figure,...Array.from(figure.querySelectorAll<HTMLElement>('[data-av-plot]'))])if(plot.hasAttribute('data-av-plot'))plot.dispatchEvent(new EventType('av-layout-invalidated'));return true;
      }
      if(action==='expand'){expand(figure,control);return true;}
      if(action==='source'){
        try{const reader=sourceReader(figure);if(!reader)throw new Error('Original source is unavailable.');reader.open(control);}
        catch(error){notify({text:error instanceof Error?error.message:'The source reader could not open.',tone:'error',source:figure});}
        return true;
      }
      if(control.disabled)return true;control.disabled=true;control.setAttribute('aria-busy','true');
      const operation=(async()=>{
        const name=(figureTitle(figure).replace(/[^a-z0-9_-]+/gi,'-').slice(0,80)||'visualization');
        if(action==='copy')await copyFigureImage(figure);
        else if(action==='copy-source')await copyFigureSource(figure);
        else if(action==='download-source'){const source=figureSource(figure);if(!source)throw new Error('Original source is unavailable.');downloadBlob(document,new Blob([source.text],{type:'text/plain;charset=utf-8'}),source.filename||name+'.txt');}
        else if(action==='svg'){const svg=await exportFigureSvg(figure);if(!stopped)downloadBlob(document,new Blob([svg],{type:'image/svg+xml'}),name+'.svg');}
        else {const png=await exportFigurePng(figure);if(!stopped)downloadBlob(document,png,name+'.png');}
        if(!stopped)notify({text:action?.startsWith('copy')?(action==='copy-source'?'Source copied.':'Image copied.'):'Download prepared.',tone:'success',source:sourceReaders.get(figure)?.panel.hasAttribute('open')?sourceReaders.get(figure)!.panel:figure});
      })().catch(error=>{if(!stopped)notify({text:(error instanceof Error?error.message:'Export could not complete.')+(action?.startsWith('copy')?' Use a download or view the source.':''),tone:'error',source:sourceReaders.get(figure)?.panel.hasAttribute('open')?sourceReaders.get(figure)!.panel:figure});}).finally(()=>{control.disabled=false;control.removeAttribute('aria-busy');});
      jobs.add(operation);void operation.then(()=>jobs.delete(operation));return true;
    },
    async whenIdle(){while(jobs.size)await Promise.all([...jobs]);},cleanup(){stopped=true;for(const panel of modePanels.values())panel.cleanup();modePanels.clear();modeTriggers.clear();for(const reader of sourceReaders.values())reader.cleanup();sourceReaders.clear();for(const bar of commands.values())bar.cleanup();for(const restore of undo.reverse())restore();owners.clear();bars.clear();commands.clear();expansions.clear();modesByFigure.clear();}
  };
}
