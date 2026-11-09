function visibleProjects() {
  const query = $('search').value.trim().toLowerCase(), filter = $('filter').value;
  return (state?.projects || []).filter(p => p.title.toLowerCase().includes(query) && (
    filter === 'excluded' && p.excluded || filter === 'all' || filter === 'unscanned' && !p.scanned || filter === 'ready' && p.remaining > 0 && !p.excluded || filter === 'complete' && p.count > 0 && p.remaining === 0 || filter === 'issues' && p.error && !p.excluded));
}
function pageProjects() {
  const filtered = visibleProjects();
  projectPage = Math.max(0, Math.min(projectPage, Math.max(0, Math.ceil(filtered.length / pageSize) - 1)));
  return {filtered, page: filtered.slice(projectPage * pageSize, (projectPage + 1) * pageSize)};
}
function updateSelection() {
  const {page: visible} = pageProjects();
  $('selection-count').textContent = selected.size ? `${selected.size} project${selected.size === 1 ? '' : 's'} selected` : 'Select projects on this page';
  $('select-all').checked = visible.length > 0 && visible.every(p => selected.has(p.id));
  $('select-all').indeterminate = !visible.every(p => selected.has(p.id)) && visible.some(p => selected.has(p.id));
  const busy = operationsBusy() || !!pendingAction;
  $('exclude-selected').disabled = busy || ![...selected].some(id=>!projectsById.get(id)?.excluded);
  $('include-selected').disabled = busy || ![...selected].some(id=>projectsById.get(id)?.excluded);
  $('scan-selected').disabled = !!state?.job.running || !!pendingAction || ![...selected].some(id=>!projectsById.get(id)?.excluded) || !state?.session.connected;
  $('scan-selected').title = state?.job.running ? 'Wait for the current library operation or stop the scan.' : !state?.session.connected ? 'Connect your saved session first.' : selected.size === 0 ? 'Select projects using the checkboxes, then scan their pages.' : `Scan ${selected.size} selected project pages; downloads can continue.`;
  $('download-selected').disabled = busy || selected.size === 0 || [...selected].some(id => !projectsById.get(id)?.count || projectsById.get(id)?.excluded);
}
function renderProjects(force = false) {
  const {filtered, page: projects} = pageProjects();
  const signature = JSON.stringify([state.library_version, projectPage, $('search').value, $('filter').value, [...selected], state.job.running, state.download_job?.running, state.job.project_id, state.job.project_ids, pendingAction]);
  if (!force && signature === lastRows) return;
  if (!force && $('projects').contains(document.activeElement) && document.activeElement.tagName === 'SELECT') return;
  lastRows = signature;
  const fragment = document.createDocumentFragment();
  for (const p of projects) {
    const row = node('tr');
    const checkboxCell = node('td'), checkbox = node('input'); checkbox.type = 'checkbox'; checkbox.checked = selected.has(p.id); checkbox.setAttribute('aria-label', `Select ${p.title}`);
    checkbox.addEventListener('change', () => { checkbox.checked ? selected.add(p.id) : selected.delete(p.id); updateSelection(); lastRows = ''; }); checkboxCell.append(checkbox);
    const titleCell = node('td'), title = node('a', p.title, 'project-title'); title.href = p.url; title.target = '_blank'; title.rel = 'noopener noreferrer'; title.title = p.title;
    titleCell.append(title, node('div', p.scanned ? `${p.count || 0} file${p.count === 1 ? "" : "s"} detected · ${p.complete} downloaded` : 'Scan to discover files', 'project-subtitle'));
    if (p.section_count > 1) titleCell.append(node('div', `${p.selected_section_count} of ${p.section_count} sections selected`, 'project-subtitle'));
    const countCell = node('td'), count = node('div', p.count === null ? '—' : String(p.remaining), 'file-count'); if (p.count !== null) count.append(node('span', 'remaining')); countCell.append(count);
    const qualityCell = node('td'), badges = node('div', undefined, 'quality-wrap');
    if (p.qualities.length) p.qualities.forEach((q, i) => badges.append(node('span', qualityLabel(q), `badge${i === 0 ? ' best' : ''}`))); else badges.append(node('span', '—', 'muted'));
    qualityCell.append(badges);
    let status = 'Not scanned', statusClass = '';
    const scanning = state.job.running && state.job.kind === 'scan' && (state.job.project_id === p.id || (!state.job.project_id && state.job.project_ids?.includes(p.id)));
    const requestingScan = pendingAction?.path === '/api/scan' && pendingAction.ids.includes(p.id);
    if (scanning || requestingScan) {status = scanning && state.job.project_id ? 'Scanning…' : 'Starting scan…'; statusClass = 'ready';}
    else if (p.excluded) {status = 'Excluded'; statusClass = 'issue';}
    else if (p.restoring) status = 'Restoring…';
    else if (p.error) {status = 'Needs attention'; statusClass = 'issue';}
    else if (p.scanned && p.count > 0) {status = p.remaining ? 'Ready' : 'Downloaded'; statusClass = 'ready';}
    else if (p.scanned) status = 'No direct links';
    const statusCell = node('td'), statusBadge = node('span', status, `status ${statusClass}`); if (p.error) statusBadge.title = p.error; statusCell.append(statusBadge);
    const actionsCell = node('td'), actions = node('div', undefined, 'row-actions');
    if (p.scanned && p.qualities.length > 0 && !p.error) {
      const select = node('select'); select.setAttribute('aria-label', `Quality preference for ${p.title}`);
      select.append(new Option('Highest', '0'));
      const values = [...new Set([...p.qualities.filter(q => q > 0), ...(p.preferred ? [p.preferred] : [])])].sort((a,b) => b-a);
      values.forEach(q => select.append(new Option(`Prefer ${q}p`, String(q)))); select.value = p.preferred; select.disabled = operationsBusy() || !!pendingAction;
      select.title = 'Prefer this quality; fall back to highest if unavailable. Per-file choices override this.';
      select.addEventListener('change', () => action('/api/project/settings', {id: p.id, quality: Number(select.value)}));
      const button = node('button', '⋯'); button.setAttribute('aria-label', `Review files for ${p.title}`); button.title = 'Review files and individual quality choices'; button.addEventListener('click', () => openDetails(p.id)); actions.append(select, button);
    } else {
      const waiting = scanning || requestingScan;
      const button = node('button', waiting ? (scanning && state.job.project_id ? 'Scanning…' : 'Starting…') : p.error ? 'Retry scan' : 'Scan page');
      button.disabled = p.excluded || state.job.running || !!pendingAction || !state.session.connected;
      if (waiting) {button.prepend(node('span', undefined, 'button-spinner')); button.setAttribute('aria-busy', 'true');}
      button.addEventListener('click', () => action('/api/scan', {ids: [p.id]})); actions.append(button);
    }
    actionsCell.append(actions); row.append(checkboxCell, titleCell, countCell, qualityCell, statusCell, actionsCell); fragment.append(row);
  }
  $('projects').replaceChildren(fragment);
  $('visible-count').textContent = `${filtered.length ? projectPage * pageSize + 1 : 0}–${projectPage * pageSize + projects.length} of ${filtered.length} matching projects`;
  $('project-page').textContent = `Page ${projectPage + 1} of ${Math.max(1, Math.ceil(filtered.length / pageSize))}`;
  $('previous-projects').disabled = projectPage === 0;
  $('next-projects').disabled = (projectPage + 1) * pageSize >= filtered.length;
  $('empty-library').hidden = projects.length > 0;
  const noSearch = state.projects.length === 0;
  $('empty-library').querySelector('h2').textContent = noSearch ? 'Your next collection starts here' : 'No projects match your filters';
  $('empty-connect').hidden = !noSearch;
  $('empty-connect').textContent = state.session.connected ? 'Refresh projects →' : 'Connect account →';
  updateSelection();
}
