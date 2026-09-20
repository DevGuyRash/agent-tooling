/** Bounded export validation: self-contained SVG, raster data and local paint references. */
const raster = /^data:image\/(?:png|jpeg|gif|webp|avif);base64,[a-z0-9+/=\s]+$/i;
const font = /^data:(?:font\/[a-z0-9.+-]+|application\/(?:font-woff|vnd.ms-fontobject|x-font-ttf|x-font-opentype|octet-stream));base64,[a-z0-9+/=\s]+$/i;
export function exportReference(value: string, fonts = false): boolean {
  return !value || /^#[^\s]*$/.test(value) || raster.test(value) || (fonts && font.test(value));
}
// Decode CSS escapes for dependency checks. Retain original bytes for output.
export function validateExportCss(value: string): void {
  const decoded = value.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\\([0-9a-f]{1,6})(?:\r\n|[ \t\r\n\f])?|\\([^\r\n\f])/gi, (_match, hex, char) => hex ? String.fromCodePoint(Math.min(parseInt(hex,16) || 0xfffd,0x10ffff)) : char);
  if (/@import\b|(?:image-set|image|src|expression|paint)\s*\(|-moz-binding|behavior\s*:/i.test(decoded)) throw new Error('This export style uses a resource or active feature that cannot be embedded. Download source or supply a self-contained image.');
  const urls = decoded.matchAll(/url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*))\s*\)/gi);
  for (const match of urls) if (!exportReference((match[1] ?? match[2] ?? match[3]).trim(), true)) throw new Error('Embed the figure’s external style resources before exporting it.');
  if ((decoded.match(/url\s*\(/gi)||[]).length !== [...decoded.matchAll(/url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*))\s*\)/gi)].length) throw new Error('The export contains an unsupported CSS resource expression.');
}
export function validateExportTree(svg: SVGElement): void {
  const ids=new Set([svg,...Array.from(svg.querySelectorAll('[id]'))].map(node=>node.id));
  const local=(value:string)=>{for(const match of value.matchAll(/url\(["']?#([^"')]+)["']?\)/gi))if(!ids.has(match[1]))throw new Error('An export paint or marker belongs outside this figure. Include its definition in the figure or adapter snapshot.');};
  for (const element of [svg,...Array.from(svg.querySelectorAll<Element>('*'))]) {
    const tag = (element.localName||element.tagName).split(':').pop()!.toLowerCase();
    if (['script','iframe','object','embed','link','base','meta','form','input','button','audio','video','animate','animatetransform','animatemotion','set'].includes(tag)) throw new Error('This figure needs a static, self-contained export from its adapter. Source remains available.');
    if (tag === 'style') {validateExportCss(element.textContent || '');local(element.textContent||'');}
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.split(':').pop()!.toLowerCase(), value = attribute.value;
      if(name==='base')throw new Error('An export cannot redefine its resource base. Remove xml:base and embed the figure resources.');
      if (/^on/.test(name)) { element.removeAttribute(attribute.name); continue; }
      if (['href','xlink:href','src'].includes(name)) {
        if (tag === 'a') { element.removeAttribute(attribute.name); continue; }
        if(value.startsWith('#')&&!ids.has(value.slice(1)))throw new Error('A referenced image or symbol is outside this figure. Include it in the adapter snapshot.');
        if (!exportReference(value)) throw new Error('Embed the figure’s external resources before exporting it.');
      }
      if (name === 'srcset') throw new Error('Use one embedded image for export.');
      if (name === 'style' || ['fill','stroke','filter','clip-path','mask','marker','marker-start','marker-mid','marker-end','cursor','color-profile'].includes(name)) {validateExportCss(value);local(value);}
    }
  }
}
