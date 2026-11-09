'use strict';
const $ = id => document.getElementById(id);
let state = null, currentView = 'library', selected = new Set(), detail = null, unlocked = false;
let lastRows = '', lastDownloads = '', lastJobError = '', toastTimer, imageURL, imageBusy = false, browserOpen = false;
let inputChain = Promise.resolve();
let editingDownloadId=null;
let stateRequest = null, pendingAction = null, pollTimer;
let projectPage = 0, downloadPage = 0, projectsById = new Map();
const pageSize = 50;
const queueSelected = new Set();
const queueProjectsSelected = new Set();
const expandedDownloads = new Set();
const expandedQueueGroups=new Set(), queueGroupPages=new Map();
const qualityLabel = value => Number(value) ? `${value}p` : 'Unknown';
function node(tag, text, cls) { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (cls) element.className = cls; return element; }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 6500); }
async function api(path, data) {
  const options = data === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)};
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);
  let response;
  try {response = await fetch(path, {...options, signal: controller.signal});}
  catch (error) {throw new Error(error.name === 'AbortError' ? 'The server is taking too long. Your saved data is retained; try again.' : 'Cannot reach the server. Check the container and network.');}
  finally {clearTimeout(timeout);}
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/unlock') lockScreen();
    throw new Error(result.error || 'Request failed. Try again.');
  }
  return result;
}
function lockScreen() { unlocked = false; clearTimeout(pollTimer); $('unlock').hidden = false; $('app').hidden = true; browserOpen = false; $('connection-status').hidden = true; }
function applyState(result) {
  const updates = new Map((result.project_updates || []).map(project => [project.id, project]));
  const projects = result.projects === null ? (state?.projects || []).map(project => updates.get(project.id) || project) : result.projects;
  if (result.projects !== null || updates.size) {
    projectsById = new Map(projects.map(project => [project.id, project]));
    selected = new Set([...selected].filter(id => projectsById.has(id)));
  }
  state = {...result, projects};
  downloadPage = result.download_page || 0;
}
function operationsBusy() { return !!state?.job.running || !!state?.download_job?.running; }
function canStartDownloads() { return !state?.download_job?.running && (!state?.job.running || state.job.kind === 'scan'); }
function schedulePoll() {
  clearTimeout(pollTimer);
  if (unlocked && !document.hidden) pollTimer = setTimeout(refreshState, operationsBusy() ? 1500 : 15000);
}
async function refreshState() {
  if (!unlocked) return;
  if (stateRequest) return stateRequest;
  stateRequest = (async () => {
    try {
      const query = new URLSearchParams({download_page: String(downloadPage), download_filter: $('download-filter').value, grouped:'1', group_pages:JSON.stringify(Object.fromEntries((state?.download_groups || []).filter(g=>expandedQueueGroups.has(g.id)).map(g=>[g.id,queueGroupPages.get(g.id)||0])))});
      if (state?.library_version !== undefined) query.set('library_version', String(state.library_version));
      applyState(await api(`/api/state?${query}`));
      if(state.download_groups?.some(group=>expandedQueueGroups.has(group.id) && !group.loaded)) {
        query.set('download_page',String(downloadPage));
        query.set('group_pages',JSON.stringify(Object.fromEntries(state.download_groups.filter(group=>expandedQueueGroups.has(group.id)).map(group=>[group.id,queueGroupPages.get(group.id)||0]))));
        applyState(await api(`/api/state?${query}`));
      }
      render();
    } catch (error) { if (unlocked) toast(error.message); }
    finally { stateRequest = null; schedulePoll(); }
  })();
  return stateRequest;
}
function requestLabel(path) {
  return ({'/api/scan':'Requesting scan…','/api/queue':'Adding to queue…','/api/refresh':'Loading projects…',
    '/api/session/verify':'Verifying saved session…','/api/session/import':'Importing session…',
    '/api/browser/start':'Opening login browser…','/api/browser/capture':'Saving and verifying session…',
    '/api/downloads/start':'Starting downloads…','/api/downloads/schedule':'Saving schedule…',
    '/api/stop':'Requesting stop…'})[path] || 'Saving changes…';
}
async function action(path, data = {}, message) {
  if (pendingAction) return false;
  pendingAction = {path, ids: data.ids || [], label: requestLabel(path)};
  const button = document.activeElement?.tagName === 'BUTTON' ? document.activeElement : null;
  const text = button?.textContent;
  if (button) {button.disabled = true; button.setAttribute('aria-busy','true'); button.replaceChildren(node('span', undefined, 'button-spinner'), node('span', pendingAction.label));}
  if (state) render();
  try {
    const result = await api(path, data);
    if (message) toast(message);
    else if (path === '/api/queue') toast(`${result.added} files added. Downloads have not started.`);
    if (stateRequest) await stateRequest;
    await refreshState(); return true;
  } catch (error) {toast(error.message); return false;}
  finally {
    pendingAction = null;
    if (button?.isConnected) {button.textContent = text; button.removeAttribute('aria-busy');}
    if (state) render();
  }
}

function showView(view) {
  currentView = view;
  for (const name of ['library', 'downloads', 'session']) $(`${name}-view`).hidden = name !== view;
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  if (state && view === 'downloads') renderDownloads();
  if (unlocked) refreshState();
  $('breadcrumb').textContent = `Workspace / ${{library: 'Project library', downloads: 'Downloads', session: 'Account & session'}[view]}`;
}
