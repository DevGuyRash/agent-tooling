import { anchoredPanel, visibleViewport } from "./overlay-layout";
/** Move the original command nodes between a persistent strip and its overflow. */
export interface CommandOptions { label: string; priority?: number; group?: string; menuOnly?: boolean; width?: number; icon?: string; labelled?: boolean }
interface Command { control: HTMLButtonElement; options: CommandOptions; marker: Comment; original: Node[] }
export interface CommandBar { add(control: HTMLButtonElement, options: CommandOptions): void; update(control: HTMLButtonElement, options: Partial<CommandOptions>): void; refresh(): void; dismiss(returnFocus?: boolean): void; cleanup(): void }
export function commandGroups(width: number, entries: readonly {width:number;priority:number;group:string;menuOnly?:boolean}[], reserve=40, gap=4): Set<string> {
  const groups=new Map<string,{width:number;priority:number;index:number;menuOnly:boolean}>();
  entries.forEach((entry,index)=>{const group=groups.get(entry.group);if(group){group.width+=entry.width+gap;group.priority=Math.min(group.priority,entry.priority);group.menuOnly ||= !!entry.menuOnly;}else groups.set(entry.group,{width:entry.width,priority:entry.priority,index,menuOnly:!!entry.menuOnly});});
  const all=[...groups.values()];if(!all.some(group=>group.menuOnly)&&all.reduce((total,group)=>total+group.width,0)+Math.max(0,all.length-1)*gap<=width)return new Set(groups.keys());
  let used=reserve;const selected=new Set<string>();
  for(const[key,group]of [...groups].sort((a,b)=>a[1].priority-b[1].priority||a[1].index-b[1].index))if(!group.menuOnly&&used+group.width+gap<=width){selected.add(key);used+=group.width+gap;}
  return selected;
}
export function focusCommand(control:HTMLElement|null):void {if(!control)return;let target=control;for(let owner=control.parentElement;owner;owner=owner.parentElement)if(owner.tagName.toLowerCase()==='details'&&!owner.hasAttribute('open'))target=owner.querySelector<HTMLElement>('summary')||owner;target.focus({preventScroll:true});}
export function commandIcon(document:Document,path:string):SVGElement {
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');const shape=document.createElementNS(svg.namespaceURI,'path');shape.setAttribute('d',path);svg.appendChild(shape);return svg;
}
export function attachCommandBar(host: HTMLElement, label: string): CommandBar {
  const document=host.ownerDocument,view=document.defaultView,commands:Command[]=[],undo:(()=>void)[]=[];let stopped=false,refreshing=false,watching=false;
  const primary=document.createElement('div');primary.className='av-command-primary';const more=document.createElement('details');more.className='av-command-overflow';more.setAttribute('data-av-review-ui','');
  const summary=document.createElement('summary');summary.textContent='⋯';summary.setAttribute('aria-label',label);summary.setAttribute('aria-expanded','false');more.appendChild(summary);
  const menu=document.createElement('div');menu.className='av-command-menu';menu.setAttribute('role','group');menu.setAttribute('aria-label',label);more.appendChild(menu);host.appendChild(primary);host.appendChild(more);
  const preferredWidth=host.style.getPropertyValue('--av-command-preferred-width');
  let topLayer=typeof menu.showPopover==='function'&&typeof menu.hidePopover==='function',popoverOpen=false;
  if(topLayer){menu.setAttribute('popover','manual');menu.setAttribute('data-av-menu-layer','');}
  const previous=host.classList.contains('av-command-bar');host.classList.add('av-command-bar');
  function listen(node:EventTarget,type:string,fn:EventListener,capture=false):void{node.addEventListener(type,fn,capture);undo.push(()=>node.removeEventListener(type,fn,capture));}
  const outside = (event: Event): void => { if (more.open && !more.contains(event.target as Node)) dismiss(); };
  const choose = (event: Event): void => {
    const target = event.target as Node;
    if (more.open && !more.contains(target)) dismiss();
    else if (menu.contains(target)) {
      const element = target.nodeType === 1 ? target as Element : target.parentElement;
      const button = element?.closest('button');
      if (button) dismiss(button.getAttribute('data-av-review-action') !== 'new-note');
    }
  };
  // Closed figures add no document-level pointer or scroll listeners. This is
  // consequential in a full report with hundreds of independently owned bars.
  function watchOpen(): void {
    const next = more.open && !stopped;
    if (watching === next) return;
    watching = next;
    for (const [type, handler] of [['pointerdown', outside], ['click', choose], ['scroll', placeMenu]] as const) {
      if (watching) document.addEventListener(type, handler, true);
      else document.removeEventListener(type, handler, true);
    }
    for (const type of ['resize', 'scroll']) {
      if (watching) view?.visualViewport?.addEventListener(type, placeMenu);
      else view?.visualViewport?.removeEventListener(type, placeMenu);
    }
  }
  function dismiss(returnFocus=false): void {
    const wasOpen=more.open; more.open=false; watchOpen();
    if(popoverOpen){try{menu.hidePopover();}catch{}popoverOpen=false;}
    summary.setAttribute('aria-expanded','false');if(wasOpen&&returnFocus)summary.focus({preventScroll:true});
  }
  function placeMenu():void {
    watchOpen();
    if(!more.open){if(popoverOpen){try{menu.hidePopover();}catch{}popoverOpen=false;}return;}
    if(topLayer&&!popoverOpen){try{menu.showPopover();popoverOpen=true;}catch{topLayer=false;menu.removeAttribute('popover');menu.removeAttribute('data-av-menu-layer');}}
    const anchor = summary.getBoundingClientRect();
    const bounds = visibleViewport(view);
    if (!topLayer) for (let ancestor = host.parentElement; ancestor && ancestor !== document.body; ancestor = ancestor.parentElement) {
      const style = view?.getComputedStyle?.(ancestor), rect = ancestor.getBoundingClientRect();
      if (/auto|scroll|hidden|clip/.test(style?.overflowY || '')) { bounds.top = Math.max(bounds.top, rect.top + 4); bounds.bottom = Math.min(bounds.bottom, rect.bottom - 4); }
      if (/auto|scroll|hidden|clip/.test(style?.overflowX || '')) { bounds.left = Math.max(bounds.left, rect.left + 4); bounds.right = Math.min(bounds.right, rect.right - 4); }
    }
    menu.style.setProperty('max-width', Math.max(0, bounds.right - bounds.left) + 'px');
    menu.style.setProperty('--av-menu-shift', '0px');
    const box = menu.getBoundingClientRect();
    const placed = anchoredPanel(anchor, bounds, box.width || 256, Math.max(box.height || 0, menu.scrollHeight || 280), 4);
    more.setAttribute('data-av-menu-side', placed.side);
    menu.style.setProperty('--av-menu-max-height', placed.maxHeight + 'px');
    if (topLayer) {
      menu.style.setProperty('left', placed.left + 'px');
      const height = menu.getBoundingClientRect().height;
      menu.style.setProperty('top', anchoredPanel(anchor, bounds, placed.width, height, 4).top + 'px');
      menu.style.setProperty('bottom', 'auto');
    } else menu.style.setProperty('--av-menu-shift', (placed.left - (Number.isFinite(box.left) ? box.left : placed.left)) + 'px');
  }
  function hitSize(): number { return Math.max(36, Number.parseFloat(view?.getComputedStyle?.(host).getPropertyValue?.('--av-command-hit-size') || '') || 36); }

  // Intrinsic label measurement respects text enlargement without inserting
  // measurement elements into evidence or depending on a menu's stretched width.
  const measuring = document.createElement('canvas');
  let measure: CanvasRenderingContext2D | null = null;
  try { measure = measuring.getContext?.('2d') || null; } catch { /* Bounded DOM hosts. */ }
  function commandWidth(command: Command, targetSize: number): number {
    const style = view?.getComputedStyle?.(command.control);
    const fontSize = Number.parseFloat(style?.fontSize || '') || 13;
    let width = Math.max((command.options.width ?? 36) * Math.max(1, fontSize / 13), targetSize);
    if (command.options.labelled) {
      if (measure) measure.font = style?.font || `${fontSize}px sans-serif`;
      const text = measure?.measureText(command.options.label).width ?? command.options.label.length * fontSize * .62;
      width = Math.max(width, Math.ceil(text + (command.options.icon ? 22 : 0) + fontSize * 1.4));
    }
    command.control.style.setProperty('--av-command-width', width + 'px');
    return width;
  }
  function refresh():void{
    if(stopped||refreshing)return;const targetSize=hitSize(),widthOf=(command:Command)=>commandWidth(command,targetSize);const eligible=commands.filter(command=>!command.control.hidden),inline=eligible.filter(command=>!command.options.menuOnly);host.style.setProperty('--av-command-preferred-width',(inline.reduce((total,command)=>total+widthOf(command),0)+Math.max(0,inline.length-1)*4+(eligible.some(command=>command.options.menuOnly)?targetSize+4:0))+'px');const width=host.clientWidth;if(!(width>0))return;refreshing=true;
    try{
      const focused=document.activeElement;
      const selected=commandGroups(width,commands.filter(command=>!command.control.hidden).map(command=>({width:widthOf(command),priority:command.options.priority??50,group:command.options.group||String(commands.indexOf(command)),menuOnly:command.options.menuOnly})),targetSize+4);
      for(const destination of [primary,menu]){
        const wanted=commands.filter((command,index)=>selected.has(command.options.group||String(index))===(destination===primary));
        wanted.forEach((command,index)=>{
          const inline=destination===primary;const visual=command.control.querySelector<HTMLElement>('.av-command-visual');if(visual&&!command.options.icon&&!visual.querySelector('svg'))visual.hidden=!inline;command.control.setAttribute('data-av-command-location',inline?'inline':'menu');
          const current=destination.children[index]||null;
          if(current!==command.control){const retainsFocus=focused===command.control;destination.insertBefore(command.control,current);if(retainsFocus&&!inline){more.open=true;summary.setAttribute('aria-expanded','true');}}
        });
      }
      const overflow=commands.some(command=>command.control.parentNode===menu&&!command.control.hidden);
      more.hidden=!overflow;if(!overflow){dismiss();if(focused===summary)commands.find(command=>!command.control.hidden&&!command.control.disabled)?.control.focus();}
      placeMenu();
      if(commands.some(command=>command.control===focused)&&focused?.isConnected&&document.activeElement!==focused)(focused as HTMLElement).focus({preventScroll:true});
    }finally{refreshing=false;}
  }
  listen(more,'toggle',(()=>{summary.setAttribute('aria-expanded',String(more.open));placeMenu();}) as EventListener);
  listen(menu,'toggle',((event:Event)=>{if(event.target===menu&&(event as ToggleEvent).newState==='closed'&&popoverOpen&&!menu.matches(':popover-open')){popoverOpen=false;dismiss();}}) as EventListener);
  // Deliberate menus stay open until an action, outside press, focus exit or Escape.
  // Pointer transit is not a dismissal request (including magnification and tremor).
  listen(more,'focusout',((event:FocusEvent)=>{if(!more.contains(event.relatedTarget as Node))dismiss();}) as EventListener);
  listen(more,'keydown',((event:KeyboardEvent)=>{
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();dismiss(true);return;}
    if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
    const buttons=commands.filter(command=>command.control.parentNode===menu&&!command.control.disabled&&!command.control.hidden).map(command=>command.control);if(!buttons.length)return;
    event.preventDefault();more.open=true;summary.setAttribute('aria-expanded','true');placeMenu();const current=buttons.indexOf(document.activeElement as HTMLButtonElement);const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:event.key==='ArrowDown'?(current+1)%buttons.length:(current<=0?buttons.length:current)-1;buttons[next].focus();
  }) as EventListener);
  if(view?.ResizeObserver){const observer=new view.ResizeObserver(refresh);observer.observe(host);undo.push(()=>observer.disconnect());}
  if(view&&!view.ResizeObserver)listen(view,'resize',refresh as EventListener);
  return{
    add(control,options){if(commands.some(command=>command.control===control))return;const marker=document.createComment('av-command');control.parentNode?.insertBefore(marker,control);const original=Array.from(control.childNodes),oldClass=control.className,oldWidth=control.style.getPropertyValue('--av-command-width');const attributes=['data-av-command-location','data-av-command','data-av-command-labelled','title','aria-label'].map(name=>[name,control.getAttribute(name)] as const);
      control.classList.add('av-command');control.setAttribute('data-av-command','');if(options.labelled)control.setAttribute('data-av-command-labelled','');control.setAttribute('data-av-command-location','menu');control.style.setProperty('--av-command-width',(options.width??36)+'px');control.title=options.label;if(!control.hasAttribute('aria-label'))control.setAttribute('aria-label',options.label);
      const visual=document.createElement('span');visual.className='av-command-visual';visual.setAttribute('aria-hidden','true');if(options.icon)visual.appendChild(commandIcon(document,options.icon));else for(const child of original)visual.appendChild(child);
      const text=document.createElement('span');text.className='av-command-label';text.textContent=options.label;control.replaceChildren(visual,text);commands.push({control,options,marker,original});menu.appendChild(control);
      undo.push(()=>{if(marker.parentNode)marker.parentNode.replaceChild(control,marker);control.replaceChildren(...original);control.className=oldClass;if(oldWidth)control.style.setProperty('--av-command-width',oldWidth);else control.style.removeProperty('--av-command-width');for(const[name,value]of attributes){if(value===null)control.removeAttribute(name);else control.setAttribute(name,value);}});refresh();
    },
    update(control, options) {
      const command = commands.find(item => item.control === control);
      if (!command || stopped) return;
      command.options = {...command.options, ...options};
      control.title = command.options.label;
      control.setAttribute('aria-label', command.options.label);
      const text = control.querySelector<HTMLElement>('.av-command-label');
      if (text) text.textContent = command.options.label;
      if (options.icon !== undefined) control.querySelector('.av-command-visual')?.replaceChildren(commandIcon(document, options.icon));
      if (command.options.labelled) control.setAttribute('data-av-command-labelled',''); else control.removeAttribute('data-av-command-labelled');
      refresh();
    },refresh,dismiss,
    cleanup(){if(stopped)return;dismiss();stopped=true;watchOpen();for(const restore of undo.reverse())restore();primary.remove();more.remove();if(preferredWidth)host.style.setProperty('--av-command-preferred-width',preferredWidth);else host.style.removeProperty('--av-command-preferred-width');host.classList.toggle('av-command-bar',previous);}
  };
}
