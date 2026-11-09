$('unlock-form').addEventListener('submit', async event => {
  event.preventDefault(); const button=event.submitter;
  button.disabled=true; button.textContent='Unlocking…'; $('unlock-error').textContent='';
  try {await api('/api/unlock', {password:$('web-password').value}); $('web-password').value=''; unlocked=true; $('unlock').hidden=true; $('app').hidden=false; await refreshState();}
  catch(error) {$('unlock-error').textContent=error.message;}
  finally {button.disabled=false; button.textContent='Unlock library →';}
});
$('lock-button').onclick = async () => {await action('/api/lock'); lockScreen();};
document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => showView(button.dataset.view));
for (const id of ['account-button','connect-banner-button']) $(id).onclick = () => showView('session');
$('empty-connect').onclick = () => state?.session.connected ? action('/api/refresh') : showView('session');
$('back-library').onclick = () => showView('library');
$('refresh').onclick = () => action('/api/refresh');
$('scan-all').onclick = () => action('/api/scan', {ids: state.projects.map(p => p.id)});
$('exclude-selected').onclick = () => action('/api/projects/exclude', {ids:[...selected],excluded:true}, 'Selected projects excluded from scans and queueing.');
$('include-selected').onclick = () => action('/api/projects/exclude', {ids:[...selected],excluded:false}, 'Selected projects included again.');
$('download-filter').onchange=()=>{downloadPage=0;lastDownloads='';refreshState();};
$('scan-selected').onclick = () => action('/api/scan', {ids: [...selected]});
$('download-selected').onclick = async () => {if (await action('/api/queue', {ids: [...selected]})) showView('downloads');};
$('stop-job').onclick = () => action('/api/stop', {target:'scan'});
$('stop-downloads').onclick = () => action('/api/stop', {target:'download'});
$('search').addEventListener('input', () => {projectPage=0; renderProjects(true);});
$('filter').onchange = () => {projectPage=0; renderProjects(true);};
$('select-all').onchange = () => {for (const p of pageProjects().page) $('select-all').checked ? selected.add(p.id) : selected.delete(p.id); renderProjects(true);};
$('default-quality').onchange = () => action('/api/preferences', {quality: Number($('default-quality').value)});
$('verify-session').onclick = () => action('/api/session/verify');
$('forget-session').onclick = async () => {if (confirm('Remove the saved Hi10 session from this server?')) {await action('/api/session/delete'); browserOpen = false; $('browser-panel').hidden = true; $('credentials-form').hidden = true;}};
$('session-file').onchange = async event => {const file = event.target.files[0]; if (!file) return; try {if (file.size > 2*1024*1024) throw new Error('Session file exceeds 2 MB.'); await action('/api/session/import', {state: JSON.parse(await file.text())}, 'Session imported. Verifying access…');} catch(error) {toast(error.message);} event.target.value = '';};
$('open-browser').onclick = async () => {if (await action('/api/browser/start')) {browserOpen = true; $('browser-panel').hidden = false; $('credentials-form').hidden = false; $('browser-loading').hidden = false; $('browser-panel').scrollIntoView({behavior: 'smooth',block:'start'});}};
$('credentials-form').onsubmit = async event => {event.preventDefault(); const data = {action:'credentials',username:$('username').value,password:$('password').value}; $('password').value = ''; if (await browserInput(data)) toast('Fields filled. Click Log In inside the website after reCAPTCHA loads.');};
$('close-browser').onclick = async () => {await browserInput({action:'close'}); browserOpen = false; $('browser-panel').hidden = true; $('credentials-form').hidden = true; $('password').value = '';};
$('save-session').onclick = () => action('/api/browser/capture', {}, 'Checking access and capturing your session…');
$('browser-image').onclick = event => {const box = event.target.getBoundingClientRect(); event.target.focus({preventScroll:true}); browserInput({action:'click',x:(event.clientX-box.left)*1000/box.width,y:(event.clientY-box.top)*760/box.height});};
$('browser-image').onkeydown = event => {
  const keys = new Set(['Tab','Enter','Backspace','Delete','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Escape']);
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {event.preventDefault(); browserInput({action:'key',key:'Control+A'});}
  else if (keys.has(event.key)) {event.preventDefault(); browserInput({action:'key',key:event.key});}
  else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {event.preventDefault(); browserInput({action:'text',text:event.key});}
};
$('browser-image').addEventListener('paste', event => {event.preventDefault(); browserInput({action:'text',text:event.clipboardData.getData('text')});});
$('browser-image').addEventListener('wheel', event => {event.preventDefault(); browserInput({action:'scroll',delta:event.deltaY});}, {passive:false});
$('browser-text-form').onsubmit = async event => {event.preventDefault(); const text = $('browser-text').value; $('browser-text').value = ''; await browserInput({action:'text',text});};
$('browser-enter').onclick = () => browserInput({action:'key',key:'Enter'});
$('close-details').onclick = () => $('detail-dialog').close();
$('save-details').onclick = async () => {
  const choices = {...detail.choices}, section_qualities = {};
  $('detail-files').querySelectorAll('select[data-key]').forEach(select => choices[select.dataset.key] = Number(select.value));
  const data = {id: detail.id, choices};
  if (detail.sections.length) {
    data.sections = [...$('detail-files').querySelectorAll('input[data-section]:checked')].map(input => input.dataset.section);
    $('detail-files').querySelectorAll('select[data-section-quality]').forEach(select => section_qualities[select.dataset.sectionQuality] = Number(select.value));
    data.section_qualities = section_qualities;
  }
  if (await action('/api/project/settings', data, 'Download selection saved.')) $('detail-dialog').close();
};
$('previous-projects').onclick=()=>{projectPage--;renderProjects(true);};
$('next-projects').onclick=()=>{projectPage++;renderProjects(true);};
async function changeDownloadPage(delta) {if(stateRequest) await stateRequest; downloadPage+=delta; await refreshState();}
$('previous-downloads').onclick=()=>changeDownloadPage(-1);
$('next-downloads').onclick=()=>changeDownloadPage(1);
$('start-downloads').onclick=()=>action('/api/downloads/start');
$('cancel-schedule').onclick=()=>action('/api/downloads/unschedule',{},'Scheduled start cancelled. Files remain queued.');
$('clear-completed').onclick=()=>action('/api/downloads/clear-completed',{},'Completed entries cleared. Downloaded files are retained.');
$('schedule-timezone').textContent=`Times use your browser timezone: ${Intl.DateTimeFormat().resolvedOptions().timeZone}. The container must be running at the scheduled time.`;
$('schedule-form').onsubmit=event=>{
  event.preventDefault(); const date=new Date($('schedule-time').value);
  if(!Number.isFinite(date.getTime()) || date.getTime()<=Date.now()) return toast('Choose a future date and time.');
  action('/api/downloads/schedule',{starts_at:date.toISOString()},'Start time saved on the server. You can close the browser.');
};
(async () => {
  $('connection-status').hidden=false; $('connection-status').textContent='Connecting and restoring saved data…';
  try {applyState(await api('/api/state')); unlocked=true; $('app').hidden=false; render(); schedulePoll();}
  catch(error) {lockScreen(); if(!error.message.includes('Unlock')) $('unlock-error').textContent=error.message;}
})();
document.addEventListener('visibilitychange',()=>{clearTimeout(pollTimer);if(!document.hidden) refreshState();});
setInterval(screenshot,2500);

$('download-settings').onclick=()=>$('download-settings-dialog').showModal();
$('close-download-settings').onclick=()=>$('download-settings-dialog').close();
$('close-download-link').onclick=()=>$('download-link-dialog').close();

$('select-queue-page').onchange=event=>{for(const item of state.downloads){event.target.checked?queueSelected.add(item.id):queueSelected.delete(item.id);}lastDownloads='';renderDownloads();};
$('clear-queue-selection').onclick=()=>{queueSelected.clear();lastDownloads='';renderDownloads();};
for(const [id,path] of [['start-selected-downloads','/api/downloads/start-selected'],['remove-selected-downloads','/api/downloads/remove-selected']]) {
  $(id).onclick=async()=>{if(await action(path,{ids:[...queueSelected]})){queueSelected.clear();lastDownloads='';renderDownloads();}};
}

$('download-link-form').onsubmit=async event=>{
  event.preventDefault();
  const id=editingDownloadId,url=$('download-link-value').value.trim();
  const button=$('save-download-link');button.disabled=true;button.textContent='Saving…';
  try {if(await action('/api/downloads/edit-url',{id,url},'URL saved. Use Retry or Start this item when ready.')) $('download-link-dialog').close();}
  finally {button.textContent='Save URL';button.disabled=operationsBusy();}
};

$('exclude-queue-projects').onclick=async()=>{
  const ids=[...queueProjectsSelected];
  if(await action('/api/projects/exclude',{ids,excluded:true},'Projects excluded from scans and downloads. Completed files are retained.')) {
    queueProjectsSelected.clear();queueSelected.clear();lastDownloads='';renderDownloads();
  }
};
$('clear-queue-project-selection').onclick=()=>{queueProjectsSelected.clear();lastDownloads='';renderDownloads();};
