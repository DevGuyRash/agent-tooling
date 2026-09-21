import { attachFloatingPanel, FloatingPanel } from './floating-panel';
import { figureOf, figureOrigin } from './figures';
import { CommandOptions, commandIcon, focusCommand } from './command-bar';

export const selectableItems = '[data-av-inspect],[data-av-observation],[data-av-mermaid-item]';
export interface ItemSelectionState { keys: string[]; pivot: string | null }
/** Source order, not a new analytical ordering. Shift replaces a range; an
 * additive modifier unions it. A toggle retains its pivot after deselection. */
export function changeItemSelection(state: ItemSelectionState, order: readonly string[], key: string, toggle = false, range = false): ItemSelectionState {
  if (!order.includes(key)) return state;
  let keys: Set<string>;
  const start = state.pivot === null ? -1 : order.indexOf(state.pivot), end = order.indexOf(key);
  if (range && start >= 0) {
    keys = new Set(toggle ? state.keys : []);
    for (const id of order.slice(Math.min(start,end), Math.max(start,end)+1)) keys.add(id);
  } else if (toggle) { keys = new Set(state.keys); if (keys.has(key)) keys.delete(key); else keys.add(key); }
  else keys = new Set([key]);
  return {keys:order.filter(id => keys.has(id)), pivot:range && start >= 0 ? state.pivot : key};
}
export const selectedFigureItems = (figure: HTMLElement): HTMLElement[] => Array.from(figure.querySelectorAll<HTMLElement>('[data-av-item-selected]')).filter(node => figureOf(node) === figure && !node.closest('[data-av-review-ui]'));
export interface ItemSelectionHooks {
  inspect(item: HTMLElement, open?: boolean, trigger?: HTMLElement): void;
  review(figure: HTMLElement, action: 'note' | 'bookmark', trigger: HTMLElement): void;
  canReview(figure: HTMLElement): boolean;
  command?(figure: HTMLElement, control: HTMLButtonElement, options: CommandOptions): void;
  updateCommand?(figure: HTMLElement, control: HTMLButtonElement, options: Partial<CommandOptions>): void;
}
export interface ItemSelectionController {
  click(event: MouseEvent, target: Element): boolean;
  keydown(event: KeyboardEvent, target: Element): boolean;
  refresh(figure?: HTMLElement): void;
  cleanup(): void;
}
interface ItemState {
  figure: HTMLElement; selection: ItemSelectionState; additive: boolean; active: string | null;
  marks: Map<string, HTMLElement>; restore: Map<HTMLElement, () => void>; source: string;
  trigger: HTMLButtonElement; panel: FloatingPanel; bar: HTMLElement; status: HTMLOutputElement; buttons: Map<string, HTMLButtonElement>;
}
const icons: Record<string,string> = {
  inspect:'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14m5 12 6 6',
  note:'M4 3h16v14l-5 4H4zM8 8h8M8 12h6',
  bookmark:'M6 3h12v18l-6-4-6 4z', clear:'m6 6 12 12M6 18 18 6', add:'M12 4v16M4 12h16'
};
export function attachItemSelection(root: HTMLElement, figures: readonly HTMLElement[], hooks: ItemSelectionHooks): ItemSelectionController {
  const document = root.ownerDocument, view = document.defaultView, states = new Map<HTMLElement, ItemState>(), undo: (()=>void)[] = [];
  let stopped = false;
  const keyOf = (node: Element): string | null => node.getAttribute('data-av-inspect') || node.getAttribute('data-av-observation') || node.getAttribute('data-av-mermaid-item');
  const sourceOf = (figure: HTMLElement): string => figure.getAttribute('data-av-source') || figure.querySelector('[data-av-mermaid-source]')?.getAttribute('data-av-mermaid-source') || figureOrigin(figure).owner?.getAttribute('data-av-layout-input') || '';
  const modeOf = (figure: HTMLElement): string => figure.getAttribute('data-av-selection-mode') || 'pan';
  function hasText(state: ItemState): boolean {
    const selected = view?.getSelection?.();
    const parent = selected?.anchorNode?.nodeType === 1 ? selected.anchorNode as Element : selected?.anchorNode?.parentElement;
    const end = selected?.focusNode?.nodeType === 1 ? selected.focusNode as Element : selected?.focusNode?.parentElement;
    return !!selected && !selected.isCollapsed && !!parent && !!end && state.figure.contains(parent) && state.figure.contains(end) && !parent.closest('[data-av-review-ui],[data-av-controls]');
  }
  function paint(state: ItemState): void {
    const mode = modeOf(state.figure), selected = new Set(state.selection.keys), text = mode === 'text' && hasText(state);
    if (!state.active || !state.marks.has(state.active)) state.active = state.selection.keys[state.selection.keys.length - 1] || state.marks.keys().next().value || null;
    for (const [key, mark] of state.marks) {
      if (selected.has(key)) mark.setAttribute('data-av-item-selected',''); else mark.removeAttribute('data-av-item-selected');
      mark.setAttribute('aria-pressed', String(selected.has(key)));
      mark.setAttribute('tabindex', mode === 'select' && key === state.active ? '0' : '-1');
      // Do not overwrite any renderer-owned filter, fill, or semantic stroke.
    }
    const count = state.selection.keys.length;
    state.trigger.hidden = mode === 'text' ? !text : !count;
    const caption = mode === 'text' ? 'Passage' : `${count} selected`;
    if (hooks.updateCommand) hooks.updateCommand(state.figure,state.trigger,{label:caption});
    else state.trigger.textContent = caption;
    if (state.trigger.hidden) state.panel.close(false);
    const message = mode === 'text' ? (text ? 'Passage selected' : 'Select a passage') : count ? `${count} ${count === 1 ? 'item' : 'items'} selected` : 'No items selected';
    if (state.status.textContent !== message) state.status.textContent = message;
    for (const [action, button] of state.buttons) {
      button.hidden = (action === 'add' && mode !== 'select') || (action === 'inspect' && mode === 'text');
      if (action === 'add') button.setAttribute('aria-pressed', String(state.additive));
      else button.disabled = action === 'clear' ? !count && !text : action === 'inspect' ? !count : (mode === 'text' ? !text : !count) || !hooks.canReview(state.figure);
      if (action === 'note' || action === 'bookmark') button.title = hooks.canReview(state.figure) ? (action === 'note' ? 'Annotate the exact selection' : 'Bookmark the exact selection') : 'This report does not have a notebook';
    }
  }
  function refresh(figure?: HTMLElement): void {
    if (stopped) return;
    for (const state of states.values()) {
      if (figure && state.figure !== figure && !figure.contains(state.figure)) continue;
      const source = sourceOf(state.figure);
      if (source !== state.source) { state.selection = {keys:[],pivot:null}; state.source = source; }
      const groups = new Map<string, HTMLElement[]>();
      for (const mark of Array.from(state.figure.querySelectorAll<HTMLElement>(selectableItems))) {
        const key = keyOf(mark); if (!key || figureOf(mark) !== state.figure || mark.closest('[data-av-review-ui]')) continue;
        const group = groups.get(key) || []; group.push(mark); groups.set(key,group);
      }
      state.marks = new Map([...groups].filter(([,group]) => group.length === 1).map(([key,group]) => [key,group[0]]));
      const current = new Set(state.marks.values());
      for (const [mark, restore] of state.restore) if (!current.has(mark)) { restore(); state.restore.delete(mark); }
      const added=[...current].filter(mark=>!state.restore.has(mark));
      // Read the author/renderer filter before adding selection chrome. Batch
      // reads before writes; selection must not erase a meaningful paint filter.
      const baseFilters=new Map(added.map(mark=>[mark,view?.getComputedStyle?.(mark).filter||'none']));
      for (const mark of added) {
        const attributes = ['tabindex','aria-pressed','data-av-item-selected'].map(name => [name,mark.getAttribute(name)] as const);
        const properties=['--av-item-base-filter','--av-item-filter-chain'].map(name=>[name,mark.style.getPropertyValue(name),mark.style.getPropertyPriority?.(name)||''] as const);
        const base=baseFilters.get(mark)!;
        mark.style.setProperty('--av-item-base-filter',base);
        mark.style.setProperty('--av-item-filter-chain',base==='none'?'opacity(1)':base);
        state.restore.set(mark, () => {
          for (const [name,value] of attributes) if (value === null) mark.removeAttribute(name); else mark.setAttribute(name,value);
          for(const[name,value,priority]of properties)if(value)mark.style.setProperty(name,value,priority);else mark.style.removeProperty(name);
        });
      }
      state.selection.keys = state.selection.keys.filter(key => state.marks.has(key));
      paint(state);
    }
  }
  for (const figure of figures) {
    const plot = figure.matches('[data-av-plot]') ? figure : figure.querySelector<HTMLElement>('[data-av-plot]');
    const toolbar = plot?.querySelector<HTMLElement>('.av-plot-toolbar');
    if (!plot || !toolbar) continue;
    const trigger=document.createElement('button');trigger.type='button';trigger.className='av-button av-selection-trigger';trigger.hidden=true;trigger.setAttribute('data-av-selection-menu','');toolbar.appendChild(trigger);
    const panel=attachFloatingPanel(trigger,figure,'Selected evidence');panel.element.classList.add('av-selection-panel');
    const bar=panel.body;bar.classList.add('av-item-selection');
    const status=document.createElement('output');status.setAttribute('role','status');status.setAttribute('aria-live','polite');bar.appendChild(status);
    const controls=document.createElement('div');controls.className='av-selection-actions';bar.appendChild(controls);
    const buttons=new Map<string,HTMLButtonElement>();
    for (const [action,label] of [['inspect','Inspect evidence'],['note','Add a note'],['bookmark','Bookmark selection'],['clear','Clear selection'],['add','Add to selection']]) {
      const button=document.createElement('button');button.type='button';button.className='av-button av-button-quiet';button.setAttribute('data-av-selection-command',action);
      button.appendChild(commandIcon(document,icons[action]));button.setAttribute('aria-label',label);const caption=document.createElement('span');caption.textContent=label;button.appendChild(caption);controls.appendChild(button);buttons.set(action,button);
    }
    const hint=document.createElement('p');hint.className='av-note';hint.textContent='Notes and bookmarks retain the exact selected evidence. Add to selection keeps earlier items when you tap another.';bar.appendChild(hint);
    const preserve=(event:Event)=>{if((event.target as Element)?.closest('button'))event.preventDefault();};
    bar.addEventListener('mousedown',preserve);trigger.addEventListener('mousedown',preserve);
    hooks.command?.(figure,trigger,{label:'Selection',labelled:true,priority:5,group:'selection',icon:icons.inspect});
    undo.push(()=>{panel.cleanup();bar.removeEventListener('mousedown',preserve);trigger.removeEventListener('mousedown',preserve);trigger.remove();});
    states.set(figure,{figure,selection:{keys:[],pivot:null},additive:false,active:null,marks:new Map(),restore:new Map(),source:sourceOf(figure),trigger,panel,bar,status,buttons});
  }
  function choose(state: ItemState, key: string, toggle: boolean, range: boolean): void {
    state.selection = changeItemSelection(state.selection,[...state.marks.keys()],key,toggle,range); state.active = key;
    paint(state);
    const inspected = state.marks.get(state.selection.keys.includes(key) ? key : state.selection.keys[state.selection.keys.length - 1] || '');
    if (inspected) hooks.inspect(inspected);
  }
  const invalidated = (event: Event) => { const figure = figureOf(event.target as Element); if (figure) refresh(figure); };
  root.addEventListener('av-layout-invalidated',invalidated,true); undo.push(() => root.removeEventListener('av-layout-invalidated',invalidated,true));
  const textChanged = () => { for (const state of states.values()) if (modeOf(state.figure) === 'text') paint(state); };
  document.addEventListener('selectionchange',textChanged); undo.push(() => document.removeEventListener('selectionchange',textChanged));
  refresh();
  return {
    refresh,
    click(event,target) {
      if (stopped) return false;
      const figure = figureOf(target), state = figure && states.get(figure); if (!state) return false;
      const command = target.closest<HTMLElement>('[data-av-selection-command]');
      if (command && state.bar.contains(command)) {
        const action = command.getAttribute('data-av-selection-command');
        if ((command as HTMLButtonElement).disabled) return true;
        if (action === 'clear') { state.selection = {keys:[],pivot:null}; if (hasText(state)) view?.getSelection?.()?.removeAllRanges(); paint(state); focusCommand(state.figure.querySelector<HTMLElement>('[data-av-mode-menu]') || state.figure.querySelector<HTMLElement>('.av-plot-scroll')); }
        else if (action === 'add') { state.additive = !state.additive; paint(state); }
        else if (action === 'inspect') { const mark = state.marks.get(state.selection.keys.includes(state.active || '') ? state.active! : state.selection.keys[0]); if(mark) hooks.inspect(mark,true,state.trigger); }
        else if (action === 'note' || action === 'bookmark') hooks.review(state.figure,action,state.trigger);
        if (action !== 'add') state.panel.close(action === 'bookmark');
        return true;
      }
      if (!target.closest('.av-plot-scroll') || target.closest('a[href],button,input,textarea,select,[contenteditable]')) return false;
      const mode = modeOf(state.figure);
      if (mode === 'pan') return true; // a tap is not a selection in the hand tool
      if (mode === 'text') return false;
      const mark = target.closest<HTMLElement>(selectableItems), key = mark && keyOf(mark);
      if (key && state.marks.get(key) === mark) choose(state,key,event.ctrlKey || event.metaKey || state.additive,event.shiftKey);
      else if (!event.ctrlKey && !event.metaKey && !event.shiftKey && !state.additive) { state.selection = {keys:[],pivot:null}; paint(state); }
      return true;
    },
    keydown(event,target) {
      const figure = figureOf(target), state = figure && states.get(figure);
      if (!state || stopped || event.isComposing || event.altKey || modeOf(state.figure) !== 'select' || !target.closest('.av-plot-scroll') || target.closest('a[href],button,input,textarea,select,[contenteditable]')) return false;
      if (event.key === 'Escape' && state.selection.keys.length) { state.selection = {keys:[],pivot:null}; paint(state); return true; }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') { state.selection = {keys:[...state.marks.keys()],pivot:state.active}; paint(state); return true; }
      const order = [...state.marks.keys()], current = keyOf(target.closest(selectableItems) || target) || state.active;
      if (!current || !order.length) return false;
      if (event.key === 'Enter' || event.key === ' ') { choose(state,current,event.ctrlKey || event.metaKey || state.additive,event.shiftKey); return true; }
      if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)) return false;
      const index = Math.max(0,order.indexOf(current));
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? order.length-1 : Math.max(0,Math.min(order.length-1,index+(['ArrowLeft','ArrowUp'].includes(event.key)?-1:1)));
      state.active = order[next];
      if (event.shiftKey) { if (!state.selection.pivot) state.selection.pivot = current; choose(state,order[next],event.ctrlKey || event.metaKey || state.additive,true); }
      paint(state); state.marks.get(order[next])?.focus({preventScroll:true}); return true;
    },
    cleanup() { if(stopped)return; stopped = true; for (const state of states.values()) for (const restore of state.restore.values()) restore(); for (const restore of undo.reverse()) restore(); states.clear(); }
  };
}
