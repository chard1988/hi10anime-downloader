const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source = ["core.js", "projects.js", "downloads.js", "render.js", "details.js", "browser.js", "app.js"].map(name => fs.readFileSync(require('node:path').join(__dirname, '../src/hi10_downloader/static', name), 'utf8')).join('\n');
const apply=source.slice(source.indexOf('function applyState(result) {'),source.indexOf('function schedulePoll() {'));
const visible=source.slice(source.indexOf('function visibleProjects() {'),source.indexOf('function updateSelection() {'));
const fields={search:{value:''},filter:{value:'all'}};
const context=vm.createContext({fields});
vm.runInContext(`let state=null,selected=new Set(),projectsById=new Map(),downloadPage=0,projectPage=0;const pageSize=50;const $=id=>fields[id]; ${apply}; ${visible}; this.apply=applyState;this.page=pageProjects;this.setPage=n=>projectPage=n;this.current=()=>state;`,context);
const projects=Array.from({length:123},(_,i)=>({id:String(i),title:`Project ${i}`,scanned:false}));
context.apply({projects,download_page:0});
assert.equal(context.page().page.length,50);
context.setPage(1);assert.equal(context.page().page[0].id,'50');
context.setPage(2);assert.equal(context.page().page.length,23);
context.apply({projects:null,project_updates:[{...projects[0],title:'Updated title'}],download_page:0});
assert.equal(context.current().projects.length,123);
assert.equal(context.current().projects[0].title,'Updated title');
assert.equal(context.current().projects[1].title,'Project 1');
fields.search.value='Updated title';
assert.equal(context.page().page.length,1);
assert.equal(context.page().page[0].id,'0');
Object.assign(fields,{'selection-count':{},'select-all':{},'scan-selected':{},'download-selected':{},'exclude-selected':{},'include-selected':{}});
const selection=source.slice(source.indexOf('function updateSelection() {'),source.indexOf('function renderProjects('));
vm.runInContext(`${selection};this.select=id=>selected.add(id);this.updateSelection=updateSelection;this.canStart=canStartDownloads;let pendingAction=null;`,context);
fields.search.value='';
const runningDownload={running:true,kind:'download'};
context.apply({projects,job:{running:false},download_job:runningDownload,session:{connected:true}});
context.select('0');context.updateSelection();
assert.equal(fields['scan-selected'].disabled,false,'a running download must not block selected scans');
assert.equal(fields['download-selected'].disabled,true,'queue mutations remain protected during downloads');
assert.equal(context.canStart(),false,'a second download batch must be blocked');
context.apply({projects:null,job:{running:true,kind:'scan'},download_job:{running:false},session:{connected:true}});
context.updateSelection();
assert.equal(fields['scan-selected'].disabled,true,'a second scan must be blocked');
assert.equal(context.canStart(),true,'a download may start during a scan');
console.log('UI state checks passed: incremental updates and bounded project pagination.');

// A slow request must display feedback before the server responds and block a
// second click. Exercise the actual action handler with a deferred API response.
(async()=>{
  let resolveRequest;
  const response=new Promise(resolve=>resolveRequest=resolve);
  const button={tagName:'BUTTON',textContent:'Retry scan',isConnected:true,disabled:false,
    attributes:{},setAttribute(key,value){this.attributes[key]=value;},
    removeAttribute(key){delete this.attributes[key];},replaceChildren(...children){this.children=children;}};
  let renders=0,calls=0;
  const actions=vm.createContext({document:{activeElement:button},node:(tag,text,style)=>({tag,text,style}),
    render:()=>renders++,api:()=>{calls++;return response;},toast:()=>{},refreshState:async()=>{}});
  const handler=source.slice(source.indexOf('function requestLabel(path) {'),source.indexOf('function showView(view) {'));
  vm.runInContext(`let pendingAction=null,state={},stateRequest=null;${handler};this.run=action;this.pending=()=>pendingAction;`,actions);
  const first=actions.run('/api/scan',{ids:['project']});
  assert.equal(button.disabled,true);
  assert.equal(button.attributes['aria-busy'],'true');
  assert.equal(button.children[0].style,'button-spinner');
  assert.equal(actions.pending().label,'Requesting scan…');
  assert.ok(renders>0);
  assert.equal(await actions.run('/api/scan',{ids:['project']}),false);
  assert.equal(calls,1);
  resolveRequest({});
  assert.equal(await first,true);
  assert.equal(actions.pending(),null);
  assert.equal(button.attributes['aria-busy'],undefined);
  console.log('Action feedback checks passed: immediate spinner and duplicate-click protection.');
})().catch(error=>{console.error(error);process.exitCode=1;});
// Batch progress belongs to the initiating start button, including after a reload.
const buttons=Object.fromEntries(['start-downloads','start-selected-downloads'].map(id=>[id,{
  attributes:{},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this.attributes[k];},replaceChildren(...children){this.children=children;}
}]));
const progressContext=vm.createContext({buttons,node:(tag,text,cls)=>({tag,text,cls})});
const progressCode=source.slice(source.indexOf('function renderDownloadStartProgress() {'),source.indexOf('function render() {'));
vm.runInContext(`let state={download_job:{running:true,source:'selected',done:1,total:500}},pendingAction=null;const $=id=>buttons[id];${progressCode};this.draw=renderDownloadStartProgress;this.job=state.download_job;`,progressContext);
progressContext.draw();
assert.equal(buttons['start-selected-downloads'].children[1].text,'Start selected 1/500');
assert.equal(buttons['start-downloads'].textContent,'▶ Start downloads');
assert.equal(buttons['start-selected-downloads'].attributes['aria-busy'],'true');
progressContext.job.running=false;progressContext.draw();
assert.equal(buttons['start-selected-downloads'].textContent,'Start selected');
assert.equal(buttons['start-selected-downloads'].attributes['aria-busy'],'false');
console.log('Start button progress checks passed.');

fields.filter.value='ready';fields.search.value='';
context.apply({projects:[
  {id:'eligible',title:'Eligible',scanned:true,remaining:3,excluded:false},
  {id:'excluded',title:'Excluded',scanned:true,remaining:3,excluded:true},
  {id:'finished',title:'Finished',scanned:true,remaining:0,excluded:false}
]});
assert.deepEqual(Array.from(context.page().filtered,p=>p.id),['eligible']);
fields.filter.value='excluded';
assert.deepEqual(Array.from(context.page().filtered,p=>p.id),['excluded']);
fields.filter.value='all';
assert.equal(context.page().filtered.length,3);
console.log('Project filter checks passed: excluded projects stay out of Ready to download.');
