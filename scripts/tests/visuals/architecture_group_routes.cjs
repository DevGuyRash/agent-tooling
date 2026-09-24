// Parse the original counterexamples, lay them out, and check native path output.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../../..');
const {routeArchitectureConnection}=require(path.resolve(process.argv[2],'architecture-layout.js'));
let source=fs.readFileSync(path.join(root,'plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js'),'utf8');
const hook='i(pLi,"layoutArchitecture");';assert.equal(source.split(hook).length,2);
source=source.replace(hook,hook+'globalThis.units={cytoscape:c3,align:fLi,relative:dLi,seed:B0t,groups:uLi,services:oLi,junctions:lLi,edges:hLi,endpoint:Xse.manualEndptToPx,storeAllpts:Ky.storeAllpts,drawEdges:atn,edgeId:V2};');
const context=vm.createContext({console:{log(){},warn(){},error(){}},structuredClone,setTimeout,clearTimeout,setInterval,clearInterval,performance,TextEncoder,TextDecoder,URL});
vm.runInContext(source,context,{timeout:20000});context.mermaid.initialize({startOnLoad:false});
context.mermaid.setArchitectureRouter(routeArchitectureConnection);
function enters(a,b,box) {
  let low=0,high=1;
  for(const [key,min,max] of [['x',box.x1+1e-6,box.x2-1e-6],['y',box.y1+1e-6,box.y2-1e-6]]) {
    const i=key==='x'?0:1,d=b[i]-a[i];
    if(!d){if(a[i]<min||a[i]>max)return false;}
    else{const p=(min-a[i])/d,q=(max-a[i])/d;low=Math.max(low,Math.min(p,q));high=Math.min(high,Math.max(p,q));}
    if(low>high)return false;
  }
  return true;
}
(async()=>{
  const failures=[];
  for(let attempt=1;attempt<=3;attempt++)for(const fixture of JSON.parse(fs.readFileSync(path.join(__dirname,'architecture-group-regressions.json'),'utf8'))) {
    context.db=(await context.mermaid.mermaidAPI.getDiagramFromText(fixture.source)).db;
    for(const service of context.db.getServices())service.avMeasuredBounds={x:0,y:0,width:80,height:fixture.captionHeight};
    let result;
    try { result=await vm.runInContext(`(async()=>{
      const size=db.getConfigField('iconSize');
      const cy=units.cytoscape({headless:true,styleEnabled:true,style:[
        {selector:'.node-service,.node-junction',style:{width:'data(width)',height:'data(height)'}},
        {selector:'.node-group',style:{padding:db.getConfigField('padding')+'px'}},
        {selector:'edge',style:{'curve-style':'straight','source-endpoint':'data(sourceEndpoint)','target-endpoint':'data(targetEndpoint)'}}]});
      try {
        units.groups(db.getGroups(),cy);units.services(db.getServices(),cy,db);units.junctions(db.getJunctions(),cy,db);units.edges(db.getEdges(),cy);
        const ds=db.getDataStructures(),hints=db.getLayoutHints();
        const layout=cy.layout({name:'fcose',quality:'proof',randomize:db.getConfigField('randomize'),nodeSeparation:db.getConfigField('nodeSeparation'),numIter:db.getConfigField('numIter'),animate:false,nodeDimensionsIncludeLabels:false,
          idealEdgeLength(edge){const[a,b]=edge.connectedNodes();return a.data('parent')===b.data('parent')?db.getConfigField('idealEdgeLengthMultiplier')*size:.5*size;},
          edgeElasticity(edge){const[a,b]=edge.connectedNodes();return a.data('parent')===b.data('parent')?db.getConfigField('edgeElasticity'):.001;},
          alignmentConstraint:units.align(db,ds.spatialMaps,ds.groupAlignments,hints),relativePlacementConstraint:units.relative(ds.spatialMaps,db,hints)});
        units.seed(db.getConfigField('seed'),()=>layout.run());units.seed(db.getConfigField('seed'),()=>layout.run());
        const connections=[];
        for(const edge of cy.edges()) {
          const a=units.endpoint(edge.source(),edge.pstyle('source-endpoint')),b=units.endpoint(edge.target(),edge.pstyle('target-endpoint'));
          edge._private.rscratch={edgeType:'straight',startX:a[0],startY:a[1],endX:b[0],endY:b[1],arrowStartX:a[0],arrowStartY:a[1],arrowEndX:b[0],arrowEndY:b[1]};
          units.storeAllpts(edge);
          const scratch=edge._private.rscratch;
          edge.sourceEndpoint=()=>({x:a[0],y:a[1]});edge.targetEndpoint=()=>({x:b[0],y:b[1]});edge.midpoint=()=>({x:scratch.midX,y:scratch.midY});
          connections.push({id:'probe-'+units.edgeId(edge.data('source'),edge.data('target'),{prefix:'L'}),sourceDirection:edge.data('sourceDir'),targetDirection:edge.data('targetDir'),sourceGroup:edge.data('sourceGroup')?edge.source().parent().id():null,targetGroup:edge.data('targetGroup')?edge.target().parent().id():null});
        }
        const records=[],element=tag=>{const record={tag,attributes:{}};records.push(record);return{insert:element,append:element,attr(name,value){record.attributes[name]=value;return this;}};};
        await units.drawEdges(element('edges'),cy,db,'probe');
        const frames=Object.fromEntries(cy.nodes().filter(n=>n.data('type')==='group').map(n=>{const b=n.boundingBox();return[n.id(),{x1:b.x1+size/2,x2:b.x2+size/2,y1:b.y1+size/2,y2:b.y2+size/2}];}));
        return{connections,frames,paths:records.filter(r=>r.tag==='path').map(r=>r.attributes)};
      } finally {cy.destroy();}
    })()`,context,{timeout:20000}); }
    catch(error) { failures.push({fixture:fixture.name,attempt,error:String(error.message)}); continue; }
    for(const connection of result.connections) {
      const shape=result.paths.find(p=>p.id===connection.id);assert(shape,'Original relationships retain their native path identity');
      const points=shape.d.replace(/[ML]/g,'').trim().split(/\s+/).map(p=>p.split(',').map(Number));
      for(let i=1;i<points.length-1;i++) {
        const a=points[i-1],b=points[i],c=points[i+1],x=b[0]-a[0],y=b[1]-a[1],dx=c[0]-b[0],dy=c[1]-b[1];
        if(Math.abs(x*dy-y*dx)<1e-7&&x*dx+y*dy<0)failures.push({fixture:fixture.name,attempt,reason:'collinear reversal',path:shape.d});
      }
      for(const group of [connection.sourceGroup,connection.targetGroup].filter(Boolean)) {
        if(points.slice(1).some((p,i)=>enters(points[i],p,result.frames[group])))failures.push({fixture:fixture.name,attempt,connection:connection.id,group,path:shape.d});
      }
      if(connection.sourceGroup||connection.targetGroup) {
        const vectors={L:[-1,0],R:[1,0],T:[0,-1],B:[0,1]};
        for(const [point,outside,side] of [[points[0],points[1],connection.sourceDirection],[points.at(-1),points.at(-2),connection.targetDirection]]) {
          const v=vectors[side],x=outside[0]-point[0],y=outside[1]-point[1];
          if(Math.abs(x*v[1]-y*v[0])>1e-7||x*v[0]+y*v[1]<=0)failures.push({fixture:fixture.name,attempt,side,path:shape.d});
        }
      }
    }
  }
  assert.deepEqual(failures,[],'Group connections must remain outside their attached group interiors after endpoint relocation');
  console.log('Architecture group geometry passed: parsed counterexamples, native numerical midpoint, complete emitted routes and three consecutive replays.');
})().catch(error=>{console.error(error);process.exitCode=1;});
