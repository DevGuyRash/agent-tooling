// Actual bundled constraint and numerical fcose engines, without SVG, DOM or a browser.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const root = path.resolve(__dirname, '../../..');
const { routeArchitectureConnection } = require(path.resolve(process.argv[2], 'architecture-layout.js'));
let source = fs.readFileSync(path.join(root, 'plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js'), 'utf8');
const hook = 'i(pLi,"layoutArchitecture");';
assert.equal(source.split(hook).length, 2, 'Pinned numeric test access must be unique');
source = source.replace(hook, hook + 'globalThis.avArchitectureUnits={cytoscape:c3,align:fLi,relative:dLi,seed:B0t,groups:uLi,services:oLi,junctions:lLi,edges:hLi,endpoint:Xse.manualEndptToPx,groupEndpoint:avArchitectureGroupEndpoint,measureCaption:avArchitectureMeasureCaption,measureEdgeWidth:avArchitectureMeasureEdgeWidth,drawEdges:atn,drawGroups:stn};');
const context = vm.createContext({ console: { log() {}, warn() {}, error() {} }, structuredClone, setTimeout, clearTimeout, setInterval, clearInterval, performance, TextEncoder, TextDecoder, URL });
vm.runInContext(source, context, { timeout: 20000 });
context.mermaid.initialize({ startOnLoad: false });
context.mermaid.setArchitectureRouter(routeArchitectureConnection);
(async () => {
  const original = fs.readFileSync(path.join(__dirname, 'mermaid-fixtures/architecture.mmd'), 'utf8');
  const diagram = await context.mermaid.mermaidAPI.getDiagramFromText(original);
  const db = diagram.db, units = context.avArchitectureUnits;
  for(const stroke of [3,12]) {
    let removed=0;
    const probe={attr(){return this;},node(){return{ownerDocument:{defaultView:{getComputedStyle:()=>({strokeWidth:stroke+'px'})}}};},remove(){removed++;}};
    assert.equal(units.measureEdgeWidth({append:()=>probe}),stroke,'Connection spacing uses the actual themed stroke');
    assert.equal(removed,1,'The edge-style probe releases its temporary SVG node');
    const service={},label={attr(){return this;},node(){return{getBBox:()=>({x:-50,y:3,width:100,height:44})};}};
    units.measureCaption(label,service,80,stroke);
    assert(service.avCaptionBounds.y-80>stroke+2,'A short native glyph gap leaves room for the complete painted connection');
    assert.equal(service.avCaptionBounds.width,100,'Spacing does not shrink or truncate a caption');
  }
  const { spatialMaps, groupAlignments } = db.getDataStructures();
  const hints = db.getLayoutHints(), alignments = units.align(db, spatialMaps, groupAlignments, hints);
  context.unitDb = db; context.units = units; context.alignments = alignments;
  const layoutProbe = `(() => {
    const cy = units.cytoscape({headless:true,styleEnabled:true,style:[
      {selector:'.node-service,.node-junction',style:{width:'data(width)',height:'data(height)'}},
      {selector:'.node-group',style:{padding:unitDb.getConfigField('padding')+'px'}}]});
    try {
      units.groups(unitDb.getGroups(),cy); units.services(unitDb.getServices(),cy,unitDb);
      units.junctions(unitDb.getJunctions(),cy,unitDb); units.edges(unitDb.getEdges(),cy);
      const icon = unitDb.getConfigField('iconSize');
      const layout = cy.layout({name:'fcose',quality:'proof',randomize:unitDb.getConfigField('randomize'),
        nodeSeparation:unitDb.getConfigField('nodeSeparation'),numIter:unitDb.getConfigField('numIter'),
        animate:false,nodeDimensionsIncludeLabels:false,
        idealEdgeLength(edge){const [a,b]=edge.connectedNodes();return a.data('parent')===b.data('parent')?unitDb.getConfigField('idealEdgeLengthMultiplier')*icon:.5*icon;},
        edgeElasticity(edge){const [a,b]=edge.connectedNodes();return a.data('parent')===b.data('parent')?unitDb.getConfigField('edgeElasticity'):.001;},
        alignmentConstraint:alignments,relativePlacementConstraint:units.relative(unitDb.getDataStructures().spatialMaps,unitDb,unitDb.getLayoutHints())});
      units.seed(unitDb.getConfigField('seed'),()=>layout.run()); units.seed(unitDb.getConfigField('seed'),()=>layout.run());
      return cy.nodes().map(node=>({id:node.id(),parent:node.data('parent'),position:node.position(),box:node.boundingBox()}));
    } finally { cy.destroy(); }
  })()`;
  const boxes = vm.runInContext(layoutProbe, context, { timeout: 20000 });
  const byId = new Map(Array.from(boxes, item => [item.id, item]));
  const inside = (a, b) => a.x1 >= b.x1 && a.x2 <= b.x2 && a.y1 >= b.y1 && a.y2 <= b.y2;
  const overlap = (a, b) => a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
  for (const group of db.getGroups()) for (const node of boxes) {
    if (node.id === group.id) continue;
    let parent = node.parent, descendant = false, ancestor = false;
    while (parent) { if (parent === group.id) descendant = true; parent = byId.get(parent)?.parent; }
    parent = group.in;
    while (parent) { if (parent === node.id) ancestor = true; parent = byId.get(parent)?.parent; }
    if (descendant) assert(inside(node.box, byId.get(group.id).box), `Group must contain declared descendant ${node.id}`);
    else if (!ancestor) assert(!overlap(node.box, byId.get(group.id).box), `Group ${group.id} must not visually include unrelated ${node.id}`);
  }
  const platform = byId.get('platform').box;
  assert(platform.w < 800 && platform.h < 900, 'The fixture must not retain the constraint-driven empty expansion');

  const servicesStart=source.indexOf('otn=i(async function'),servicesEnd=source.indexOf(',ltn=',servicesStart);
  assert(servicesStart>0&&servicesEnd>servicesStart);
  let measurements, captionMeasurement;
  const selection=()=>({id:'',append(){return selection();},remove(){},attr(name,value){if(name==='id')this.id=value;return this;},html(){return this;},node(){return{getBBox:()=>measurements[this.id.split('-service-')[1]]||captionMeasurement};}});
  const drawServices=vm.runInNewContext('('+source.slice(servicesStart+4,servicesEnd)+')',{
    i:fn=>fn,Qt:()=>({}),ef:async()=>{},z0:async()=>'',T$:{prefix:'architecture'},avArchitectureMeasureCaption:units.measureCaption,avArchitectureMeasureEdgeWidth:units.measureEdgeWidth,
  });
  for(const [profile,extra,width,left,top] of [['caption',24,80,0,0],['wrapped',72,128,-24,0],['large-font',100,160,-32,-8]]) {
    measurements=Object.fromEntries(db.getServices().map(service=>[service.id,{x:left,y:top,width,height:80+extra}]));
    captionMeasurement={x:left-40,y:3,width,height:extra+top-8};
    await drawServices(db,selection(),db.getServices(),'measured');
    for(const service of db.getServices())assert.equal(JSON.stringify(service.avMeasuredBounds),JSON.stringify(measurements[service.id]),'Complete getBBox geometry reaches the service model');
    for(const service of db.getServices())assert.equal(JSON.stringify(service.avCaptionBounds),JSON.stringify({x:left,y:88,width,height:extra+top-8}),'Caption bounds retain the actual title-group translation');
    const measuredBoxes=vm.runInContext(layoutProbe,context,{timeout:20000});
    const measuredById=new Map(Array.from(measuredBoxes,item=>[item.id,item]));
    for(const group of db.getGroups())for(const service of db.getServices()) {
      const node=measuredById.get(service.id),box=measurements[service.id],frame=measuredById.get(group.id).box;
      const painted={x1:node.position.x+box.x,x2:node.position.x+box.x+box.width,y1:node.position.y+box.y,y2:node.position.y+box.y+box.height};
      const groupFrame={x1:frame.x1+40,x2:frame.x2+40,y1:frame.y1+40,y2:frame.y2+40};
      let parent=service.in,descendant=false;
      while(parent){if(parent===group.id)descendant=true;parent=measuredById.get(parent)?.parent;}
      assert(descendant?inside(painted,groupFrame):!overlap(painted,groupFrame),`${profile}: group ${group.id} preserves the complete ${service.id} caption footprint`);
    }
  }
  // Icon-side anchors stay fixed when the measured collision envelope grows.
  // Execute Cytoscape's actual endpoint conversion and the group's drawing hook.
  context.units=units;
  const anchors=await vm.runInContext(`(async () => {
    const cy=units.cytoscape({headless:true,styleEnabled:true,style:[
      {selector:'.node-service,.node-junction',style:{width:'data(width)',height:'data(height)'}},
      {selector:'.node-group',style:{padding:'40px'}},
      {selector:'edge',style:{'source-endpoint':'data(sourceEndpoint)','target-endpoint':'data(targetEndpoint)'}}]});
    units.groups([{id:'g'},{id:'h'}],cy);
    units.services([{id:'a',in:'g',avMeasuredBounds:{x:-20,y:0,width:120,height:160}},{id:'b',in:'h',avMeasuredBounds:{x:0,y:0,width:80,height:100}}],cy,unitDb);
    units.junctions([{id:'j',in:'g'}],cy,unitDb);
    cy.$id('a').position({x:10,y:20});cy.$id('b').position({x:400,y:20});cy.$id('j').position({x:10,y:400});
    const result=[],drawn=[];
    const element=tag=>{const record={tag,attributes:{}};drawn.push(record);return{insert:element,append:element,attr(name,value){record.attributes[name]=value;return this;}};};
    const drawingDb={getConfigField:name=>unitDb.getConfigField(name),setElementForId(){},getNode:id=>({type:id==='j'?'junction':'service'})};
    try {
    await units.drawGroups(element('groups'),cy,drawingDb,'anchors');
    const frames=Object.fromEntries(drawn.filter(item=>item.tag==='rect').map(item=>[item.attributes.id,item.attributes]));
    for(const [direction,targetDirection] of [['L','L'],['R','R'],['T','T'],['B','B'],['R','T'],['T','L'],['L','B'],['B','R']]) {
      units.edges([{lhsId:'a',rhsId:'b',lhsDir:direction,rhsDir:targetDirection}],cy);
      const edge=cy.edges().last(),source=cy.$id('a');
      const point=units.endpoint(source,edge.pstyle('source-endpoint'));
      result.push({direction,point,position:source.position(),group:units.groupEndpoint(cy,'a',direction,{x:point[0],y:point[1]},80),box:source.parent().boundingBox()});
      const targetPoint=units.endpoint(cy.$id('b'),edge.pstyle('target-endpoint'));
      edge[0].sourceEndpoint=()=>({x:point[0],y:point[1]});
      edge[0].targetEndpoint=()=>({x:targetPoint[0],y:targetPoint[1]});
      edge[0].midpoint=()=>({x:(point[0]+targetPoint[0])/2,y:(point[1]+targetPoint[1])/2});
      edge[0]._private.rscratch={};
      for(const [sourceGroup,targetGroup] of [[false,false],[true,false],[false,true],[true,true]]) {
        edge.data({sourceGroup,targetGroup});
        const start=drawn.length;
        await units.drawEdges(element('edges'),cy,drawingDb,'anchors');
        const line=drawn.slice(start).find(item=>item.tag==='path').attributes.d;
        const route=line.replace(/[ML]/g,'').trim().split(/\\s+/).map(pair=>pair.split(',').map(Number));
        result.push({drawing:{direction,targetDirection,sourceGroup,targetGroup,route,first:route[0],last:route.at(-1),sourcePoint:point,targetPoint,sourceFrame:frames['anchors-group-g'],targetFrame:frames['anchors-group-h']}});
      }
      edge.remove();
    }
    units.edges([{lhsId:'j',rhsId:'b',lhsDir:'B',rhsDir:'T'}],cy);
    const edge=cy.edges().last(),junction=cy.$id('j');
    result.push({junction:units.endpoint(junction,edge.pstyle('source-endpoint')),position:junction.position()});
    return result;
    } finally { cy.destroy(); }
  })()`,context);
  for(const item of anchors) {
    if(item.drawing){
      const d=item.drawing;
      for(const [actual,baseline,frame,group,direction] of [[d.first,d.sourcePoint,d.sourceFrame,d.sourceGroup,d.direction],[d.last,d.targetPoint,d.targetFrame,d.targetGroup,d.targetDirection]]) {
        const expected=Array.from(baseline);
        if(group){if(direction==='L')expected[0]=frame.x;else if(direction==='R')expected[0]=frame.x+frame.width;else if(direction==='T')expected[1]=frame.y;else expected[1]=frame.y+frame.height;}
        assert.deepEqual(Array.from(actual),expected,'Native edge output joins the actual icon or painted group border');
      }
      if(d.sourceGroup||d.targetGroup){
        const first=d.route[0],next=d.route[1],last=d.route.at(-1),before=d.route.at(-2);
        const vectors={L:[-1,0],R:[1,0],T:[0,-1],B:[0,1]};
        for(const [port,outside,direction] of [[first,next,d.direction],[last,before,d.targetDirection]]) {
          const vector=vectors[direction],dx=outside[0]-port[0],dy=outside[1]-port[1];
          assert.equal(dx*vector[1]-dy*vector[0],0,'The terminal leg follows its declared side axis');
          assert(dx*vector[0]+dy*vector[1]>0,'The terminal leg reaches the outside of its attached side');
        }
      }
      continue;
    }
    if(item.junction){assert.deepEqual(Array.from(item.junction),[item.position.x+40,item.position.y+80]);continue;}
    const relative={L:[0,40],R:[80,40],T:[40,0],B:[40,80]}[item.direction];
    assert.deepEqual(Array.from(item.point),[item.position.x+relative[0],item.position.y+relative[1]],'Measured captions preserve the original icon side attachment');
    const axis=['L','R'].includes(item.direction)?'x':'y',bound={L:'x1',R:'x2',T:'y1',B:'y2'}[item.direction];
    assert.equal(item.group[axis],item.box[bound]+40,'Group attachment follows its actual painted border');
    assert.equal(item.group[axis==='x'?'y':'x'],item.point[axis==='x'?1:0]);
  }

  // A real group named default is different from ungrouped material.
  const nodes = new Map([['external', {}], ['member', {in:'default'}], ['peer', {in:'default'}]]);
  const testDb = {getNode: id => nodes.get(id)};
  const spatial = [new Map([['external',[0,0]],['member',[0,1]],['peer',[0,2]]])];
  const scoped = units.align(testDb, spatial, new Map());
  assert(scoped.vertical.some(ids=>ids.includes('member')&&ids.includes('peer')));
  assert(!scoped.vertical.some(ids=>ids.includes('external')&&ids.includes('member')));
  const explicit = units.align(testDb, spatial, new Map(), [{direction:'column',members:['external','member']}]);
  assert(explicit.vertical.some(ids=>ids.join(',')==='external,member'), 'Explicit cross-group hints remain authoritative');
  assert(!explicit.vertical.some(ids=>ids.includes('peer')), 'Heuristic constraints cannot compete with explicit hints');
  const drawStart=source.indexOf('gLi=i(async'),drawEnd=source.indexOf(',htn=',drawStart);
  assert(drawStart>0&&drawEnd>drawStart);
  for(const failure of [null,'edges','groups','bounds']) {
    let destroyed=0;
    const selection={append(){return this;},attr(){return this;}};
    const failAt=phase=>{if(failure===phase)throw new Error('Failed '+phase);};
    const draw=vm.runInNewContext('('+source.slice(drawStart+4,drawEnd)+')',{
      i:fn=>fn,xu:()=>selection,otn:async()=>{},ltn(){},pLi:async()=>({destroy(){destroyed++;}}),
      atn:async()=>failAt('edges'),stn:async()=>failAt('groups'),cLi(){},Uk:()=>failAt('bounds'),
    });
    const model={setDiagramId(){},getServices:()=>[],getJunctions:()=>[],getGroups:()=>[],getEdges:()=>[],getDataStructures:()=>({}),getConfigField:()=>0};
    if(failure)await assert.rejects(draw('', 'owned', '', {db:model}),new RegExp('Failed '+failure));
    else await draw('', 'owned', '', {db:model});
    assert.equal(destroyed,1,'Drawing completion or failure releases its owned layout core');
  }
  const layoutStart=source.indexOf('function pLi('),layoutEnd=source.indexOf('var utn',layoutStart);
  for(const failure of [null,'construct','prepare','layout']) {
    let removed=0,destroyed=0;
    const owned={},alien={},selection={append(){return this;},attr(){return this;},node(){return owned;},remove(){removed++;}};
    const failAt=phase=>{if(failure===phase)throw new Error('Failed '+phase);};
    const core={layout:()=>({one(){},run:()=>failAt('layout')}),ready:callback=>callback(),destroy(){destroyed++;}};
    const layout=vm.runInNewContext('('+source.slice(layoutStart,layoutEnd)+')',{
      fn:()=>selection,document:{getElementById:()=>alien},c3:options=>{assert.equal(options.container,owned,'Layout owns its actual container, regardless of existing document IDs');failAt('construct');return core;},
      uLi:()=>failAt('prepare'),oLi(){},lLi(){},hLi(){},fLi:()=>({}),dLi:()=>[],B0t:(_seed,run)=>run(),Pe:{info(){}},
    });
    const model={getLayoutHints:()=>[],getConfigField:()=>80};
    if(failure)await assert.rejects(layout([],[],[],[],model,{spatialMaps:[],groupAlignments:new Map()}),new RegExp('Failed '+failure));
    else assert.equal(await layout([],[],[],[],model,{spatialMaps:[],groupAlignments:new Map()}),core);
    assert.equal(removed,1,'Owned temporary containers are removed after success and failure');
    assert.equal(destroyed,failure&&failure!=='construct'?1:0,'Failure releases any created core; success transfers ownership to drawing');
  }
  console.log('Architecture geometry passed: exact fixture parsing, numerical containment/exclusion, bounded canvas, distinct root/group identity and explicit alignment hints.');
})().catch(error => { console.error(error); process.exitCode = 1; });
