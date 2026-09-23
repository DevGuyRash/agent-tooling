import { exactJson } from './exact-json';
import { readerTimestamp } from './reader-values';
import { ReviewAnchor, ReviewTarget, ReviewItem } from './review-types';
export interface AnnotationVersion { id: string; annotationId: string; anchor: ReviewAnchor; text: string | null; at: string; draft: boolean; baseIds?: readonly string[] }
export interface ReviewRecords { versions: readonly AnnotationVersion[]; bookmarks: readonly ReviewAnchor[]; supportingVersions?: readonly AnnotationVersion[] }
export type ReviewChange = { type:'annotation'; version: AnnotationVersion; observedIds: readonly string[]; supportingVersions?: readonly AnnotationVersion[] } | { type:'review-bookmark'; anchor: ReviewAnchor; enabled:boolean };
export const emptyReviewRecords=():ReviewRecords=>({versions:[],bookmarks:[]});
function object(value:unknown,fields:string[]):Record<string,unknown>{if(!value||typeof value!=='object'||Array.isArray(value)||(Object.getPrototypeOf(value)!==Object.prototype&&Object.getPrototypeOf(value)!==null))throw new Error('Review data must be a plain object.');for(const key of Reflect.ownKeys(value)){if(typeof key!=='string'||!fields.includes(key)||!('value'in Object.getOwnPropertyDescriptor(value,key)!))throw new Error('Review data contains an unsupported field.');}return value as Record<string,unknown>;}
function array(value:unknown):unknown[]{if(!Array.isArray(value)||Object.getPrototypeOf(value)!==Array.prototype||Reflect.ownKeys(value).length!==value.length+1)throw new Error('Review arrays must contain only plain data.');const items:unknown[]=[];for(let i=0;i<value.length;i++){const item=Object.getOwnPropertyDescriptor(value,String(i));if(!item||!('value'in item)||!item.enumerable)throw new Error('Review arrays must contain only plain data.');items.push(item.value);}return items;}
function text(value:unknown):string{if(typeof value!=='string')throw new Error('Review text must be a string.');return value;}
export function validateAnchor(value:unknown):ReviewAnchor{
  const a=object(value,['kind','target','quote','prefix','suffix','start','end','itemId','label','text','values','items']),t=object(a.target,['reportId','revision','id','label','path','fingerprint','excerpt','ambiguous','sources']);
  if(!array(t.path).every(item=>typeof item==='string'))throw new Error('Review context path is invalid.');
  const target:ReviewTarget={reportId:text(t.reportId),revision:text(t.revision),id:text(t.id),label:text(t.label),path:array(t.path).map(text),fingerprint:text(t.fingerprint),excerpt:text(t.excerpt),...(t.ambiguous===true?{ambiguous:true}:{})};
  if(t.ambiguous!==undefined&&typeof t.ambiguous!=='boolean')throw new Error('Invalid ambiguous target flag.');
  if(t.sources!==undefined)target.sources=array(t.sources).map(value=>{const source=object(value,['label','href']);return{label:text(source.label),href:text(source.href)};});
  if(!target.id||!target.fingerprint||!target.reportId||!target.revision)throw new Error('Review identity is missing.');
  if(a.kind==='section'||a.kind==='figure')return{kind:a.kind,target};
  if(a.kind==='text'){if(typeof a.quote!=='string'||!a.quote.length)throw new Error('A text annotation needs its exact nonempty quotation.');if(!Number.isSafeInteger(a.start)||!Number.isSafeInteger(a.end)||Number(a.start)<0||Number(a.end)-Number(a.start)!==a.quote.length)throw new Error('Review text offsets are invalid.');return{kind:'text',target,quote:text(a.quote),prefix:text(a.prefix),suffix:text(a.suffix),start:Number(a.start),end:Number(a.end)};}
  const item = (value: unknown): ReviewItem => {
    const data = object(value, ['itemId', 'label', 'text', 'values']);
    if (!text(data.itemId)) throw new Error('An item annotation needs its original item identity.');
    const result: ReviewItem = {itemId:text(data.itemId), label:text(data.label), text:text(data.text)};
    if (data.values !== undefined) {
      const values = object(data.values, Object.keys(data.values as object));
      if (!Object.values(values).every(value => value === null || typeof value === 'string' || typeof value === 'number' && Number.isFinite(value))) throw new Error('Review item values are invalid.');
      result.values = {...values} as Record<string,string|number|null>;
    }
    return result;
  };
  if (a.kind === 'item') return {kind:'item', target, ...item({itemId:a.itemId,label:a.label,text:a.text,...(a.values === undefined ? {} : {values:a.values})})};
  if (a.kind === 'items') {
    const items = array(a.items).map(item);
    if (items.length < 2 || new Set(items.map(item => item.itemId)).size !== items.length) throw new Error('A group annotation needs two or more distinct item identities.');
    return {kind:'items', target, items};
  }
  throw new Error('Unknown review anchor. Use section, figure, text, item or items.');
}
export function validateReview(value:unknown):ReviewRecords{
  const record=object(value,['versions','bookmarks','supportingVersions']);if(!Array.isArray(record.versions)||!Array.isArray(record.bookmarks))throw new Error('Review records are invalid.');
  const ids=new Set<string>(),version=(item:unknown):AnnotationVersion=>{const v=object(item,['id','annotationId','anchor','text','at','draft','baseIds']);const id=text(v.id),annotationId=text(v.annotationId),at=readerTimestamp(v.at,'Annotation timestamp');if(!id||!annotationId||ids.has(id)||typeof v.draft!=='boolean')throw new Error('Review version identity or timestamp is invalid.');if(v.baseIds!==undefined&&!array(v.baseIds).every(id=>typeof id==='string'))throw new Error('Annotation draft bases are invalid.');ids.add(id);return{id,annotationId,anchor:validateAnchor(v.anchor),text:v.text===null?null:text(v.text),at,draft:v.draft,...(v.baseIds?{baseIds:array(v.baseIds).map(text)}:{})};};
  const versions=array(record.versions).map(version),supportingVersions=record.supportingVersions===undefined?[]:array(record.supportingVersions).map(version);
  if(supportingVersions.some(item=>item.draft))throw new Error('Supporting annotation context must be a saved version.');
  const retainedDraftBases=new Map<string,Set<string>>();for(const item of versions)if(item.draft){const bases=retainedDraftBases.get(item.annotationId)||new Set<string>();for(const id of item.baseIds||[])bases.add(id);retainedDraftBases.set(item.annotationId,bases);}
  for(const supporting of supportingVersions)if(!retainedDraftBases.get(supporting.annotationId)?.has(supporting.id))throw new Error('Supporting annotation context must belong to a retained draft base.');
  const bookmarks=array(record.bookmarks).map(validateAnchor);if(new Set(bookmarks.map(a=>exactJson(a))).size!==bookmarks.length)throw new Error('Duplicate review bookmark.');return{versions,bookmarks,...(supportingVersions.length?{supportingVersions}:{})};
}
export function applyReview(source:ReviewRecords,change:ReviewChange):ReviewRecords{
  const prior=validateReview(source);
  if(change.type==='review-bookmark'){const anchor=validateAnchor(change.anchor),key=exactJson(anchor),bookmarks=prior.bookmarks.filter(item=>exactJson(item)!==key);if(change.enabled)bookmarks.push(anchor);return{...prior,bookmarks};}
  const input=validateReview({versions:[change.version],bookmarks:[]}).versions[0],observed=new Set(array(change.observedIds).map(text)),priorVersions=[...prior.versions,...(prior.supportingVersions||[])],priorById=new Map(priorVersions.map(item=>[item.id,item]));
  const withoutBases=(item:AnnotationVersion)=>{const{baseIds,...content}=item;return content;};
  const supplied=change.supportingVersions===undefined?[]:array(change.supportingVersions).map(item=>validateReview({versions:[item],bookmarks:[]}).versions[0]);
  for(const base of supplied){
    if(base.draft||base.annotationId!==input.annotationId||!observed.has(base.id))throw new Error('Supporting annotation context must be a referenced saved version of this annotation.');
    const existingBase=priorById.get(base.id);
    if(existingBase&&exactJson(withoutBases(existingBase))!==exactJson(withoutBases(base)))throw new Error('Supporting annotation identity conflicts with saved content.');
    if(!existingBase)priorById.set(base.id,base);
  }
  const bases=new Set(input.baseIds||[]);
  if(!input.draft)for(const id of observed){
    if(id===input.id)continue;
    const base=priorById.get(id);
    if(base&&base.annotationId!==input.annotationId)continue;
    bases.add(id);
    if(base)for(const ancestor of base.baseIds||[])bases.add(ancestor);
  }
  bases.delete(input.id);
  const version:AnnotationVersion={...input,...(bases.size?{baseIds:[...bases]}:{})};
  const existing=priorById.get(version.id);
  if(existing){
    if(exactJson(withoutBases(existing))!==exactJson(withoutBases(version)))throw new Error('Annotation version identity conflicts with saved content.');
    return prior;
  }
  const versions=[...prior.versions.filter(item=>item.annotationId!==version.annotationId||!observed.has(item.id)||(version.draft&&!item.draft)),version],activeIds=new Set(versions.map(item=>item.id)),supporting:AnnotationVersion[]=[],supportingIds=new Set<string>();
  for(const draft of versions)if(draft.draft)for(const id of draft.baseIds||[]){if(activeIds.has(id)||supportingIds.has(id))continue;const base=priorById.get(id);if(base&&!base.draft&&base.annotationId===draft.annotationId){supporting.push(base);supportingIds.add(id);}}
  const{supportingVersions:_priorSupporting,...record}=prior;return{...record,versions,...(supporting.length?{supportingVersions:supporting}:{})};
}
