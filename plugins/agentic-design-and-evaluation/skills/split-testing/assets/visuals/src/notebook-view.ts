export type NotebookTab = 'notes' | 'bookmarks' | 'activity' | 'share';
export interface NotebookView { areas: Record<NotebookTab, HTMLElement>; footer: HTMLElement; locate(tab: NotebookTab): void; activate(tab: NotebookTab): void; refresh(): void; cleanup(): void }
/** Presentation only: all edits, recovery and concurrent versions stay with the
 * notebook controller. One live panel, four independently scrolled collections. */
export function createNotebookView(details: HTMLElement, content: HTMLElement): NotebookView {
  const document = content.ownerDocument, undo: (()=>void)[] = [], ids: NotebookTab[] = ['notes','bookmarks','activity','share'];
  const labels = {notes:'Notes',bookmarks:'Bookmarks',activity:'Activity',share:'Share'};
  const areas = {} as Record<NotebookTab,HTMLElement>, buttons = new Map<NotebookTab,HTMLButtonElement>();
  let active: NotebookTab = 'notes'; const scroll = new Map<NotebookTab,number>();
  const node = <K extends keyof HTMLElementTagNameMap>(tag: K, parent: HTMLElement, cls = '', text?: string): HTMLElementTagNameMap[K] => { const child = document.createElement(tag); child.className = cls; if(text!==undefined)child.textContent=text; parent.appendChild(child);return child; };
  const header = node('header',content,'av-notebook-header'); node('strong',header,'','Your notebook');
  const close = node('button',header,'av-button av-button-quiet','Close'); close.type='button'; close.setAttribute('aria-label','Close notebook');
  const closeClick = (event: Event) => {event.preventDefault();event.stopPropagation();details.removeAttribute('open');details.querySelector<HTMLElement>('summary')?.focus({preventScroll:true});}; close.addEventListener('click',closeClick);undo.push(()=>close.removeEventListener('click',closeClick));
  const tabs = node('div',content,'av-notebook-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Your notebook');
  const tools = node('div',content,'av-notebook-filterbar');
  const filter = node('input',tools,'');filter.type='search';filter.placeholder='Filter notes and bookmarks';filter.setAttribute('aria-label','Filter notes and bookmarks');
  const state = node('select',tools,'');state.setAttribute('aria-label','Filter by state');for(const [value,text] of [['all','All entries'],['draft','Drafts'],['attention','Needs attention']]){const option=node('option',state,'',text);option.value=value;}
  const body = node('div',content,'av-notebook-body');
  const empty = node('p',body,'av-empty','No entries match these filters.'); empty.hidden=true;
  for(const id of ids){
    const button=node('button',tabs,'',labels[id]);button.type='button';button.id=`${details.id}--${id}-tab`;button.setAttribute('role','tab');button.setAttribute('data-av-notebook-tab',id);buttons.set(id,button);
    const area=node('section',body,'av-notebook-page');area.id=`${details.id}--${id}-page`;area.setAttribute('role','tabpanel');area.setAttribute('aria-labelledby',button.id);button.setAttribute('aria-controls',area.id);areas[id]=area;
    const click=(event:Event)=>{event.preventDefault();event.stopPropagation();activate(id);};button.addEventListener('click',click);undo.push(()=>button.removeEventListener('click',click));
  }
  const footer=node('footer',content,'av-notebook-footer');
  function refresh():void{
    const query=filter.value.trim().toLocaleLowerCase();let count=0,matched=0;
    for(const id of ['notes','bookmarks'] as const){
      const entries=Array.from(areas[id].querySelectorAll<HTMLElement>('[data-av-review-entry],[data-av-review-bookmark],[data-av-legacy-note],[data-av-legacy-bookmark]'));
      const seen=new Set(entries.map(item=>item.getAttribute('data-av-review-entry')||item.getAttribute('data-av-review-bookmark')||'legacy:'+item.getAttribute('data-av-notebook-target-id')));
      buttons.get(id)!.textContent=labels[id]+(entries.length?` (${id==='notes'?seen.size:entries.length})`:'');
      for(const item of entries){const fits=(!query||(item.textContent||'').toLocaleLowerCase().includes(query))&&(state.value==='all'||item.getAttribute('data-av-entry-state')===state.value);item.hidden=!fits;if(active===id){count++;if(fits)matched++;}}
    }
    empty.hidden=!(count>0&&matched===0);tools.hidden=active!=='notes'&&active!=='bookmarks';
  }
  function activate(tab:NotebookTab):void{
    scroll.set(active,body.scrollTop);active=tab;
    for(const id of ids){const selected=id===tab;areas[id].hidden=!selected;buttons.get(id)!.setAttribute('aria-selected',String(selected));buttons.get(id)!.tabIndex=selected?0:-1;}
    refresh();body.scrollTop=scroll.get(tab)||0;
  }
  const onKey=(event:KeyboardEvent)=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();event.stopPropagation();const current=ids.indexOf(active);const next=event.key==='Home'?0:event.key==='End'?ids.length-1:(current+(event.key==='ArrowRight'?1:-1)+ids.length)%ids.length;activate(ids[next]);buttons.get(ids[next])!.focus({preventScroll:true});};
  tabs.addEventListener('keydown',onKey);filter.addEventListener('input',refresh);state.addEventListener('change',refresh);
  undo.push(()=>{tabs.removeEventListener('keydown',onKey);filter.removeEventListener('input',refresh);state.removeEventListener('change',refresh);});activate('notes');
  return {areas,footer,activate,locate(tab){filter.value='';state.value='all';activate(tab);},refresh,cleanup(){for(const fn of undo.reverse())fn();}};
}
