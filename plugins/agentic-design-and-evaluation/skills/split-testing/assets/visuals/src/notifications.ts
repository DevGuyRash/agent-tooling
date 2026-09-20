/** One report-owned transient status channel, shared by figure and notebook actions. */
export type NotificationTone = 'success' | 'error' | 'info';
export interface NotificationMessage { text: string; tone?: NotificationTone; source?: Element }
export interface NotificationController { show(message: NotificationMessage): void; refresh():void; cleanup(): void }
interface ToastRecord { owner:object; source:Element; node:HTMLElement; timer:number|null; removeTimer:number|null; closing:boolean; pause:()=>void; resume:()=>void; paint:()=>void }
const pools=new WeakMap<Document,{trays:Map<Element,HTMLElement>;records:ToastRecord[]}>();
export function attachNotifications(root: HTMLElement, mirror: (target: HTMLElement, source: Element) => void, options: { limit?: number; duration?: number } = {}): NotificationController {
  const document=root.ownerDocument,view=document.defaultView,limit=options.limit??3,duration=options.duration??4500;
  if(!Number.isInteger(limit)||limit<1||!Number.isFinite(duration)||duration<0)throw new TypeError('Notifications need a positive limit and a nonnegative duration.');
  const pool=pools.get(document)||{trays:new Map<Element,HTMLElement>(),records:[]};pools.set(document,pool);
  const {trays,records}=pool,owner={};let stopped=false;
  const later=(fn:()=>void,ms:number)=>(view?.setTimeout||setTimeout)(fn,ms) as unknown as number;
  const cancel=(timer:number|null)=>{if(timer!==null)(view?.clearTimeout||clearTimeout)(timer);};
  function trayFor(source:Element):HTMLElement{
    const host=source.closest('dialog[open]')||document.body;let tray=trays.get(host);
    if(!tray){tray=document.createElement('div');tray.className='av-notifications';tray.setAttribute('data-av-review-ui','');tray.setAttribute('aria-label','Notifications');trays.set(host,tray);}
    if(!tray.isConnected)host.appendChild(tray);return tray;
  }
  function pruneTrays(): void {
    for (const [host, tray] of trays) if (!records.some(record => tray.contains(record.node))) { tray.remove(); trays.delete(host); }
  }
  function remove(record:typeof records[number],fade=true):void{
    if(record.closing)return;record.closing=true;cancel(record.timer);record.timer=null;
    const finish=()=>{record.node.remove();const index=records.indexOf(record);if(index>=0)records.splice(index,1);pruneTrays();};
    if(fade){record.node.setAttribute('data-av-dismissing','');record.removeTimer=later(finish,180);}else finish();
  }
  return{
    show(message){
      if(stopped||!message.text)return;const source=message.source||root;
      while(records.filter(record=>!record.closing).length>=limit){const oldest=records.find(record=>!record.closing)!;remove(oldest);}
      // Bound fading remnants as well as active messages during rapid actions.
      while(records.length>=limit+1)removeImmediately(records[0]);
      const node=document.createElement('div');node.className='av-toast';node.setAttribute('data-av-tone',message.tone||'info');node.setAttribute('role','status');node.setAttribute('aria-live',message.tone==='error'?'assertive':'polite');node.setAttribute('aria-atomic','true');mirror(node,source);
      const icon=document.createElement('span');icon.className='av-toast-icon';icon.setAttribute('aria-hidden','true');icon.textContent=message.tone==='success'?'✓':message.tone==='error'?'!':'i';node.appendChild(icon);
      const text=document.createElement('span');text.className='av-toast-text';text.textContent=message.text;text.tabIndex=0;node.appendChild(text);
      const close=document.createElement('button');close.type='button';close.className='av-toast-close';close.setAttribute('aria-label','Dismiss notification');close.textContent='×';node.appendChild(close);
      const record:ToastRecord={owner,source,node,paint:()=>mirror(node,source),timer:null,removeTimer:null,closing:false,pause(){cancel(record.timer);record.timer=null;},resume(){record.pause();if(!record.closing&&duration)record.timer=later(()=>remove(record),duration);}};
      close.addEventListener('click',()=>remove(record));let hovered=false,focused=false;node.addEventListener('pointerenter',()=>{hovered=true;record.pause();});node.addEventListener('pointerleave',()=>{hovered=false;if(!focused)record.resume();});node.addEventListener('focusin',()=>{focused=true;record.pause();});node.addEventListener('focusout',(event:FocusEvent)=>{focused=node.contains(event.relatedTarget as Node);if(!hovered&&!focused)record.resume();});records.push(record);trayFor(source).appendChild(node);record.resume();
    },
    refresh(){for(const record of records)if(record.owner===owner&&!record.closing){const tray=trayFor(record.source);if(record.node.parentNode!==tray)tray.appendChild(record.node);record.paint();}pruneTrays();},
    cleanup(){stopped=true;for(const record of [...records])if(record.owner===owner)removeImmediately(record);for(const[host,tray]of trays)if(!records.some(record=>tray.contains(record.node))){tray.remove();trays.delete(host);}}
  };
  function removeImmediately(record:typeof records[number]):void{cancel(record.timer);cancel(record.removeTimer);record.node.remove();const index=records.indexOf(record);if(index>=0)records.splice(index,1);pruneTrays();}
}
