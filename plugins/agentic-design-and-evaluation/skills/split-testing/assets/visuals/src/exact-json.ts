/** JSON syntax can represent -0 even though JSON.stringify normally erases its
 * sign. Preserve it in evidence/reader records without a new wire schema, magic
 * object fields, or replacements inside evidence strings. Ordinary JSON output
 * is byte-identical. Callers still validate their own supported data contracts.
 */
export function exactJson(value: unknown): string {
  let signedZero=false;
  const ordinary=JSON.stringify(value,(_key,item)=>{if(Object.is(item,-0))signedZero=true;return item;});
  if(ordinary===undefined)throw new TypeError('This value has no JSON representation.');
  if(!signedZero)return ordinary;
  let marker='\u0000av-negative-zero';
  while(ordinary.includes(JSON.stringify(marker).slice(1,-1)))marker+='-';
  return JSON.stringify(value,(_key,item)=>Object.is(item,-0)?marker:item).split(JSON.stringify(marker)).join('-0');
}
