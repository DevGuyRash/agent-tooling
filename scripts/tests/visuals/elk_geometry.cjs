// Actual bundled ELK numerical layouts and shared routing; no native drawing.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root = path.resolve(__dirname, '../../..');
const { repairElkLayout } = require(path.resolve(process.argv[2], 'elk-layout.js'));
let source = fs.readFileSync(path.join(root, 'plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js'), 'utf8');
const marker = 'getRegisteredDiagramsMetadata:Mzi';
assert.equal(source.split(marker).length, 2);
source = source.replace(marker, 'numericElkUnits(){PAr();return{ELK:wAr.default,run:Qai,apply:Jai}},' + marker);
const context = vm.createContext({ console: { log() {}, warn() {}, error() {} }, structuredClone, setTimeout, clearTimeout, setInterval, clearInterval, performance, TextEncoder, TextDecoder, URL });
vm.runInContext('globalThis.global=globalThis;', context);
vm.runInContext(source, context, { timeout: 20000 });
context.mermaid.initialize({ startOnLoad: false });
const units = context.mermaid.numericElkUnits(), elk = new units.ELK();
const cleanup = () => { if (typeof elk.worker?.worker?.terminate === 'function') elk.terminateWorker(); };
const log = { debug() {}, error() {}, info() {}, warn() {} };
// ELK's bundled GWT bridge uses realm-local Array checks. JSON transport gives
// the numerical engine the same realm-local input it receives in the report.
const localGraph = graph => { context.numericInput = JSON.stringify(graph); return vm.runInContext('JSON.parse(numericInput)', context); };
const numericLayout = graph => elk.layout(localGraph(graph));
const ids = ['intake','validate','parse','missing','render','review','audit','export','handoff'];
function input(algorithm) {
  return { id: 'root', layoutOptions: { 'elk.algorithm': algorithm, 'elk.direction': 'RIGHT', 'spacing.baseValue': 40 },
    children: ids.map(id => ({ id, width: id === 'validate' ? 190 : 160, height: id === 'validate' ? 190 : 96 })),
    edges: [
      ['intake','validate'], ['validate','parse','yes'], ['validate','missing','no'], ['parse','render'],
      ['missing','render'], ['render','review'], ['parse','audit'], ['review','export'], ['audit','export'],
      ['export','handoff'], ['handoff','validate','feedback loop'],
    ].map(([from,to,text], i) => ({ id: 'relationship-'+i, sources:[from], targets:[to],
      ...(text ? { labels:[{text, width:text.length*8, height:22}] } : {}) })) };
}
const points = edge => { const s=edge.sections?.[0]; return s?[s.startPoint,...(s.bendPoints||[]),s.endPoint]:[]; };
const overlap = (a,b) => a.x < b.x+b.width && a.x+a.width > b.x && a.y < b.y+b.height && a.y+a.height > b.y;
// Independent segment/box intersection: clamp the entry/exit parameter for
// each axis, excluding boundary contact. Tests do not import the repair's predicate.
function crosses(a,b,box) {
  let entry=0,exit=1;
  for(const key of ['x','y']) {
    const d=b[key]-a[key],lo=box[key]+1e-5,hi=box[key]+box[key==='x'?'width':'height']-1e-5;
    if(!d){if(a[key]<lo||a[key]>hi)return false;}
    else {const p=(lo-a[key])/d,q=(hi-a[key])/d;entry=Math.max(entry,Math.min(p,q));exit=Math.min(exit,Math.max(p,q));}
  }
  return entry <= exit;
}
function inspect(graph) {
  let nodeOverlaps=0,obstructions=0,labelOverlaps=0,missingRoutes=0;
  const labels=graph.edges.flatMap(edge=>(edge.labels||[]).map(label=>({edge,label})));
  for(let i=0;i<graph.children.length;i++)for(let j=i+1;j<graph.children.length;j++)if(overlap(graph.children[i],graph.children[j]))nodeOverlaps++;
  for(const edge of graph.edges) {
    const route=points(edge);if(route.length<2){missingRoutes++;continue;}
    for(const node of graph.children)if(![edge.sources[0],edge.targets[0]].includes(node.id))
      if(route.slice(1).some((p,i)=>crosses(route[i],p,node)))obstructions++;
    for(const {edge:other,label} of labels)if(other!==edge&&Number.isFinite(label.x)&&Number.isFinite(label.y))
      if(route.slice(1).some((p,i)=>crosses(route[i],p,label)))obstructions++;
  }
  for(let i=0;i<labels.length;i++) {
    const box=labels[i].label;
    if(!Number.isFinite(box.x)||!Number.isFinite(box.y)){labelOverlaps++;continue;}
    if(graph.children.some(n=>overlap(box,n)))labelOverlaps++;
    for(let j=i+1;j<labels.length;j++)if(overlap(box,labels[j].label))labelOverlaps++;
  }
  return {nodeOverlaps,obstructions,labelOverlaps,missingRoutes};
}
const identity = graph => JSON.stringify({ nodes:graph.children.map(({id,width,height})=>({id,width,height})),
  edges:graph.edges.map(({id,sources,targets,labels})=>({id,sources,targets,labels:labels?.map(({text,width,height})=>({text,width,height}))})) });
function nativeAdapt(graph) {
  const data = {nodes:graph.children.map(node=>({...node,shape:node.id==='validate'?'question':'rect'})),
    edges:graph.edges.map(edge=>({...edge,start:edge.sources[0],end:edge.targets[0]})),config:{elk:{}}};
  const state={nodeDb:Object.fromEntries(data.nodes.map(node=>[node.id,{...node}])),parentLookupDb:{parentById:{},childrenById:{}}};
  units.apply(data,graph,state,log);
  return {children:data.nodes.map(node=>({...node,x:node.x-node.width/2,y:node.y-node.height/2})),
    edges:data.edges.map(edge=>({...edge,sections:[{startPoint:edge.points[0],endPoint:edge.points.at(-1),bendPoints:edge.points.slice(1,-1)}],
      labels:edge.labels?.map((label,i)=>({...label,...(i===0?{x:edge.x-label.width/2,y:edge.y-label.height/2}:{})}))}))};
}
(async()=>{
  const regressions=JSON.parse(fs.readFileSync(path.join(__dirname,'elk-routing-regressions.json'),'utf8'));
  const failures=[];
  for (let attempt=1;attempt<=3;attempt++) for (const fixture of regressions) {
    const graph=structuredClone(fixture.graph), original=identity(graph);
    const repaired=await repairElkLayout(graph,numericLayout);
    assert.equal(identity(repaired),original,fixture.name+': identities and measured labels survive');
    const afterRepair=inspect(repaired), afterNative=inspect(nativeAdapt(repaired));
    for (const [stage,result] of [['repair',afterRepair],['native adapter',afterNative]])
      if(Object.values(result).some(value=>value!==0))failures.push({fixture:fixture.name,attempt,stage,...result});
  }
  assert.deepEqual(failures,[],'Retained counterexamples must stay clear through the complete native adapter on three consecutive replays');
  const fixtures=JSON.parse(fs.readFileSync(path.join(__dirname,'mermaid-fixtures/index.json'),'utf8'));
  const algorithms=[...new Set(fixtures.map(f=>f.layout).filter(name=>name?.startsWith('elk')).map(name=>name==='elk'?'elk.layered':name))];
  let demonstrated=false;
  for(const algorithm of algorithms) {
    const raw=await numericLayout(input(algorithm)), before=inspect(raw), original=identity(raw);
    if(Object.values(before).some(n=>n>0))demonstrated=true;
    const repaired=await repairElkLayout(raw, numericLayout);
    assert.equal(identity(repaired),original,algorithm+': node/relationship identity, dimensions, labels and topology survive');
    assert.equal(repaired.layoutOptions['elk.algorithm'],algorithm, 'Requested algorithm identity is retained');
    assert.deepEqual(inspect(repaired),{nodeOverlaps:0,obstructions:0,labelOverlaps:0,missingRoutes:0},algorithm+': evidence must be unobscured');
    for(const edge of repaired.edges)for(const point of points(edge))assert(point.x>=0&&point.y>=0&&point.x<=repaired.width&&point.y<=repaired.height,algorithm+': complete route remains in canvas');
    const adapted=nativeAdapt(repaired);
    assert.deepEqual(inspect(adapted),{nodeOverlaps:0,obstructions:0,labelOverlaps:0,missingRoutes:0},algorithm+': the native adapter must preserve repaired route and label geometry');
    console.log(JSON.stringify({algorithm,before,after:inspect(repaired),width:repaired.width,height:repaired.height}));
  }
  assert(demonstrated,'At least one retained failure must be reproduced by the numeric fixture');
  const repeat=input('elk.box');
  repeat.edges.push({id:'parallel',sources:['validate'],targets:['parse'],labels:[{text:'separate qualifier λ',width:170,height:22}]},
    {id:'reciprocal',sources:['parse'],targets:['validate'],labels:[{text:'returns to original grounds',width:210,height:22}]},
    {id:'self-a',sources:['review'],targets:['review'],labels:[{text:'first loop',width:80,height:22}]},
    {id:'self-b',sources:['review'],targets:['review'],labels:[{text:'second loop',width:88,height:22}]});
  const repeated=await repairElkLayout(await numericLayout(repeat),numericLayout);
  assert.deepEqual(inspect(repeated),{nodeOverlaps:0,obstructions:0,labelOverlaps:0,missingRoutes:0});
  assert.equal(new Set(repeated.edges.map(edge=>JSON.stringify(points(edge)))).size,repeated.edges.length,'Parallel, reciprocal and self-loop relationships retain distinct routes');
  const nested={id:'root',children:[{id:'group',x:0,y:0,width:200,height:100,children:[]}],edges:[]};
  assert.equal(await repairElkLayout(nested,async()=>{throw Error('Compound geometry has a native owner');}),nested);
  const clean={id:'root',width:300,height:100,children:[{id:'a',x:0,y:0,width:50,height:50},{id:'b',x:150,y:0,width:50,height:50}],edges:[{id:'ab',sources:['a'],targets:['b'],sections:[{startPoint:{x:50,y:25},endPoint:{x:150,y:25}}]}]};
  const bytes=JSON.stringify(clean);await repairElkLayout(clean,async()=>{throw Error('Already sound layout needs no second pass');});assert.equal(JSON.stringify(clean),bytes);
  const nativeClean={id:'root',width:320,height:200,children:[{id:'a',x:0,y:0,width:80,height:80},{id:'b',x:240,y:120,width:80,height:80}],
    edges:[{id:'ab',sources:['a'],targets:['b'],sections:[{startPoint:{x:80,y:40},bendPoints:[{x:100,y:40},{x:100,y:50},{x:220,y:50},{x:220,y:160}],endPoint:{x:240,y:160}}]}]};
  const nativeBytes=JSON.stringify(nativeClean), originalRoute=points(nativeClean.edges[0]);
  await repairElkLayout(nativeClean,async()=>{throw Error('Sound native route needs no repair');});
  assert.equal(JSON.stringify(nativeClean),nativeBytes);
  const nativeResult=nativeAdapt(nativeClean);
  assert(points(nativeResult.edges[0]).length<originalRoute.length,'An unrepaired sound layout retains native terminal straightening');
  const residual=input('elk.stress');residual.children.forEach(node=>{node.x=0;node.y=0;});
  const residualIdentity=identity(residual);
  await repairElkLayout(residual,async graph=>graph); // The processor makes no separation progress.
  assert.equal(identity(residual),residualIdentity);
  assert.deepEqual(inspect(residual),{nodeOverlaps:0,obstructions:0,labelOverlaps:0,missingRoutes:0},'Residual/coincident boxes have a finite deterministic separation');
  let calls=0;const prior=context.mermaid.setElkLayoutPostprocessor(async(graph,layout)=>{calls++;return repairElkLayout(graph,value=>layout(localGraph(value)));});
  try{const integrated=await units.run(elk,localGraph(input('elk.box')),log);assert.equal(calls,1);assert.deepEqual(inspect(integrated),{nodeOverlaps:0,obstructions:0,labelOverlaps:0,missingRoutes:0});}
  finally{context.mermaid.setElkLayoutPostprocessor(prior);cleanup();}
  console.log('ELK geometry passed: measured obstacles/labels, exact topology, complete routes, loops/repeated links, scoped integration and unchanged sound/compound layouts.');
})().catch(error=>{cleanup();console.error(error);process.exitCode=1});
