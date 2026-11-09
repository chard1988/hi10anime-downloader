const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = ["core.js", "projects.js", "downloads.js", "render.js", "details.js", "browser.js", "app.js"].map(name => fs.readFileSync(require('node:path').join(__dirname, '../src/hi10_downloader/static', name), 'utf8')).join('\n');
const refresh = source.slice(source.indexOf('async function refreshState() {'), source.indexOf('\nasync function action('));
let requests = 0, renders = 0, errors = 0, resolveRequest, rejectRequest;
const context = vm.createContext({URLSearchParams, $:()=>({value:'all'}),
  api() { requests++; return new Promise((resolve, reject) => {resolveRequest=resolve; rejectRequest=reject;}); },
  render() {renders++;}, toast() {errors++;}
});
vm.runInContext(`let unlocked=true, stateRequest=null, state=null, downloadPage=0; function applyState(value){state=value;} function schedulePoll(){} ${refresh}; this.refresh=refreshState; this.lock=()=>unlocked=false;`, context);
(async () => {
  const first=context.refresh(), second=context.refresh();
  assert.equal(requests,1,'overlapping polls must share one request');
  resolveRequest({projects:[]});
  await Promise.all([first,second]);
  assert.equal(renders,1);
  const failed=context.refresh();
  assert.equal(requests,2);
  rejectRequest(new Error('network failure'));
  await failed;
  assert.equal(errors,1);
  const retry=context.refresh();
  assert.equal(requests,3,'a failed request must release the polling guard');
  resolveRequest({projects:[]});
  await retry;
  context.lock();
  await context.refresh();
  assert.equal(requests,3,'locked interfaces should not poll');
  console.log('Polling checks passed: deduplication, failure recovery, and locked state.');
})().catch(error => {console.error(error); process.exitCode=1;});
