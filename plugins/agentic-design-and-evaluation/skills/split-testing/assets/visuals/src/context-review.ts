import { exactJson } from './exact-json';
import { anchorLabel, anchorContext, anchorEvidence, readerDate } from './review-presentation';
import { selectedFigureItems } from './item-selection';
import { visibleViewport } from "./overlay-layout";
import { focusCommand } from './command-bar';
import { NotificationMessage } from './notifications';
import { fingerprint } from './identity';
import { ReaderNotebook } from './reader-state';
import { ReviewAnchor, TargetRegistry } from './review-targets';
import { AnnotationVersion, ReviewChange } from './review-state';
export interface ContextReviewHooks {
  notify?(message:NotificationMessage):void;
  notebook(): ReaderNotebook;
  change(change: ReviewChange): boolean;
  reveal(element: HTMLElement): void;
  now(): string;
  id(): string;
  status?(): string;
  controls?(element:HTMLElement):HTMLElement|null;
}
export interface ContextReviewController { reveal(anchor: ReviewAnchor): void; edit(versionId: string, trigger: HTMLElement): void; open(anchor: ReviewAnchor, from: HTMLElement): void; click(target: Element): boolean; change(target: Element): boolean; exportNotebook(value: ReaderNotebook): ReaderNotebook; input(target: Element): boolean; render(lists: HTMLElement[], bookmarkLists?: HTMLElement[], inclusionLists?: HTMLElement[]): void; cleanup(): void }
export function attachContextReview(scope: HTMLElement, registry: TargetRegistry, hooks: ContextReviewHooks): ContextReviewController {
  const document=scope.ownerDocument,view=document.defaultView,buttons=new Map<Element,{element:HTMLElement;action:string}>(),undo:(()=>void)[]=[],generatedActions=new WeakSet<Element>();
  const excluded=new Set<string>(), choices=new WeakMap<Element,string>(), anchorActions=new WeakMap<Element,ReviewAnchor>();
  let editor:HTMLElement|null=null,textarea:HTMLTextAreaElement|null=null,context:HTMLElement|null=null,notice:HTMLElement|null=null,current:ReviewAnchor|null=null,annotationId='',observed:string[]=[],trigger:HTMLElement|null=null,selected:ReviewAnchor|null=null,stopped=false,dirty=false;
  let returnControl: HTMLElement | null = null;
  // Reconcile immutable record versions, not the live reader's disclosures and
  // focus. Saving status and unrelated activity must not rebuild a collection.
  const rendered=new WeakMap<HTMLElement,Map<string,{signature:string;node:HTMLElement}>>();
  function reconcile(list:HTMLElement,entries:HTMLElement[],attribute:string):void{
    const wanted=new Set(entries),focus=document.activeElement as HTMLElement|null;
    for(const node of Array.from(list.querySelectorAll<HTMLElement>('['+attribute+']')))if(!wanted.has(node))node.remove();
    for(const node of Array.from(list.children))if(node.classList.contains('av-empty'))node.remove();
    const preceding=Array.from(list.children).filter(node=>!node.hasAttribute(attribute));
    [...preceding,...entries].forEach((node,index)=>{if(list.children[index]!==node)list.insertBefore(node,list.children[index]||null);});
    if(focus?.isConnected&&document.activeElement!==focus&&list.contains(focus))focus.focus({preventScroll:true});
  }
  const control=(parent:HTMLElement,action:string,text:string)=>{const button=document.createElement('button');button.type='button';button.className='av-button av-button-quiet';button.textContent=text;button.setAttribute('data-av-review-action',action);parent.appendChild(button);generatedActions.add(button);return button;};
  for(const {element}of registry.targets.values()){
    if(element===scope||!element.matches('.av-card,[data-av-figure]'))continue;
    const holder=document.createElement('span');holder.className='av-review-actions';holder.setAttribute('data-av-review-ui','');
    const note=control(holder,'new-note','Note'),bookmark=control(holder,'bookmark','Bookmark');note.title='Add a note on this content or selected text';bookmark.setAttribute('aria-pressed','false');
    for(const [button,action]of [[note,'new-note'],[bookmark,'bookmark']] as const)buttons.set(button,{element,action});
    const header=hooks.controls?.(element)||element.querySelector<HTMLElement>('.av-frame-tools,.av-plot-toolbar,figcaption')||element;
    if(header===element)element.insertBefore(holder,element.firstChild);else header.appendChild(holder);
    const preserve=(event:Event)=>event.preventDefault();for(const button of [note,bookmark])button.addEventListener('mousedown',preserve);undo.push(()=>{for(const button of [note,bookmark])button.removeEventListener('mousedown',preserve);holder.remove();});
  }
  const highlighted=new Map<HTMLElement,boolean>(); let highlightTimer: ReturnType<typeof setTimeout> | null = null;
  function clearHighlight(): void { if(highlightTimer!==null)clearTimeout(highlightTimer);highlightTimer=null;for(const[element,original]of highlighted)element.classList.toggle('av-review-target',original);highlighted.clear(); }
  function reveal(anchor:ReviewAnchor):void{
    const resolved=registry.resolve(anchor);if(resolved.status!=='resolved'||!resolved.element)return;
    clearHighlight();for(const menu of Array.from(scope.querySelectorAll('[data-av-notebook][open]')))menu.removeAttribute('open');
    hooks.reveal(resolved.element);
    if(resolved.range){const selection=view?.getSelection?.();selection?.removeAllRanges();selection?.addRange(resolved.range);}
    else {for(const element of resolved.elements || [resolved.element]){highlighted.set(element,element.classList.contains('av-review-target'));element.classList.add('av-review-target');}highlightTimer=setTimeout(clearHighlight,5000);}
  }
  function selection():void{const active=view?.getSelection?.();const anchor=active&&registry.selection(active);if(anchor)selected=anchor;else if(!editor?.contains(document.activeElement))selected=null;}
  document.addEventListener('selectionchange',selection);undo.push(()=>document.removeEventListener('selectionchange',selection));
  function returnFocus(): void { focusCommand(trigger?.isConnected ? trigger : returnControl?.isConnected ? returnControl : null); }
  function hideEditor(): void { if (editor) { if (typeof editor.hidePopover === 'function' && editor.hasAttribute('popover')) { try { editor.hidePopover(); } catch { /* Already hidden. */ } } editor.hidden = true; } }
  function placeEditor(): void {
    if (!editor || editor.hidden || stopped) return;
    const bounds = visibleViewport(view, 12);
    editor.style.setProperty('max-width', Math.max(0, bounds.right - bounds.left) + 'px');
    editor.style.setProperty('max-height', Math.max(0, bounds.bottom - bounds.top) + 'px');
    const rect = editor.getBoundingClientRect();
    editor.style.setProperty('inset-inline-end', 'auto'); editor.style.setProperty('bottom', 'auto');
    editor.style.setProperty('left', Math.max(bounds.left, bounds.right - rect.width) + 'px');
    editor.style.setProperty('top', Math.max(bounds.top, bounds.bottom - rect.height) + 'px');
  }
  function closeEditor(restoreFocus = true): void {
    if (dirty) save(true);
    if (dirty) { if (notice) notice.textContent = 'This draft could not be kept. Keep the editor open and copy your text before leaving.'; return; }
    hideEditor();
    current = null; selected = null; if (restoreFocus) returnFocus();
  }
  function ensureEditor(parent: HTMLElement): void {
    if (!editor) {
      editor = document.createElement('aside'); editor.className = 'av-context-review';
      editor.setAttribute('data-av-review-ui', ''); editor.setAttribute('role', 'region'); editor.setAttribute('aria-label', 'Annotation editor');
      const header = document.createElement('header'); header.className = 'av-context-review-header'; editor.appendChild(header);
      const heading = document.createElement('h3'); heading.textContent = 'Your note'; header.appendChild(heading);
      control(header, 'cancel', 'Close');
      const body = document.createElement('div'); body.className = 'av-context-review-body'; editor.appendChild(body);
      context = document.createElement('blockquote'); body.appendChild(context);
      textarea = document.createElement('textarea'); textarea.rows = 6; textarea.setAttribute('aria-label', 'Annotation text'); body.appendChild(textarea);
      const footer = document.createElement('footer'); footer.className = 'av-context-review-footer'; editor.appendChild(footer);
      const tools = document.createElement('div'); tools.className = 'av-button-group'; footer.appendChild(tools);
      for (const [action, label] of [['save', 'Save note'], ['draft', 'Keep draft'], ['delete', 'Remove note']]) control(tools, action, label);
      tools.querySelector('[data-av-review-action="save"]')?.classList.add('av-button-primary');
      notice = document.createElement('p'); notice.setAttribute('role', 'status'); footer.appendChild(notice);
      const keydown = (event: KeyboardEvent): void => {
        if (event.isComposing) return;
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeEditor(); }
        else if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); event.stopPropagation(); save(false, false, true); }
      };
      editor.addEventListener('keydown', keydown);
      if (typeof editor.showPopover === 'function') editor.setAttribute('popover', 'manual');
      if (view?.ResizeObserver) { const observer = new view.ResizeObserver(placeEditor); observer.observe(editor); undo.push(() => observer.disconnect()); }
      const closeContext = (event: Event): void => { if (editor && !editor.hidden && (event.target as Node | null)?.nodeType === 1 && (event.target as Element).tagName.toLowerCase() === 'dialog' && (event.target as Element).contains(editor)) closeEditor(false); };
      document.addEventListener('close', closeContext, true);
      undo.push(() => { document.removeEventListener('close', closeContext, true); editor!.removeEventListener('keydown', keydown); hideEditor(); editor!.remove(); });
      for (const surface of [view, view?.visualViewport]) if (surface) for (const type of ['resize', 'scroll']) { surface.addEventListener(type, placeEditor); undo.push(() => surface.removeEventListener(type, placeEditor)); }
    }
    parent.appendChild(editor); editor.hidden = false;
    if (editor.hasAttribute('popover')) { try { editor.showPopover(); } catch { editor.removeAttribute('popover'); } }
  }
  function open(anchor:ReviewAnchor,from:HTMLElement,version?:AnnotationVersion):void{
    if(current&&dirty){save(true);if(dirty)return;}
    current=anchor;dirty=false;trigger=from;returnControl=from.closest<HTMLElement>('[data-av-notebook]')?.querySelector<HTMLElement>('summary')||registry.targets.get(anchor.target.id)?.element.querySelector<HTMLElement>('summary')||null;annotationId=version?.annotationId||hooks.id();observed=version?[...(version.draft?version.baseIds||[]:[]),version.id]:[];
    from.closest<HTMLElement>('[data-av-notebook]')?.removeAttribute('open');
    ensureEditor(from.closest<HTMLElement>('dialog')||scope);context!.textContent=anchor.target.path.concat(anchor.target.label).join(' / ')+(anchor.kind==='text'?'\n“'+anchor.quote+'”':anchor.kind==='item'?'\n'+anchor.label+'\n'+anchor.text:anchor.kind==='items'?'\n'+anchor.items.map(item=>item.label+'\n'+item.text).join('\n\n'):'');textarea!.value=version?.text||'';notice!.textContent=registry.resolve(anchor).message;placeEditor();textarea!.focus({preventScroll:true});
  }
  function save(draft:boolean,deleted=false,announce=false):boolean{
    if(!current||!textarea)return false;
    if(draft&&!dirty){if(announce&&!observed.length){notice!.textContent='Write a note to keep a draft.';return true;}if(announce)hooks.notify?.({text:'Draft kept.',tone:'success',source:editor||scope});return true;}
    const version:AnnotationVersion={id:hooks.id(),annotationId,anchor:current,text:deleted?null:textarea.value,at:hooks.now(),draft,...(draft?{baseIds:observed.filter(id=>hooks.notebook().review?.versions.some(item=>item.id===id&&!item.draft))}:{})};
    if(!deleted&&!draft&&!version.text?.trim()){notice!.textContent='Enter a note before saving.';return true;}
    if(hooks.change({type:'annotation',version,observedIds:observed})){if(announce)hooks.notify?.({text:deleted?'Note removed.':draft?'Draft kept.':'Note added to this report.',tone:'success',source:registry.resolve(current).element||scope});dirty=false;observed=[...(draft?version.baseIds||[]:[]),version.id];notice!.textContent=hooks.status?.()||(draft?'Draft retained.':'Note retained.');if(!draft){hideEditor();current=null;textarea.value='';returnFocus();}}return true;
  }
  return{
    open, reveal,
    edit(versionId, trigger) { const version=hooks.notebook().review?.versions.find(value=>value.id===versionId);if(version)open(version.anchor,trigger,version); },
    click(target){
      const control=target.closest<HTMLElement>('[data-av-review-action]');
      if(!control){const item=registry.item(target);if(item)selected=item;return false;}
      const owned=buttons.get(control);
      if(owned){
        const base=registry.anchor(owned.element), native=view?.getSelection?.(), text=native&&registry.selection(native);
        const textOwner=text&&registry.targets.get(text.target.id)?.element;
        const passage=textOwner&&(owned.element.contains(textOwner)||textOwner.contains(owned.element))?text:null;
        const start=native?.anchorNode?.nodeType===1?native.anchorNode as Element:native?.anchorNode?.parentElement;
        const end=native?.focusNode?.nodeType===1?native.focusNode as Element:native?.focusNode?.parentElement;
        if(native&&!native.isCollapsed&&!passage&&((start&&owned.element.contains(start))||(end&&owned.element.contains(end)))){
          hooks.notify?.({text:'This passage crosses evidence that cannot be attached precisely. Select text inside one record, or clear the selection before annotating the whole figure or section.',tone:'error',source:owned.element});return true;
        }
        const textMode=owned.element.getAttribute('data-av-selection-mode')==='text';
        const items=owned.element.hasAttribute('data-av-figure')&&!textMode?registry.items(selectedFigureItems(owned.element)):null;
        const retained=selected&&(!textMode||selected.kind==='text')&&registry.targets.get(selected.target.id)?.element===owned.element?selected:null;
        const anchor=passage||items||retained||base;
        if(owned.action==='bookmark'){
          const enabled=!(hooks.notebook().review?.bookmarks||[]).some(value=>exactJson(value)===exactJson(anchor));
          const applied=hooks.change({type:'review-bookmark',anchor,enabled});
          if(applied)hooks.notify?.({text:enabled?'Bookmark added.':'Bookmark removed.',tone:'success',source:owned.element});return true;
        }
        open(anchor,control);
        return true;
      }
      if(!generatedActions.has(control)&&!editor?.contains(control))return false;
      const bookmark=anchorActions.get(control);
      if(bookmark){
        if(control.getAttribute('data-av-review-action')==='remove-bookmark'){
          const notebook=control.closest<HTMLElement>('[data-av-notebook]');
          const cards=Array.from(notebook?.querySelectorAll<HTMLElement>('[data-av-review-bookmark]')||[]),card=control.closest<HTMLElement>('[data-av-review-bookmark]');
          const at=card?cards.indexOf(card):0;
          if(hooks.change({type:'review-bookmark',anchor:bookmark,enabled:false})){
            const remaining=Array.from(notebook?.querySelectorAll<HTMLElement>('[data-av-review-bookmark]')||[]);
            const next=remaining[Math.min(at,remaining.length-1)];
            (next?.querySelector<HTMLElement>('button:not([disabled])')||notebook?.querySelector<HTMLElement>('[data-av-notebook-tab="bookmarks"]'))?.focus({preventScroll:true});
            hooks.notify?.({text:'Bookmark removed.',tone:'success',source:scope});
          }
        }else if(control.getAttribute('data-av-review-action')==='note-bookmark')open(bookmark,control);else if(registry.resolve(bookmark).status==='resolved')reveal(bookmark);
        return true;
      }
      const action=control.getAttribute('data-av-review-action');
      if(action==='edit'||action==='resolve'){
        const version=hooks.notebook().review?.versions.find(value=>value.id===control.getAttribute('data-av-review-version'));if(version){if(action==='resolve'){const observedIds=hooks.notebook().review?.versions.filter(item=>item.annotationId===version.annotationId&&!item.draft).map(item=>item.id)||[];hooks.change({type:'annotation',version:{...version,id:hooks.id(),at:hooks.now(),draft:false},observedIds});}else open(version.anchor,control,version);}return true;
      }
      if(action==='reveal'){
        const version=hooks.notebook().review?.versions.find(value=>value.id===control.getAttribute('data-av-review-version'));if(version){const result=registry.resolve(version.anchor);if(result.status==='resolved')reveal(version.anchor);}return true;
      }
      if(!editor?.contains(control))return false;
      if(action==='save')return save(false,false,true);if(action==='draft')return save(true,false,true);if(action==='delete')return save(false,true,true);
      if(action==='cancel'){closeEditor();return true;}return false;
    },
    change(target){const key=choices.get(target);if(!key)return false;if((target as HTMLInputElement).checked)excluded.delete(key);else excluded.add(key);return true;},
    exportNotebook(value){const omitted=(key:string)=>excluded.has(key);const review=value.review||{versions:[],bookmarks:[]};return{...value,state:{...value.state,notes:value.state.notes.filter(note=>!omitted('legacy:'+note.targetId)),bookmarks:value.state.bookmarks.filter(id=>!omitted('bookmark:'+id)),activity:[],droppedActivityCount:0,nextSequence:1},noteVersions:value.noteVersions.filter(note=>!omitted('legacy:'+note.targetId)),review:{versions:review.versions.filter(note=>!omitted('annotation:'+note.annotationId)),bookmarks:review.bookmarks.filter(anchor=>!omitted('anchor:'+fingerprint(exactJson(anchor))))},originals:[],reviewImports:[]};},
    input(target){if(target!==textarea||!current)return false;dirty=true;save(true);return true;},
    render(lists,bookmarkLists=[],inclusionLists=[]){
      const make = <K extends keyof HTMLElementTagNameMap>(parent:HTMLElement,tag:K,text?:string,cls=''):HTMLElementTagNameMap[K]=>{const node=document.createElement(tag);node.className=cls;if(text!==undefined)node.textContent=text;parent.appendChild(node);return node;};
      const choice=(parent:HTMLElement,key:string,labelText:string)=>{const label=make(parent,'label',undefined,'av-review-include');const input=make(label,'input');input.type='checkbox';input.checked=!excluded.has(key);label.appendChild(document.createTextNode(labelText));choices.set(input,key);return label;};
      const includeNodes=new Map<HTMLElement,HTMLElement[]>();for(const list of inclusionLists)includeNodes.set(list,[]);
      const include=(key:string,label:string)=>{for(const list of inclusionLists){
        const cache=rendered.get(list)||new Map();rendered.set(list,cache);const signature=exactJson([label,!excluded.has(key)]),prior=cache.get(key);
        let node:HTMLElement;
        if(prior?.signature===signature)node=prior.node;else{const holder=document.createElement('div');node=choice(holder,key,label);node.setAttribute('data-av-inclusion-key',key);cache.set(key,{signature,node});}
        includeNodes.get(list)!.push(node);
      }};
      if(editor&&!editor.hidden&&notice)notice.textContent=hooks.status?.()||notice.textContent;
      const notebook=hooks.notebook(),versions=notebook.review?.versions||[],groups=new Map<string,AnnotationVersion[]>();
      const anchors=[...versions.map(version=>version.anchor),...(notebook.review?.bookmarks||[])];
      const resolvedBatch=registry.resolveAll?.(anchors)||anchors.map(anchor=>registry.resolve(anchor));
      const resolutions=new Map(anchors.map((anchor,index)=>[anchor,resolvedBatch[index]]));
      for(const version of versions){const group=groups.get(version.annotationId)||[];group.push(version);groups.set(version.annotationId,group);}
      const noteCounts = new Map<string,Set<string>>();
      for(const version of versions)if(version.text!==null){let ids=noteCounts.get(version.anchor.target.id);if(!ids){ids=new Set();noteCounts.set(version.anchor.target.id,ids);}ids.add(version.annotationId);}
      for(const[button,owned]of buttons){const target=registry.targets.get(owned.element.id)?.target;if(!target)continue;if(owned.action==='bookmark'){
        const bookmarks=(notebook.review?.bookmarks||[]).filter(value=>value.target.id===target.id);
        if(!bookmarks.length){button.setAttribute('aria-pressed','false');continue;}
        const picked=owned.element.hasAttribute('data-av-figure')&&owned.element.getAttribute('data-av-selection-mode')!=='text'?registry.items(selectedFigureItems(owned.element)):null;
        const anchor=picked||registry.anchor(owned.element),key=exactJson(anchor);
        button.setAttribute('aria-pressed',String(bookmarks.some(value=>exactJson(value)===key)));
      }else{const count=noteCounts.get(target.id)?.size||0;button.setAttribute('data-av-has-notes',String(count>0));button.setAttribute('aria-label',count?`${count} annotations on ${target.label}; add another`:`Add a note on ${target.label}`);}}
      function original(parent:HTMLElement,anchor:ReviewAnchor):void{
        const details=make(parent,'details',undefined,'av-review-original');make(details,'summary','Original evidence');make(details,'pre',anchorEvidence(anchor),'av-notebook-note');
        if(anchor.target.sources?.length)for(const source of anchor.target.sources)make(details,'p',source.label+' — '+source.href,'av-muted');
      }
      function heading(parent:HTMLElement,anchor:ReviewAnchor):void{make(parent,'h4',anchorLabel(anchor));const path=anchorContext(anchor);if(path)make(parent,'p',path,'av-review-location');}
      for(const note of notebook.state.notes)include('legacy:'+note.targetId,'Earlier note · '+(registry.targets.get(note.targetId)?.target.label||note.targetId));
      for(const[id,group]of groups){const live=group.filter(version=>version.text!==null||group.length>1);if(live.length)include('annotation:'+id,`Note · ${anchorLabel(live[0].anchor)}${live.some(v=>v.draft)?' (includes draft)':''}`);}
      for(const list of lists){
        const cache=rendered.get(list)||new Map(),wanted:HTMLElement[]=[],keep=new Set<string>();rendered.set(list,cache);
        for(const[id,group]of groups)for(const version of group){
          if(version.text===null&&group.length===1)continue;
          const resolved=resolutions.get(version.anchor)!,competing=group.filter(item=>item.draft===version.draft).length>1;
          const key=version.id,signature=exactJson([version,competing,resolved.status,resolved.message]),prior=cache.get(key);keep.add(key);
          if(prior?.signature===signature){wanted.push(prior.node);continue;}
          const item=document.createElement('li');item.className='av-review-card';item.setAttribute('data-av-review-entry',id);item.setAttribute('data-av-note-version',version.id);item.setAttribute('data-av-entry-state',resolved.status!=='resolved'||competing?'attention':version.draft?'draft':'saved');heading(item,version.anchor);
          const meta=make(item,'div',undefined,'av-review-meta');const time=make(meta,'time',readerDate(version.at));time.setAttribute('datetime',version.at);time.title=version.at;
          if(version.draft)make(meta,'span','Draft','av-review-badge');if(competing)make(meta,'span','Competing version','av-review-badge');
          if(resolved.status!=='resolved')make(item,'p','Unresolved · '+resolved.message,'av-review-warning');
          make(item,'pre',version.text===null?'[Removed in this version]':version.text||'[Empty draft]','av-notebook-note');original(item,version.anchor);
          const actions=make(item,'div',undefined,'av-review-card-actions');const go=control(actions,'reveal','Go to evidence');go.setAttribute('data-av-review-version',version.id);go.disabled=resolved.status!=='resolved';
          const edit=control(actions,'edit',version.draft?'Continue draft':'Edit note');edit.setAttribute('data-av-review-version',version.id);
          if(!version.draft&&competing){const keep=control(actions,'resolve','Keep this version');keep.setAttribute('data-av-review-version',version.id);}
          cache.set(key,{signature,node:item});wanted.push(item);
        }
        for(const key of cache.keys())if(!keep.has(key))cache.delete(key);
        reconcile(list,wanted,'data-av-review-entry');
        if(!list.children.length)make(list,'li','No notes yet. Select evidence or use Add a note.','av-empty');
      }
      for(const id of notebook.state.bookmarks)include('bookmark:'+id,'Earlier bookmark · '+(registry.targets.get(id)?.target.label||id));
      for(const anchor of notebook.review?.bookmarks||[])include('anchor:'+fingerprint(exactJson(anchor)),'Bookmark · '+anchorLabel(anchor));
      for(const list of bookmarkLists){
        const cache=rendered.get(list)||new Map(),wanted:HTMLElement[]=[],keep=new Set<string>();rendered.set(list,cache);
        for(const anchor of notebook.review?.bookmarks||[]){
          const key=fingerprint(exactJson(anchor)),resolved=resolutions.get(anchor)!,signature=exactJson([resolved.status,resolved.message]),prior=cache.get(key);keep.add(key);
          if(prior?.signature===signature){wanted.push(prior.node);continue;}
          const item=document.createElement('li');item.className='av-review-card';item.setAttribute('data-av-review-bookmark',key);heading(item,anchor);
          item.setAttribute('data-av-entry-state',resolved.status==='resolved'?'saved':'attention');
          if(resolved.status!=='resolved')make(item,'p','Unresolved · '+resolved.message,'av-review-warning');
          if(anchor.kind==='text')make(item,'blockquote',anchor.quote,'av-review-quote');else if(anchor.kind==='items')make(item,'p',anchor.items.map(item=>item.label).join(' · '),'av-muted');
          original(item,anchor);const actions=make(item,'div',undefined,'av-review-card-actions');
          for(const[action,label]of [['reveal-bookmark','Go to evidence'],['note-bookmark','Add a note'],['remove-bookmark','Remove']]){const button=control(actions,action,label);anchorActions.set(button,anchor);if(action==='reveal-bookmark')button.disabled=resolved.status!=='resolved';}
          cache.set(key,{signature,node:item});wanted.push(item);
        }
        for(const key of cache.keys())if(!keep.has(key))cache.delete(key);
        reconcile(list,wanted,'data-av-review-bookmark');
        if(!list.children.length)make(list,'li','No bookmarks yet. Bookmark a section, figure, passage or selection to return to it.','av-empty');
      }
      for(const [list,nodes]of includeNodes){
        reconcile(list,nodes,'data-av-inclusion-key');const cache=rendered.get(list),keys=new Set(nodes.map(node=>node.getAttribute('data-av-inclusion-key')));if(cache)for(const key of cache.keys())if(!keys.has(key))cache.delete(key);
        if(!list.children.length)make(list,'p','No notes or bookmarks to include yet.','av-empty');
      }
    },cleanup(){if(stopped)return;stopped=true;if(current&&dirty)save(true);for(const restore of undo.reverse())restore();clearHighlight();buttons.clear();}
  };
}
