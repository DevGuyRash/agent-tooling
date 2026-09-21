import { escapeText as e } from './core';
import { figureSource, figureTitle, visualAdapter, figureOrigin, figureContext } from './figures';
import { wrapText } from './text-layout';
import { validateExportCss, validateExportTree } from './export-safety';
const paintProperties = ['color','fill','fill-opacity','stroke','stroke-width','stroke-opacity','stroke-dasharray','stroke-linecap','stroke-linejoin','opacity','font-family','font-size','font-weight','font-style','text-anchor','dominant-baseline','letter-spacing','white-space','paint-order','visibility','background-color','border-color','border-width','border-style','border-radius','line-height','text-align','display','padding','box-sizing','width','height','stop-color','stop-opacity','filter','clip-path','mask','marker-start','marker-mid','marker-end','transform','transform-origin','transform-box','overflow','overflow-wrap','word-break','word-spacing','font-stretch','font-variant','text-decoration','text-transform','vertical-align','margin-top','margin-right','margin-bottom','margin-left','padding-top','padding-right','padding-bottom','padding-left','max-width','min-width','max-height','min-height','flex-direction','flex-wrap','align-items','align-content','justify-content','gap'];
const SVG_NS = 'http://www.w3.org/2000/svg';
function serialize(node: Node, namespace?: string): string {
  if (node.nodeType === 3) return e(node.textContent || '');
  if (node.nodeType !== 1) return '';
  const element = node as Element, ns = element.namespaceURI || namespace;
  const attributes = Array.from(element.attributes).map(attribute => ` ${attribute.name}="${e(attribute.value)}"`).join('');
  const declaration = ns && ns !== namespace && !element.hasAttribute('xmlns') ? ` xmlns="${e(ns)}"` : '';
  const name = element.localName || element.tagName.toLowerCase();
  return `<${name}${declaration}${attributes}>${Array.from(node.childNodes).map(child => serialize(child,ns)).join('')}</${name}>`;
}
/** Bake the *active* cascade, not the renderer's catalog of unused theme rules.
 * Mermaid ships optional look rules that reference definitions absent from this
 * scene. Those rules are not evidence or dependencies of the painted snapshot.
 * Active paint references and adapter-provided SVG still undergo strict checks.
 */
function paintedClone(element: SVGElement, paint = true): SVGElement {
  const copy = element.cloneNode(true) as SVGElement, view = element.ownerDocument.defaultView;
  const live = [element, ...Array.from(element.querySelectorAll<SVGElement>('*'))];
  const clones = [copy, ...Array.from(copy.querySelectorAll<SVGElement>('*'))];
  const restore: (() => void)[] = [];
  const scope=element.closest<HTMLElement>('[data-av-figure]');
  if(paint&&scope){const original=scope.getAttribute('data-av-export-reading');scope.setAttribute('data-av-export-reading','');restore.push(()=>{if(original===null)scope.removeAttribute('data-av-export-reading');else scope.setAttribute('data-av-export-reading',original);});}
  try {
    // Reader emphasis is transient, never an authored status or category color.
    // This synchronous read phase completes before the browser can paint again.
    if (paint) for (const node of live) {
      // A running color/filter transition would otherwise bake an intermediate
      // selected or previous-theme frame into the permanent evidence image.
      const transition=node.style.getPropertyValue('transition'),priority=node.style.getPropertyPriority('transition');
      node.style.setProperty('transition','none','important');
      restore.push(()=>{if(transition)node.style.setProperty('transition',transition,priority);else node.style.removeProperty('transition');});
      for (const name of ['av-selected', 'av-related', 'av-review-target']) if (node.classList.contains(name)) {
        node.classList.remove(name); restore.push(() => node.classList.add(name));
      }
      for (const name of ['data-av-item-selected', 'data-av-inspected', 'aria-pressed']) if (node.hasAttribute(name)) {
        const value = node.getAttribute(name)!; node.removeAttribute(name);
        restore.push(() => node.setAttribute(name, value));
      }
    }
    for (let i = 0; i < live.length; i++) {
      const node = clones[i], computed = paint ? view?.getComputedStyle?.(live[i]) : null;
      for (const name of paintProperties) {
        let value = computed?.getPropertyValue(name).trim();
        if (value) {
          value = value.replace(/url\(["']?([^"')]+)["']?\)/g, (match, reference: string) => {
            try {
              const url = new URL(reference, element.ownerDocument.baseURI), base = new URL(element.ownerDocument.baseURI);
              return url.hash && url.origin === base.origin && url.pathname === base.pathname && url.search === base.search ? `url("${url.hash}")` : match;
            } catch { return match; }
          });
          validateExportCss(value); node.style.setProperty(name, value);
        }
      }
      for(const name of ['--av-item-base-filter','--av-item-filter-chain'])node.style.removeProperty(name);
      for (const name of ['tabindex', 'aria-pressed', 'data-av-item-selected', 'data-av-inspected']) node.removeAttribute(name);
      for (const name of ['av-selected', 'av-related', 'av-review-target']) node.classList.remove(name);
      if (node.hasAttribute('data-av-row-center')) { node.removeAttribute('transform'); node.style.removeProperty('transform'); }
    }
  } finally { for (const undo of restore.reverse()) undo(); }
  if (paint && view?.getComputedStyle) {
    // All used declarations (including HTML label layout) are now inline. Keep
    // font faces separately; never remove unresolved *active* paint references.
    for (const style of Array.from(copy.querySelectorAll('style'))) style.remove();
  }
  for (const ui of Array.from(copy.querySelectorAll('[data-av-review-ui]'))) ui.remove();
  for (const name of ['width','height','min-width','max-width','min-height','max-height','transform']) copy.style.removeProperty(name);
  copy.removeAttribute('preserveAspectRatio'); validateExportTree(copy); return copy;
}
function sceneBounds(scene: SVGElement): {width:number;height:number} {
  const box=(scene.getAttribute('viewBox')||'').split(/[ ,]+/).map(Number);
  const width=Number.parseFloat(scene.getAttribute('width')||'') || (box.length===4?box[2]:0), height=Number.parseFloat(scene.getAttribute('height')||'') || (box.length===4?box[3]:0);
  if (!(width>0 && height>0 && Number.isFinite(width+height))) throw new Error('The figure has no complete export bounds.');
  return {width,height};
}
async function rasterScene(figure:HTMLElement):Promise<SVGElement|null> {
  const document=figure.ownerDocument,adapter=visualAdapter(figure),image=figure.querySelector<HTMLImageElement>('img[data-av-zoom-target]'),canvas=figure.querySelector<HTMLCanvasElement>('canvas[data-av-zoom-target]');
  let width=0,height=0,src='';
  if(adapter?.png){const bounds=adapter.bounds(figure);width=bounds.width;height=bounds.height;const blob=await adapter.png(figure);if(blob.type!=='image/png')throw new Error('The adapter must return a PNG image.');const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';for(let start=0;start<bytes.length;start+=8192)binary+=String.fromCharCode(...bytes.subarray(start,start+8192));src='data:image/png;base64,'+btoa(binary);}
  else if(image||canvas){width=image?.naturalWidth||canvas?.width||0;height=image?.naturalHeight||canvas?.height||0;if(!(width>0&&height>0))throw new Error('The image is not loaded yet.');if(image){const snapshot=document.createElement('canvas');snapshot.width=width;snapshot.height=height;const context=snapshot.getContext('2d');if(!context)throw new Error('Image conversion is unavailable. Keep the original embedded image.');context.drawImage(image,0,0);src=snapshot.toDataURL('image/png');}else src=canvas!.toDataURL('image/png');}
  else return null;
  if(!(width>0&&height>0&&Number.isFinite(width+height))||!src.startsWith('data:image/png;base64,'))throw new Error('The adapter returned an unavailable image or invalid bounds.');
  const scene=document.createElementNS(SVG_NS,'svg');scene.setAttribute('width',String(width));scene.setAttribute('height',String(height));scene.setAttribute('viewBox',`0 0 ${width} ${height}`);const bitmap=document.createElementNS(SVG_NS,'image');bitmap.setAttribute('href',src);bitmap.setAttribute('width',String(width));bitmap.setAttribute('height',String(height));scene.appendChild(bitmap);return scene;
}
export async function exportFigureSvg(figure: HTMLElement): Promise<string> {
  const diagram=figure.querySelector('[data-av-mermaid]');if(diagram&&diagram.getAttribute('data-av-mermaid-state')!=='ready')throw new Error('The diagram is not ready for image export. Its original source remains available.');
  const document=figure.ownerDocument,custom=visualAdapter(figure)?.svg;
  let scene:SVGElement|null=null;
  if(custom){const template=document.createElement('template');template.innerHTML=await custom(figure);scene=template.content.querySelector('svg');if(!scene)throw new Error('The adapter did not return an SVG image.');validateExportTree(scene);}
  else scene=figure.querySelector<SVGElement>('svg[data-av-zoom-target]')||figure.querySelector<SVGElement>('[data-av-figure-body] svg')||await rasterScene(figure);
  if(!scene)throw new Error('Image export is unavailable for this visualization. Use its original source.');
  const {width,height}=sceneBounds(scene),row=custom?null:figure.querySelector<SVGElement>('[data-av-axis-layer="rows"]'),axis=custom?null:figure.querySelector<SVGElement>('[data-av-axis-layer="x"]');
  const rowWidth=row?sceneBounds(row).width:0,axisHeight=axis?sceneBounds(axis).height:0,totalWidth=width+rowWidth,padding=20;
  const context:string[]=[figureTitle(figure)],legends:{key:SVGElement|null;glyph:HTMLElement|null;label:string;lines:string[];height:number}[]=[];
  for(const node of figureContext(figure)){
    if(node.matches('.av-legend')){
      const items=node.tagName.toLowerCase()==='ul'?Array.from(node.children):[];
      if(items.length)for(const item of items){const key=item.querySelector<SVGElement>('svg'),label=item.querySelector('span')?.textContent||item.textContent||'';const lines=wrapText(label,{maxWidth:Math.max(totalWidth,160)-32,fontSize:14,lineHeight:21}).lines;legends.push({key,glyph:null,label,lines,height:Math.max(20,lines.length*21)+8});}
      else{let glyph:HTMLElement|null=null,text='';const push=()=>{if(!glyph&&!text.trim())return;const lines=wrapText(text.trim(),{maxWidth:Math.max(totalWidth,160)-32,fontSize:14,lineHeight:21}).lines;legends.push({key:null,glyph,label:text.trim(),lines,height:Math.max(20,lines.length*21)+8});};for(const child of Array.from(node.childNodes)){if(child.nodeType===1){push();glyph=child as HTMLElement;text='';}else text+=child.textContent||'';}push();}
      continue;
    }
    const text=node.textContent?.trim();if(text&&!context.includes(text))context.push(text);
  }
  const scope=figureOrigin(figure).scope;
  if(scope)context.push(scope.getAttribute('data-av-coordinate-scope')==='complete'?'Complete coordinate pairs only':'All supplied known coordinates determine the scale');
  const lines=context.flatMap(text=>wrapText(text,{maxWidth:Math.max(totalWidth,160),fontSize:14,lineHeight:21}).lines),headingHeight=lines.length*21+16+legends.reduce((height,item)=>height+item.height,0),exportWidth=Math.max(totalWidth,160)+padding*2;
  const root=document.createElementNS(SVG_NS,'svg');root.setAttribute('xmlns',SVG_NS);root.setAttribute('xmlns:xlink','http://www.w3.org/1999/xlink');root.setAttribute('width',String(exportWidth));root.setAttribute('height',String(height+axisHeight+headingHeight+padding*2));root.setAttribute('viewBox',`0 0 ${exportWidth} ${height+axisHeight+headingHeight+padding*2}`);
  const probe=document.createElement('span');probe.setAttribute('data-av-review-ui','');figure.appendChild(probe);const color=(token:string,fallback:string)=>{probe.style.setProperty('color',`var(${token})`);const value=document.defaultView?.getComputedStyle?.(probe).color;return value&&!value.includes('var(')?value:fallback;};const ink=color('--av-ink','#172032'),paper=color('--av-plot','#ffffff');probe.remove();
  const rect=document.createElementNS(SVG_NS,'rect');rect.setAttribute('width','100%');rect.setAttribute('height','100%');rect.setAttribute('fill',paper);root.appendChild(rect);
  const title=document.createElementNS(SVG_NS,'title');title.textContent=context[0];root.appendChild(title);
  lines.forEach((line,index)=>{const text=document.createElementNS(SVG_NS,'text');text.setAttribute('x',String(padding));text.setAttribute('y',String(padding+14+index*21));text.setAttribute('fill',ink);text.setAttribute('font-family','sans-serif');text.setAttribute('font-size','14');text.textContent=line;root.appendChild(text);});
  let legendY=padding+lines.length*21+10;
  for(const item of legends){
    if(item.key){const key=paintedClone(item.key);key.setAttribute('x',String(padding));key.setAttribute('y',String(legendY));key.setAttribute('width','20');key.setAttribute('height','20');root.appendChild(key);}
    else if(item.glyph){const text=document.createElementNS(SVG_NS,'text');text.setAttribute('x',String(padding));text.setAttribute('y',String(legendY+15));text.setAttribute('fill',document.defaultView?.getComputedStyle?.(item.glyph).color||ink);text.textContent=item.glyph.textContent;root.appendChild(text);}
    item.lines.forEach((line,index)=>{const text=document.createElementNS(SVG_NS,'text');text.setAttribute('x',String(padding+30));text.setAttribute('y',String(legendY+15+index*21));text.setAttribute('fill',ink);text.setAttribute('font-family','sans-serif');text.setAttribute('font-size','14');text.textContent=line;root.appendChild(text);});legendY+=item.height;
  }
  const append=(svg:SVGElement,x:number,y:number,paint=true)=>{const copy=paintedClone(svg,paint),bounds=sceneBounds(svg);copy.setAttribute('width',String(bounds.width));copy.setAttribute('height',String(bounds.height));copy.setAttribute('x',String(padding+x));copy.setAttribute('y',String(padding+headingHeight+y));root.appendChild(copy);};
  if(axis)append(axis,rowWidth,0);if(row)append(row,0,axisHeight);append(scene,rowWidth,axisHeight,!custom&&figure.contains(scene));
  // The SVG carries any embedded fonts used by the report's computed text styles.
  const fontRules:string[]=[];
  for(const sheet of Array.from(document.styleSheets||[])){
    try { for(const rule of Array.from(sheet.cssRules))if(rule.type===5){validateExportCss(rule.cssText);fontRules.push(rule.cssText);} }
    catch(error){if(error instanceof Error&&error.name==='SecurityError')throw new Error('An export font stylesheet is inaccessible. Embed the report fonts before exporting.');throw error;}
  }
  if(fontRules.length){const style=document.createElementNS(SVG_NS,'style');style.textContent=fontRules.join('\n');root.insertBefore(style,root.firstChild);}
  validateExportTree(root);
  return serialize(root);
}
export async function exportFigurePng(figure: HTMLElement): Promise<Blob> {
  const svg=await exportFigureSvg(figure),document=figure.ownerDocument,ImageType=document.defaultView?.Image;
  if(!ImageType)throw new Error('PNG conversion is unavailable. Download SVG or source.');
  const image=new ImageType();image.decoding='async';
  await new Promise<void>((resolve,reject)=>{
    let done=false;
    const finish=(error?:Error)=>{if(done)return;done=true;clearTimeout(timer);image.onload=null;image.onerror=null;if(error){image.removeAttribute('src');reject(error);}else resolve();};
    const timer=setTimeout(()=>finish(new Error('PNG conversion timed out. Download SVG or source for the complete figure.')),20000);
    image.onload=()=>finish();image.onerror=()=>finish(new Error('This browser cannot rasterize the complete figure. Download SVG or source.'));
    image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
  });
  if (!image.naturalWidth || !image.naturalHeight || image.naturalWidth > 32767 || image.naturalHeight > 32767 || image.naturalWidth * image.naturalHeight > 64000000) throw new Error('The complete figure is too large for a reliable PNG in this browser. Download SVG for the full-resolution drawing.');
  const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
  try{
    const context=canvas.getContext('2d');if(!context)throw new Error('PNG conversion is unavailable. Download SVG or source.');
    context.drawImage(image,0,0);
    return await new Promise<Blob>((resolve,reject)=>{
      let done=false;const finish=(blob:Blob|null,error?:unknown)=>{if(done)return;done=true;clearTimeout(timer);if(blob)resolve(blob);else reject(error instanceof Error?error:new Error('The full image exceeds this browser’s export capacity. Download SVG or source.'));};
      const timer=setTimeout(()=>finish(null,new Error('PNG encoding timed out. Download SVG or source.')),20000);
      try{canvas.toBlob(blob=>finish(blob),'image/png');}catch(error){finish(null,error);}
    });
  }finally{canvas.width=0;canvas.height=0;image.removeAttribute('src');}

}
export function downloadBlob(document: Document, blob: Blob, name: string): void {
  const URLType=document.defaultView?.URL;if(!URLType?.createObjectURL)throw new Error('Downloads are unavailable in this browser.');
  const url=URLType.createObjectURL(blob),link=document.createElement('a');let dispatched=false;
  try{link.href=url;link.download=name;link.hidden=true;link.setAttribute('data-av-review-ui','');link.setAttribute('data-av-internal-download','');document.body.appendChild(link);link.click();dispatched=true;}
  finally{link.remove();if(dispatched)(document.defaultView?.setTimeout||setTimeout)(()=>URLType.revokeObjectURL(url),60000);else URLType.revokeObjectURL(url);}
}
export async function copyFigureImage(figure: HTMLElement): Promise<void> {
  const view=figure.ownerDocument.defaultView,Clipboard=(view as unknown as {ClipboardItem?:typeof ClipboardItem})?.ClipboardItem;
  if(!view?.navigator?.clipboard?.write||!Clipboard)throw new Error('Image copying is unavailable here. Download PNG or SVG instead.');
  await view.navigator.clipboard.write([new Clipboard({'image/png':exportFigurePng(figure)})]);
}
export async function copyFigureSource(figure: HTMLElement): Promise<void> {
  const source=figureSource(figure);if(!source)throw new Error('No original source was supplied for this visualization.');
  const clipboard=figure.ownerDocument.defaultView?.navigator?.clipboard;if(!clipboard?.writeText)throw new Error('Clipboard access is unavailable. Select the source text and copy it, or download it.');
  await clipboard.writeText(source.text);
}
