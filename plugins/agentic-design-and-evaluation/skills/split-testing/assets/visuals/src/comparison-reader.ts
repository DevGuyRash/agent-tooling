import { attachFloatingPanel } from './floating-panel';
import { commandIcon } from './command-bar';
import { registerReviewOrder, reviewText } from './review-targets';

/** A reading window is independent of the chosen evidence set. No ranking,
 * correspondence or difference is inferred from position or linked scrolling. */
export function comparisonWindow(keys: readonly string[], capacity: number, offset: number, reference: string | null, showReference = false): { keys: string[]; offset: number; step: number; remaining: string[] } {
  const size = Math.max(1, Math.floor(Number.isFinite(capacity) ? capacity : 1));
  const pin = reference && keys.includes(reference) ? reference : null;
  const remaining = pin ? keys.filter(key => key !== pin) : [...keys];
  const step = Math.max(1, size - (pin && size > 1 ? 1 : 0));
  const at = Math.max(0, Math.min(Math.floor(Number.isFinite(offset) ? offset : 0), Math.max(0, remaining.length - 1)));
  const selected = pin && size === 1 && showReference ? [pin] : [...(pin && size > 1 ? [pin] : []), ...remaining.slice(at, at + step)];
  return {keys: selected.length ? selected : pin ? [pin] : [], offset: at, step, remaining};
}
export interface ComparisonReader {
  readonly explorer: HTMLElement;
  readonly stage: HTMLElement;
  render(key?: string): void;
  compare(): void;
  reset(): void;
  reveal(key: string): void;
  cleanup(): void;
}
const pinIcon = 'm8 3 8 0-1 6 4 4H5l4-4-1-6M12 13v8';
const gridIcon = 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z';
const columnsIcon = 'M3 3h18v18H3zM12 3v18';
const linkIcon = 'm9 15 6-6M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0';

export function attachComparisonReader(explorer: HTMLElement, stage: HTMLElement, objects: readonly HTMLElement[]): ComparisonReader {
  const document=stage.ownerDocument, view=document.defaultView, undo:(()=>void)[]=[];
  const keys=objects.map(object=>object.getAttribute('data-av-object')!);
  const byKey=new Map(objects.map((object,index)=>[keys[index],object]));
  const labelOf=(object:HTMLElement)=>reviewText(object.querySelector('summary') || object).trim();
  const labels=new Map(objects.map((object,index)=>[keys[index],labelOf(object)]));
  const own=<T extends Element>(selector:string)=>Array.from(explorer.querySelectorAll<T>(selector)).filter(node=>node.closest('[data-av-explorer]')===explorer);
  const checks=own<HTMLInputElement>('[data-av-compare]').filter(control=>byKey.has(control.getAttribute('data-av-compare')||''));
  const controlsByKey=new Map(checks.map(control=>[control.getAttribute('data-av-compare')!,control]));
  const selects=own<HTMLSelectElement>('[data-av-select]');
  let current=keys.find(key=>byKey.get(key)!.classList.contains('av-selected')) || keys[0] || '';
  let selected=new Set(checks.filter(input=>input.checked).map(input=>input.getAttribute('data-av-compare')!));
  let comparing=selected.size>1, layout:'window'|'cards'='window', reference:string|null=null, offset=0, capacity=1, showReference=false, linked=false, stopped=false;
  let visibleKeys:string[]=[], rendering=false, layoutFrame:number|null=null, scrollFrame:number|null=null, leader:HTMLElement|null=null;
  const positions=new Map<HTMLElement,{top:number;left:number}>(), expected=new WeakMap<HTMLElement,number>();
  const bodies=new Map<HTMLElement,string>();
  const originalChildren=Array.from(stage.childNodes); const releaseOrder=registerReviewOrder(stage);
  // Keep authored non-record siblings in place while moving the live records.
  const slotsByPosition=objects.map(object=>{const slot=document.createComment('av-record-slot');stage.insertBefore(slot,object);return slot;});
  const originalStageClass=stage.className, originalExplorerComparing=explorer.classList.contains('av-comparing');
  const oldColumns=stage.style.getPropertyValue('--av-reader-columns');
  const empty=document.createElement('p');empty.className='av-reader-empty';empty.setAttribute('data-av-review-ui','');empty.textContent='Choose records to start a comparison.';
  stage.classList.add('av-reading-stage'); stage.setAttribute('data-av-comparison-layout','window');
  for(const object of objects){
    const attributes=['hidden','open'].map(name=>[name,object.getAttribute(name)] as const), oldClass=object.className;
    const summary=object.querySelector<HTMLElement>('summary'), body=object.querySelector<HTMLElement>('.av-object-body');
    if(body){bodies.set(body,object.getAttribute('data-av-object')!);positions.set(body,{top:body.scrollTop,left:body.scrollLeft});}
    if(summary){
      const disabled=summary.getAttribute('aria-disabled');summary.removeAttribute('aria-disabled');
      const pin=document.createElement('button');pin.type='button';pin.className='av-record-pin';pin.setAttribute('data-av-controls','');pin.setAttribute('data-av-review-ui','');pin.setAttribute('data-av-pin-record',object.getAttribute('data-av-object')!);pin.appendChild(commandIcon(document,pinIcon));summary.appendChild(pin);
      const clicked=(event:Event)=>{event.preventDefault();event.stopPropagation();const key=object.getAttribute('data-av-object')!;reference=reference===key?null:key;if(!selected.has(key))selected.add(key);comparing=true;offset=0;showReference=false;render();};
      pin.addEventListener('click',clicked);undo.push(()=>{pin.removeEventListener('click',clicked);pin.remove();if(disabled===null)summary.removeAttribute('aria-disabled');else summary.setAttribute('aria-disabled',disabled);});
    }
    undo.push(()=>{object.className=oldClass;object.removeAttribute('data-av-reference');for(const[name,value]of attributes)if(value===null)object.removeAttribute(name);else object.setAttribute(name,value);});
  }
  // Keep the established native command inputs, but remove their duplicate
  // presentation. The record picker uses its own controls, never clones evidence.
  const hiddenControls=new Set<HTMLElement>();
  for(const control of [...checks,...selects]){
    const container=control.closest<HTMLElement>('.av-artifact-controls,.av-explorer-tools');
    if(container&&!hiddenControls.has(container)){hiddenControls.add(container);const hidden=container.hidden;container.hidden=true;undo.push(()=>{container.hidden=hidden;});}
  }
  const bar=document.createElement('div');bar.className='av-comparison-bar';bar.setAttribute('data-av-controls','');bar.setAttribute('data-av-review-ui','');bar.setAttribute('role','group');bar.setAttribute('aria-label','Read and compare');stage.parentNode!.insertBefore(bar,stage);
  function button(label:string,attr:string,parent:HTMLElement=bar,icon?:string):HTMLButtonElement{const b=document.createElement('button');b.type='button';b.className='av-button';b.setAttribute(attr,'');if(icon)b.appendChild(commandIcon(document,icon));const span=document.createElement('span');span.textContent=label;b.appendChild(span);parent.appendChild(b);return b;}
  const modes=document.createElement('div');modes.className='av-reader-switch';modes.setAttribute('role','group');modes.setAttribute('aria-label','Reading mode');bar.appendChild(modes);
  const read=button('Read','data-av-read-one',modes),compare=button('Compare','data-av-read-compare',modes);
  const pickerButton=button('Records','data-av-record-picker',bar,gridIcon);
  const picker=attachFloatingPanel(pickerButton,explorer,'Choose records');picker.element.classList.add('av-record-picker');
  const searchLabel=document.createElement('label');searchLabel.className='av-picker-search';searchLabel.textContent='Find a record';
  const search=document.createElement('input');search.type='search';search.placeholder='Name or passage';search.setAttribute('data-av-record-search','');searchLabel.appendChild(search);picker.body.appendChild(searchLabel);
  const pickerTools=document.createElement('div');pickerTools.className='av-picker-tools';picker.body.appendChild(pickerTools);
  const all=button('Select all','data-av-records-all',pickerTools),clear=button('Clear','data-av-records-clear',pickerTools);
  const matchCount=document.createElement('output');matchCount.className='av-picker-count';matchCount.setAttribute('role','status');picker.body.appendChild(matchCount);
  const options=document.createElement('div');options.className='av-record-options';picker.body.appendChild(options);
  const more=button('Show more','data-av-records-more',picker.body);
  const pickerFoot=document.createElement('div');pickerFoot.className='av-picker-footer';picker.body.appendChild(pickerFoot);
  const done=button('Done','data-av-records-done',pickerFoot);
  let shown=60;
  // Search text is built once from actual evidence, with the controls excluded.
  const searchable=new Map(keys.map(key=>[key,(labels.get(key)+' '+reviewText(byKey.get(key)!)).toLocaleLowerCase()]));
  const optionRows=new Map<string,{row:HTMLElement;check:HTMLInputElement;open:HTMLButtonElement}>();
  for(const key of keys){
    const row=document.createElement('div');row.className='av-record-option';
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.setAttribute('data-av-pick-record',key);checkbox.setAttribute('aria-label','Compare '+labels.get(key));row.appendChild(checkbox);
    const open=document.createElement('button');open.type='button';open.className='av-record-choice';open.setAttribute('data-av-open-record',key);open.textContent=labels.get(key)!;row.appendChild(open);
    // Full labels and original evidence are not truncated in the reading panes.
    optionRows.set(key,{row,check:checkbox,open});options.appendChild(row);
  }
  const settings=document.createElement('div');settings.className='av-comparison-options';bar.appendChild(settings);
  const cards=button('All cards','data-av-reader-cards',settings,gridIcon);
  const sync=button('Scroll together','data-av-reader-sync',settings,linkIcon);sync.title='Link relative vertical progress. Paragraphs are not assumed to correspond.';
  const navigation=document.createElement('div');navigation.className='av-comparison-navigation';navigation.setAttribute('data-av-controls','');navigation.setAttribute('data-av-review-ui','');stage.parentNode!.insertBefore(navigation,stage);
  const previous=button('Previous','data-av-reader-previous',navigation),range=document.createElement('output');range.setAttribute('role','status');range.setAttribute('aria-live','polite');range.setAttribute('data-av-reader-range','');navigation.appendChild(range);
  const next=button('Next','data-av-reader-next',navigation),referenceToggle=button('Reference','data-av-reader-reference',navigation,pinIcon);
  const existingStatus=own<HTMLElement>('[data-av-comparison-status]')[0];
  const status=existingStatus || document.createElement('output');
  if(!existingStatus){status.className='av-sr-only';status.setAttribute('data-av-comparison-status','');status.setAttribute('data-av-review-ui','');bar.appendChild(status);}
  function matching():string[]{const query=search.value.trim().toLocaleLowerCase();return keys.filter(key=>!query||searchable.get(key)!.includes(query));}
  function paintPicker():void{
    const matches=matching(),visible=new Set(matches.slice(0,shown));
    for(const[key,entry]of optionRows){entry.row.hidden=!visible.has(key);entry.check.checked=selected.has(key);entry.check.hidden=!comparing;entry.open.setAttribute('aria-current',key===current?'true':'false');}
    all.hidden=clear.hidden=!comparing;all.disabled=!matches.length||matches.every(key=>selected.has(key));clear.disabled=!selected.size;
    all.querySelector('span')!.textContent=search.value.trim()?'Select matches':'Select all';
    matchCount.textContent=`${matches.length} ${matches.length===1?'record':'records'}${comparing?' · '+selected.size+' selected':''}`;
    more.hidden=matches.length<=shown;more.querySelector('span')!.textContent=`Show ${Math.min(60,Math.max(0,matches.length-shown))} more`;
    picker.refresh();
  }
  function savePositions():void{for(const[body,key]of bodies)if(visibleKeys.includes(key)&&body.clientHeight>0)positions.set(body,{top:body.scrollTop,left:body.scrollLeft});}
  function slots():number{
    const width=stage.clientWidth;if(!(width>0))return capacity;
    const body=objects[0]?.querySelector<HTMLElement>('.av-object-body');
    const text=Number.parseFloat(view?.getComputedStyle?.(body||stage).fontSize||'')||16;
    const rem=Number.parseFloat(view?.getComputedStyle?.(document.documentElement).fontSize||'')||16;
    // Match CSS em/rem sizing; a reader increasing text gets fewer, wider panes.
    const minimum=Math.max(288,18*rem,18*text),gap=Math.max(12,rem);
    return Math.max(1,Math.min(4,Math.floor((width+gap)/(minimum+gap))));
  }
  function render(key?:string):void{
    if(stopped||rendering)return;rendering=true;
    try{
      savePositions();capacity=slots();
      if(key&&byKey.has(key))current=key;
      const chosen=keys.filter(key=>selected.has(key));
      if(reference&&!selected.has(reference))reference=null;
      const window=comparisonWindow(chosen,capacity,offset,reference,showReference);offset=window.offset;
      visibleKeys=comparing?(layout==='cards'?chosen:window.keys):current?[current]:[];
      const comparingNow=comparing&&chosen.length>0;
      if(comparing&&!chosen.length){if(!empty.parentNode)stage.appendChild(empty);}else empty.remove();
      stage.setAttribute('data-av-comparison-layout',comparingNow?layout:'read');
      stage.style.setProperty('--av-reader-columns',String(Math.max(1,Math.min(capacity,visibleKeys.length))));
      explorer.classList.toggle('av-comparing',comparingNow);
      const visibleSet=new Set(visibleKeys),ordered=comparingNow?[...visibleKeys,...keys.filter(key=>!visibleSet.has(key))]:keys;
      ordered.forEach((key,index)=>{const node=byKey.get(key)!,slot=slotsByPosition[index];if(slot.nextSibling!==node)stage.insertBefore(node,slot.nextSibling);});
      for(const[key,object]of byKey){const visible=visibleSet.has(key);object.hidden=!visible;if(visible)object.setAttribute('open','');else object.removeAttribute('open');object.classList.toggle('av-compared',comparingNow&&selected.has(key));object.classList.toggle('av-selected',key===current);if(reference===key)object.setAttribute('data-av-reference','');else object.removeAttribute('data-av-reference');
        const pin=object.querySelector<HTMLButtonElement>('[data-av-pin-record]');if(pin){pin.hidden=!comparing;pin.setAttribute('aria-pressed',String(reference===key));pin.setAttribute('aria-label',(reference===key?'Unpin ':'Pin as reference: ')+labels.get(key));pin.title=pin.getAttribute('aria-label')!;}}
      for(const input of checks)input.checked=selected.has(input.getAttribute('data-av-compare')!);
      for(const select of selects)if(Array.from(select.options).some(option=>option.value===current))select.value=current;
      read.setAttribute('aria-pressed',String(!comparing));compare.setAttribute('aria-pressed',String(comparing));
      pickerButton.querySelector('span')!.textContent=comparing?`Records · ${chosen.length}`:`Records · ${keys.length}`;
      cards.hidden=sync.hidden=!comparing;cards.setAttribute('aria-pressed',String(layout==='cards'));cards.querySelector('span')!.textContent=layout==='cards'?'Reading panes':'All cards';
      sync.setAttribute('aria-pressed',String(linked));sync.disabled=visibleKeys.length<2;
      previous.disabled=comparing?layout==='cards'||offset<=0:keys.indexOf(current)<=0;
      next.disabled=comparing?layout==='cards'||offset+window.step>=window.remaining.length:keys.indexOf(current)>=keys.length-1;
      referenceToggle.hidden=!(comparing&&layout==='window'&&reference&&capacity===1);referenceToggle.setAttribute('aria-pressed',String(showReference));referenceToggle.querySelector('span')!.textContent=showReference?'Back to records':'Reference';
      const message=!comparing?`${keys.indexOf(current)+1} of ${keys.length} · ${labels.get(current)||'No records'}`:!chosen.length?'Choose records to compare':layout==='cards'?`${chosen.length} selected · all cards`:`${reference?'Reference + ':''}${window.remaining.length?`${offset+1}–${Math.min(window.remaining.length,offset+window.step)} of ${window.remaining.length}`:'reference'}${showReference&&capacity===1?' · viewing reference':''}`;
      range.textContent=message;if(status)status.textContent=!comparing?'Single record view.':`${chosen.length} selected. ${visibleKeys.length} visible. ${linked?'Scrolling follows relative progress, not matching passages.':'Independent scrolling.'}`;
      paintPicker();
      for(const[body,key]of bodies)if(visibleKeys.includes(key)){const position=positions.get(body);if(position){body.scrollTop=position.top;body.scrollLeft=position.left;expected.set(body,body.scrollTop);}}
    }finally{rendering=false;}
  }
  function schedule():void{if(stopped||layoutFrame!==null)return;if(view?.requestAnimationFrame)layoutFrame=view.requestAnimationFrame(()=>{layoutFrame=null;render();});else render();}
  function listen(target:EventTarget,type:string,handler:EventListener,capture=false):void{target.addEventListener(type,handler,capture);undo.push(()=>target.removeEventListener(type,handler,capture));}
  const activate=(action:()=>void):EventListener=>event=>{event.preventDefault();event.stopPropagation();action();};
  listen(read,'click',activate(()=>{comparing=false;render();}));
  listen(compare,'click',activate(()=>{comparing=true;if(!selected.size&&current)selected.add(current);render();picker.open();}));
  listen(cards,'click',activate(()=>{layout=layout==='cards'?'window':'cards';showReference=false;render();}));
  listen(sync,'click',activate(()=>{linked=!linked;render();}));
  listen(previous,'click',activate(()=>{if(comparing){offset=Math.max(0,offset-comparisonWindow(keys.filter(key=>selected.has(key)),capacity,offset,reference).step);showReference=false;}else current=keys[Math.max(0,keys.indexOf(current)-1)];render();}));
  listen(next,'click',activate(()=>{if(comparing){offset+=comparisonWindow(keys.filter(key=>selected.has(key)),capacity,offset,reference).step;showReference=false;}else current=keys[Math.min(keys.length-1,keys.indexOf(current)+1)];render();}));
  listen(referenceToggle,'click',activate(()=>{showReference=!showReference;render();}));
  listen(search,'input',(()=>{shown=60;paintPicker();}) as EventListener);
  listen(all,'click',activate(()=>{for(const key of matching())selected.add(key);render();}));
  listen(clear,'click',activate(()=>{selected.clear();reference=null;offset=0;render();}));
  listen(more,'click',activate(()=>{shown+=60;paintPicker();}));
  listen(done,'click',activate(()=>picker.close(true)));
  listen(options,'change',((event:Event)=>{const target=event.target as HTMLInputElement,key=target.getAttribute('data-av-pick-record');if(!key)return;event.stopPropagation();if(target.checked)selected.add(key);else selected.delete(key);render();}) as EventListener);
  listen(options,'click',((event:Event)=>{const target=(event.target as Element).closest<HTMLElement>('[data-av-open-record]');if(!target)return;event.preventDefault();event.stopPropagation();const key=target.getAttribute('data-av-open-record')!;if(comparing){if(selected.has(key))selected.delete(key);else selected.add(key);render();}else{current=key;render();picker.close(true);}}) as EventListener);
  listen(stage,'scroll',((event:Event)=>{
    const body=event.target as HTMLElement,key=bodies.get(body);if(stopped||rendering||!key||!visibleKeys.includes(key)||body.clientHeight<=0)return;
    const anticipated=expected.get(body);expected.delete(body);positions.set(body,{top:body.scrollTop,left:body.scrollLeft});if(anticipated!==undefined&&Math.abs(anticipated-body.scrollTop)<1)return;
    if(!linked||!comparing||body.scrollHeight<=body.clientHeight)return;leader=body;if(scrollFrame!==null)return;
    const propagate=()=>{scrollFrame=null;const source=leader;leader=null;if(stopped||!linked||!source||!visibleKeys.includes(bodies.get(source)!))return;const ratio=source.scrollTop/Math.max(1,source.scrollHeight-source.clientHeight);for(const[other,k]of bodies)if(other!==source&&visibleKeys.includes(k)&&other.clientHeight>0){const top=Math.max(0,other.scrollHeight-other.clientHeight)*Math.max(0,Math.min(1,ratio));expected.set(other,Math.round(top));other.scrollTop=top;positions.set(other,{top:other.scrollTop,left:other.scrollLeft});}};
    if(view?.requestAnimationFrame)scrollFrame=view.requestAnimationFrame(propagate);else propagate();
  }) as EventListener,true);
  const observer=view?.ResizeObserver?new view.ResizeObserver(schedule):null;observer?.observe(stage);observer?.observe(bar);
  if(view)listen(view,'resize',schedule);
  // Readability depends on font metrics too. Font loading and preference edits
  // cause a fresh capacity calculation without changing the selected set.
  void document.fonts?.ready.then(()=>{if(!stopped)schedule();});
  render();
  return {explorer,stage,render,
    compare(){selected=new Set(checks.filter(input=>input.checked).map(input=>input.getAttribute('data-av-compare')!));comparing=selected.size>1;offset=0;showReference=false;if(selected.size===1)current=[...selected][0];render();},
    reset(){comparing=false;selected.clear();reference=null;offset=0;showReference=false;render();},
    reveal(key){if(!byKey.has(key))return;current=key;if(comparing&&selected.has(key)){if(reference===key&&capacity===1)showReference=true;else{showReference=false;offset=Math.max(0,keys.filter(k=>selected.has(k)&&k!==reference).indexOf(key));}}else comparing=false;render();},
    cleanup(){if(stopped)return;stopped=true;observer?.disconnect();if(layoutFrame!==null)view?.cancelAnimationFrame(layoutFrame);if(scrollFrame!==null)view?.cancelAnimationFrame(scrollFrame);picker.cleanup();empty.remove();for(const restore of undo.reverse())restore();for(const slot of slotsByPosition)slot.remove();for(const node of originalChildren)if(node.parentNode===stage)stage.appendChild(node);releaseOrder();bar.remove();navigation.remove();stage.className=originalStageClass;stage.removeAttribute('data-av-comparison-layout');if(oldColumns)stage.style.setProperty('--av-reader-columns',oldColumns);else stage.style.removeProperty('--av-reader-columns');explorer.classList.toggle('av-comparing',originalExplorerComparing);bodies.clear();positions.clear();}
  };
}
