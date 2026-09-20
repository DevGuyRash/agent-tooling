/** Fictional observations used to exercise small reports and independent embeds.
 * Findings below are authored example text, never inferred by the visual library. */
import * as V from '../src/index';

function sensorNote(id: string, embedded = false, dark = false): string {
  const reference = [{label: 'Retained bench record', href: '#' + id + '--record'}];
  const overview = V.scatterPlot({
    id: id + '--plot', title: 'Drift under the recorded conditions',
    description: 'Housing, room temperature and missing readings are retained separately. Each completed point represents one run.',
    xAxis: 'Room temperature', xUnit: '°C', yAxis: 'Drift after ten minutes', yUnit: '°C',
    points: [
      {id: 'open', label: 'Bench run', groupId: 'open', group: 'Open housing', x: 22.2, y: .18, evidence: reference},
      {id: 'insulated', label: 'Bench run', groupId: 'insulated', group: 'Insulated housing', x: 21.8, y: .04, evidence: reference},
      {id: 'control', label: 'Bench run', groupId: 'control', group: 'Control', x: 22.0, y: null, note: 'The logger failed before the final reading. No drift value is available.', evidence: reference},
    ],
    limitations: ['One completed run per housing. Room temperatures differed; repeatability was not measured.'],
  });
  const record = V.nativeArtifactViewer({ id: id + '--record', title: 'Original bench records', artifacts: [
    { label: 'Bench run', mediaType: 'text/plain', text: 'run: open\nhousing: open\nroom: 22.2 °C\ndrift after 10 min: 0.18 °C\nprobe: Δ-1', evidence: reference },
    { label: 'Bench run', mediaType: 'text/plain', text: 'run: insulated\nhousing: insulated\nroom: 21.8 °C\ndrift after 10 min: 0.04 °C\nprobe: Δ-1', evidence: reference },
    { label: 'Bench run — interrupted', mediaType: 'text/plain', text: 'run: control\nroom: 22.0 °C\nfinal reading: unavailable\nlogger: failed\noperator note: <script> is literal evidence text.\nUnicode record: e\u0301 / 日本語 / 👩🏽‍🚀' },
  ]});
  return V.evidenceWorkspace({
    id, landmark: embedded ? 'region' : 'main', label: 'Fictional bench observations', title: 'A cooler housing, an open question',
    description: 'A small comparison of two housings and an interrupted control run.',
    theme: dark ? 'dark' : 'light', palette: dark ? 'ocean' : 'graphite', canvas: 'plain',
    brief: {
      question: 'Does the insulated housing reduce ten-minute drift?',
      paragraphs: ['The insulated-housing run recorded less drift than the open-housing run. Room temperatures differed, and the control run has no final reading.'],
      finding: 'These observations motivate another comparison; they do not establish repeatability or isolate the effect of the housing.',
      evidence: reference,
    },
    notebook: { revision: 'bench-1', storageKey: id + ':notebook' }, storageKey: id + ':display',
    views: [{id: 'observations', label: 'Measurements and limits', body: overview + record}],
    footer: '<p>All observations are fictional. No real instrument or product was evaluated.</p>',
  });
}
export function renderCompact(): string { return sensorNote('sensor-note'); }
export function renderEmbedded(): string {
  // Container widths, not the browser viewport, determine each report layout.
  return '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:24px;align-items:start;max-width:1120px;margin:24px auto">' + sensorNote('left-study', true) + sensorNote('right-study', true, true) + '</div>';
}
export function renderStress(): string {
  const long = 'This retained observation includes a qualification that must remain readable when the container is narrow. ';
  const body = V.reportSection({id:'long-evidence', title:'Repeated observations with their original conditions', body:
    V.scatterPlot({id:'many-points',title:'Known and incomplete readings',xAxis:'Elapsed time',xUnit:'s',yAxis:'Recorded value',yUnit:'mV',points:Array.from({length:160},(_,i)=>({id:'reading-'+i,label:'Reading',groupId:'g'+i%9,group:'Condition '+i%9,x:i%17===0?null:i,y:i%19===0?null:(i%23)*.25,note:i%19===0?'Logger failed; final value missing.':long+(i+1)}))})+
    V.nativeArtifactViewer({id:'long-records',title:'Complete retained passages',artifacts:Array.from({length:12},(_,i)=>({label:'Record '+(i+1),mediaType:'text/plain',text:'record: '+i+'\n'+long.repeat(i%3===0?40:2)+'\nExact tail: '+i+' / Δ / 日本語 / e\u0301 / 👩🏽‍🚀'}))})
  });
  return V.evidenceWorkspace({id:'stress-study',title:'Recorded conditions and incomplete observations',label:'Fictional stress composition',theme:'light',notebook:{revision:'stress-1'},views:[
    {id:'readings',label:'Readings',body},
    {id:'diagrams',label:'Relationships',body:V.reportSection({id:'diagram-parent',title:'Source, check and result',body:V.reportSection({id:'diagram-child',title:'A nested process view',body:V.mermaidDiagram({id:'valid-diagram',title:'A qualified relationship',source:'flowchart LR\n A[Original source] -->|supports under these conditions| B[Result]\n C[Exception] -.->|limits| B'})})})+V.mermaidDiagram({id:'failed-diagram',title:'An unreadable source remains available',source:'this is intentionally not a diagram'})},
  ]});
}
