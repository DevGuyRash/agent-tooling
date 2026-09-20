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
export interface ContextReviewController { open(anchor: ReviewAnchor, from: HTMLElement): void; click(target: Element): boolean; change(target: Element): boolean; exportNotebook(value: ReaderNotebook): ReaderNotebook; input(target: Element): boolean; render(lists: HTMLElement[], bookmarkLists?: HTMLElement[]): void; cleanup(): void }
export function attachContextReview(scope: HTMLElement, registry: TargetRegistry, hooks: ContextReviewHooks): ContextReviewController {
  const document=scope.ownerDocument,view=document.defaultView,buttons=new Map<Element,{element:HTMLElement;action:string}>(),undo:(()=>void)[]=[],generatedActions=new WeakSet<Element>();
  const excluded=new Set<string>(), choices=new WeakMap<Element,string>(), anchorActions=new WeakMap<Element,ReviewAnchor>();
  let editor:HTMLElement|null=null,textarea:HTMLTextAreaElement|null=null,context:HTMLElement|null=null,notice:HTMLElement|null=null,current:ReviewAnchor|null=null,annotationId='',observed:string[]=[],trigger:HTMLElement|null=null,selected:ReviewAnchor|null=null,stopped=false,dirty=false;
  let returnControl: HTMLElement | null = null;
  const control=(parent:HTMLElement,action:string,text:string)=>{const button=document.createElement('button');button.type='button';button.className='av-button av-button-quiet';button.textContent=text;button.setAttribute('data-av-review-action',action);parent.appendChild(button);generatedActions.add(button);return button;};
  for(const {element}of registry.targets.values()){
    if(element===scope||!element.matches('.av-card,[data-av-figure]'))continue;
    const holder=document.createElement('span');holder.className='av-review-actions';holder.setAttribute('data-av-review-ui','');
    const note=control(holder,'new-note','Note'),bookmark=control(holder,'bookmark','Bookmark');note.title='Add a note on this content or selected text';bookmark.setAttribute('aria-pressed','false');
    for(const [button,action]of [[note,'new-note'],[bookmark,'bookmark']] as const)buttons.set(button,{element,action});
    const header=hooks.controls?.(element)||element.querySelector<HTMLElement>('.av-frame-tools,.av-plot-toolbar,figcaption')||element;
    if(header===element)element.insertBefore(holder,element.firstChild);else header.appendChild(holder);
    const preserve=(event:Event)=>event.preventDefault();note.addEventListener('mousedown',preserve);undo.push(()=>{note.removeEventListener('mousedown',preserve);holder.remove();});
  }
  const highlighted=new Map<HTMLElement,boolean>();
  function reveal(anchor:ReviewAnchor):void{const resolved=registry.resolve(anchor);if(resolved.status!=='resolved'||!resolved.element)return;hooks.reveal(resolved.element);if(resolved.range){const selection=view?.getSelection?.();selection?.removeAllRanges();selection?.addRange(resolved.range);}else{if(!highlighted.has(resolved.element))highlighted.set(resolved.element,resolved.element.classList.contains('av-review-target'));resolved.element.classList.add('av-review-target');}}
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
    ensureEditor(from.closest<HTMLElement>('dialog')||scope);context!.textContent=anchor.target.path.concat(anchor.target.label).join(' / ')+(anchor.kind==='text'?'\n“'+anchor.quote+'”':anchor.kind==='item'?'\n'+anchor.label+'\n'+anchor.text:'');textarea!.value=version?.text||'';notice!.textContent=registry.resolve(anchor).message;placeEditor();textarea!.focus({preventScroll:true});
  }
  function save(draft:boolean,deleted=false,announce=false):boolean{
    if(!current||!textarea)return false;
    if(draft&&!dirty){if(announce&&!observed.length){notice!.textContent='Write a note to keep a draft.';return true;}if(announce)hooks.notify?.({text:'Draft kept.',tone:'success',source:editor||scope});return true;}
    const version:AnnotationVersion={id:hooks.id(),annotationId,anchor:current,text:deleted?null:textarea.value,at:hooks.now(),draft,...(draft?{baseIds:observed.filter(id=>hooks.notebook().review?.versions.some(item=>item.id===id&&!item.draft))}:{})};
    if(!deleted&&!draft&&!version.text?.trim()){notice!.textContent='Enter a note before saving.';return true;}
    if(hooks.change({type:'annotation',version,observedIds:observed})){if(announce)hooks.notify?.({text:deleted?'Note removed.':draft?'Draft kept.':'Note added to this report.',tone:'success',source:registry.resolve(current).element||scope});dirty=false;observed=[...(draft?version.baseIds||[]:[]),version.id];notice!.textContent=hooks.status?.()||(draft?'Draft retained.':'Note retained.');if(!draft){hideEditor();current=null;textarea.value='';returnFocus();}}return true;
  }
  return{
    open,
    click(target){
      const control=target.closest<HTMLElement>('[data-av-review-action]');
      if(!control){const item=registry.item(target);if(item)selected=item;return false;}
      const owned=buttons.get(control);
      if(owned){const base=registry.anchor(owned.element);if(owned.action==='bookmark'){const enabled=!(hooks.notebook().review?.bookmarks||[]).some(value=>JSON.stringify(value)===JSON.stringify(base));const applied=hooks.change({type:'review-bookmark',anchor:base,enabled});if(applied)hooks.notify?.({text:enabled?'Bookmark added.':'Bookmark removed.',tone:'success',source:owned.element});return applied;}
        const fromSelection=view?.getSelection?.(),text=fromSelection&&registry.selection(fromSelection);const matchingText=text&&registry.targets.get(text.target.id)?.element;const relevantText=matchingText&&(owned.element.contains(matchingText)||matchingText.contains(owned.element))?text:null;const picked=relevantText||(selected&&registry.targets.get(selected.target.id)?.element===owned.element?selected:base);open(picked,control);if(fromSelection&&!fromSelection.isCollapsed&&!text)notice!.textContent='The selection crosses content that cannot be anchored precisely. This note is attached to the displayed section or figure.';return true;}
      if(!generatedActions.has(control)&&!editor?.contains(control))return false;
      const bookmark=anchorActions.get(control);
      if(bookmark){
        if(control.getAttribute('data-av-review-action')==='remove-bookmark'){
          const returnTo=control.closest<HTMLElement>('[data-av-notebook]')?.querySelector<HTMLElement>('summary');
          if(hooks.change({type:'review-bookmark',anchor:bookmark,enabled:false})){
            if(returnTo?.isConnected)returnTo.focus({preventScroll:true});
            hooks.notify?.({text:'Bookmark removed.',tone:'success',source:scope});
          }
        }else if(registry.resolve(bookmark).status==='resolved')reveal(bookmark);
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
    exportNotebook(value){const omitted=(key:string)=>excluded.has(key);const review=value.review||{versions:[],bookmarks:[]};return{...value,state:{...value.state,notes:value.state.notes.filter(note=>!omitted('legacy:'+note.targetId)),bookmarks:value.state.bookmarks.filter(id=>!omitted('bookmark:'+id)),activity:[],droppedActivityCount:0,nextSequence:1},noteVersions:value.noteVersions.filter(note=>!omitted('legacy:'+note.targetId)),review:{versions:review.versions.filter(note=>!omitted('annotation:'+note.annotationId)),bookmarks:review.bookmarks.filter(anchor=>!omitted('anchor:'+fingerprint(JSON.stringify(anchor))))},originals:excluded.size?[]:value.originals};},
    input(target){if(target!==textarea||!current)return false;dirty=true;save(true);return true;},
    render(lists,bookmarkLists=[]){
      const choice=(parent:HTMLElement,key:string)=>{const label=document.createElement('label');label.className='av-review-include';const input=document.createElement('input');input.type='checkbox';input.checked=!excluded.has(key);label.appendChild(input);label.appendChild(document.createTextNode('Include in review copy'));parent.appendChild(label);choices.set(input,key);};
      if(editor&&!editor.hidden&&notice)notice.textContent=hooks.status?.()||notice.textContent;
      const notebook=hooks.notebook(),versions=notebook.review?.versions||[],groups=new Map<string,AnnotationVersion[]>();
      for(const version of versions){const group=groups.get(version.annotationId)||[];group.push(version);groups.set(version.annotationId,group);}
      const noteCounts = new Map<string, Set<string>>();
      for (const version of versions) if (version.text !== null) {
        let ids = noteCounts.get(version.anchor.target.id);
        if (!ids) { ids = new Set(); noteCounts.set(version.anchor.target.id, ids); }
        ids.add(version.annotationId);
      }
      const bookmarked = new Map<string, ReviewAnchor[]>();
      for (const anchor of notebook.review?.bookmarks || []) {
        const group = bookmarked.get(anchor.target.id) || []; group.push(anchor); bookmarked.set(anchor.target.id, group);
      }
      for (const [button, owned] of buttons) {
        const id = owned.element.id, target = registry.targets.get(id)?.target;
        if (!target) continue;
        if (owned.action === 'bookmark') {
          const candidates = bookmarked.get(id);
          const active = !!candidates?.some(anchor => registry.resolve(anchor).status === 'resolved');
          button.setAttribute('aria-pressed', String(active));
        } else {
          const count = noteCounts.get(id)?.size || 0;
          button.setAttribute('data-av-has-notes', String(count > 0));
          button.setAttribute('aria-label', count ? `${count} annotations on ${target.label}; add another` : `Add a note on ${target.label}`);
        }
      }
      for(const list of lists){
        for(const legacy of Array.from(list.querySelectorAll<HTMLElement>('li'))){const target=legacy.querySelector('[data-av-notebook-action="edit-note"]')?.getAttribute('data-av-notebook-target-id');if(target&&!legacy.querySelector('.av-review-include'))choice(legacy,'legacy:'+target);}
        for(const node of Array.from(list.querySelectorAll('[data-av-review-entry]')))node.remove();
        if(!notebook.state.notes.length&&groups.size)list.textContent='';
        for(const[id,group]of groups)for(const version of group){if(version.text===null&&group.length===1)continue;const item=document.createElement('li');item.setAttribute('data-av-review-entry',id);const heading=document.createElement('p');heading.textContent=version.anchor.target.label+(version.draft?' · Draft':'')+(group.filter(item=>item.draft===version.draft).length>1?' · Competing version':'');item.appendChild(heading);if(version===group[0])choice(item,'annotation:'+id);const state=document.createElement('p');state.className='av-muted';const resolved=registry.resolve(version.anchor);state.textContent=resolved.message;item.appendChild(state);const body=document.createElement('pre');body.className='av-notebook-note';body.textContent=version.text===null?'[Removed in this version]':version.text||'[Empty draft]';item.appendChild(body);if(version.anchor.kind==='text'){const quote=document.createElement('blockquote');quote.textContent=version.anchor.quote;item.appendChild(quote);}const edit=control(item,'edit',version.draft?'Continue draft':'Edit note');if(!version.draft&&group.filter(value=>!value.draft).length>1){const keep=control(item,'resolve','Keep this version');keep.setAttribute('data-av-review-version',version.id);}edit.setAttribute('data-av-review-version',version.id);if(resolved.status==='resolved'){const go=control(item,'reveal','Go to content');go.setAttribute('data-av-review-version',version.id);}list.appendChild(item);}
        if(!list.children.length){const empty=document.createElement('li');empty.className='av-muted';empty.textContent='No saved notes yet.';list.appendChild(empty);}
      }
      for(const list of bookmarkLists){
        for(const node of Array.from(list.querySelectorAll('[data-av-review-bookmark]')))node.remove();
        for(const legacy of Array.from(list.querySelectorAll<HTMLElement>('li'))){const id=legacy.querySelector('[data-av-notebook-target-id]')?.getAttribute('data-av-notebook-target-id');if(id&&!legacy.querySelector('.av-review-include'))choice(legacy,'bookmark:'+id);}
        if(!notebook.state.bookmarks.length&&(notebook.review?.bookmarks.length||0)>0)list.textContent='';
        for(const anchor of notebook.review?.bookmarks||[]){
          const item=document.createElement('li');item.setAttribute('data-av-review-bookmark','');
          const resolved=registry.resolve(anchor), go=control(item,'reveal-bookmark',anchor.target.label);go.disabled=resolved.status!=='resolved';anchorActions.set(go,anchor);
          const state=document.createElement('p');state.className='av-muted';state.textContent=resolved.message;item.appendChild(state);
          choice(item,'anchor:'+fingerprint(JSON.stringify(anchor)));
          const remove=control(item,'remove-bookmark','Remove bookmark');anchorActions.set(remove,anchor);list.appendChild(item);
        }
        if(!list.children.length){const empty=document.createElement('li');empty.className='av-muted';empty.textContent='No bookmarks yet.';list.appendChild(empty);}
      }
    },cleanup(){if(stopped)return;stopped=true;if(current&&dirty)save(true);for(const restore of undo.reverse())restore();for(const[element,original]of highlighted)element.classList.toggle('av-review-target',original);buttons.clear();}
  };
}
