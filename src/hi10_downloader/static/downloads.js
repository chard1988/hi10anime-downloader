function bytes(value) { if (!value) return '0 B'; const units = ['B','KB','MB','GB','TB']; const unit = Math.min(Math.floor(Math.log(value)/Math.log(1024)), 4); return `${(value/1024**unit).toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`; }
function updateQueueSelection() {
  const page=state.downloads;
  $('select-queue-page').disabled=page.length===0;
  $('select-queue-page').checked=page.length>0 && page.every(e=>queueSelected.has(e.id));
  $('select-queue-page').indeterminate=page.some(e=>queueSelected.has(e.id)) && !page.every(e=>queueSelected.has(e.id));
  $('queue-selection-count').textContent=`${queueSelected.size} selected across pages`;
  $('start-selected-downloads').disabled=!queueSelected.size || !canStartDownloads() || !!pendingAction;
  $('remove-selected-downloads').disabled=!queueSelected.size || operationsBusy() || !!pendingAction;
  $('clear-queue-selection').disabled=!queueSelected.size || !!pendingAction;
}
function downloadItemRow(item) {
    const card = node('article', undefined, 'download-item'), header = node('div', undefined, 'download-header'), meta = node('div', undefined, 'download-meta');
    const details=node('div',undefined,'download-details');details.id=`queue-details-${item.id}`;details.hidden=!expandedDownloads.has(item.id);
    const checkbox=node('input');checkbox.type='checkbox';checkbox.checked=queueSelected.has(item.id);checkbox.setAttribute('aria-label',`Select ${item.filename}`);
    checkbox.onchange=()=>{checkbox.checked?queueSelected.add(item.id):queueSelected.delete(item.id);lastDownloads='';updateQueueSelection();};header.append(checkbox);
    const toggle=node('button',undefined,'download-expand');
    toggle.setAttribute('aria-expanded',String(!details.hidden));toggle.setAttribute('aria-controls',details.id);
    const chevron=node('span',details.hidden?'▸':'▾','download-chevron');chevron.setAttribute('aria-hidden','true');
    toggle.append(chevron,node('strong',item.filename));
    toggle.title='Show or hide download details';
    toggle.onclick=()=>{details.hidden=!details.hidden;details.hidden?expandedDownloads.delete(item.id):expandedDownloads.add(item.id);toggle.setAttribute('aria-expanded',String(!details.hidden));chevron.textContent=details.hidden?'▸':'▾';};
    header.append(toggle,node('span',item.status));
    meta.append(node('span', item.project), node('span', item.total ? `${bytes(item.bytes)} / ${bytes(item.total)}` : bytes(item.bytes)));
    details.append(meta);
    const destination=node('p',undefined,'download-destination');destination.append(node('strong','Destination'),node('code',item.destination || 'Destination unavailable for this older queue record.'));details.append(destination);
    card.append(header,details);
    if (item.status === 'downloading' || item.status === 'complete') { const bar = node('progress'); bar.max = item.total || 1; if (item.total) bar.value = item.bytes; bar.setAttribute('aria-label', `Download progress for ${item.filename}`); details.append(bar); }
    if (item.message) {const message=node('div',undefined,'download-error-detail');message.append(node('strong',item.status==='failed'?'Failure reason':'Details'),node('p',item.message));details.append(message);}
    const controls=node('div',undefined,'download-row-actions');
    const iconControl=(tag,label,glyph)=>{
      const control=node(tag,undefined,'secondary small icon-button');
      control.title=label;control.setAttribute('aria-label',label);
      const icon=node('span',glyph);icon.setAttribute('aria-hidden','true');control.append(icon);
      return control;
    };
    const retry=iconControl('button',item.status === 'queued' ? 'Start this item' : 'Retry download','↻');
    retry.disabled=!['queued','interrupted','failed'].includes(item.status) || !canStartDownloads() || !!pendingAction;
    retry.onclick=()=>action('/api/downloads/retry',{id:item.id});
    const view=iconControl('button','View download link','🔗');
    view.onclick=async()=>{
      view.disabled=true;view.setAttribute('aria-busy','true');
      const spinner=node('span',undefined,'button-spinner');view.replaceChildren(spinner);
      try{const result=await api(`/api/download-link/${encodeURIComponent(item.id)}`);editingDownloadId=item.id;$('download-link-value').value=result.url;const editable=['queued','failed','interrupted'].includes(item.status) && !operationsBusy();$('download-link-value').readOnly=!editable;$('save-download-link').disabled=!editable;$('download-link-help').textContent=editable?'Paste a replacement direct download URL. Saving does not start a download.':'Stop running jobs before editing. Only pending or failed items can be edited.';$('download-link-dialog').showModal();}
      catch(error){toast(error.message);}
      finally{view.disabled=false;view.removeAttribute('aria-busy');const icon=node('span','🔗');icon.setAttribute('aria-hidden','true');view.replaceChildren(icon);}
    };
    const open=iconControl('a','Open in new tab','↗');open.href=`/api/download-link/${encodeURIComponent(item.id)}?open=1`;open.target='_blank';open.rel='noopener noreferrer';
    controls.append(view,open,retry);
    if (['queued','interrupted','failed'].includes(item.status)) {
      const remove=iconControl('button','Remove from queue','×');remove.classList.add('danger');
      remove.disabled=operationsBusy() || !!pendingAction;remove.onclick=()=>action('/api/downloads/remove',{id:item.id});controls.append(remove);
    }
    header.append(controls);
    return card;
}
function updateQueueProjectSelection() {
  $('queue-project-selection-count').textContent=`${queueProjectsSelected.size} projects selected`;
  $('exclude-queue-projects').disabled=!queueProjectsSelected.size || operationsBusy() || !!pendingAction;
  $('clear-queue-project-selection').disabled=!queueProjectsSelected.size || !!pendingAction;
}
function renderDownloads() {
  updateQueueSelection();updateQueueProjectSelection();
  const signature=JSON.stringify([state.downloads,state.download_groups,state.download_page,state.job.running,state.download_job?.running,pendingAction,[...queueSelected]]);
  if(signature===lastDownloads)return;
  lastDownloads=signature;
  const fragment=document.createDocumentFragment();
  for(const group of state.download_groups || []) {
    const section=node('details',undefined,'queue-project-group');section.open=expandedQueueGroups.has(group.id);
    const summary=node('summary');
    const projectCheck=node('input');projectCheck.type='checkbox';projectCheck.checked=queueProjectsSelected.has(group.id);projectCheck.disabled=!projectsById.has(group.id);projectCheck.setAttribute('aria-label',`Select project ${group.title} for exclusion`);
    projectCheck.onclick=event=>event.stopPropagation();
    projectCheck.onchange=()=>{projectCheck.checked?queueProjectsSelected.add(group.id):queueProjectsSelected.delete(group.id);updateQueueProjectSelection();};
    summary.append(projectCheck);summary.append(node('strong',group.title),node('span',`${group.count} items · ${group.complete} completed · ${group.failed} failed`));
    const body=node('div',undefined,'queue-project-items');let loaded=false;
    const load=()=>{
      if(!section.open || loaded)return;loaded=true;
      const items=state.downloads.filter(item=>item.group_id===group.id);
      const total=Math.max(1,Math.ceil(group.count/50));
      let page=group.page || 0;
      const draw=()=>{
        body.replaceChildren(...items.map(downloadItemRow));
        if(!group.loaded)body.append(node('p','Loading files…','muted'));
        if(total>1){
          const nav=node('div',undefined,'pagination');
          const prev=node('button','←','secondary small'),next=node('button','→','secondary small');
          prev.setAttribute('aria-label',`Previous items for ${group.title}`);next.setAttribute('aria-label',`Next items for ${group.title}`);
          prev.disabled=page===0;next.disabled=page===total-1;
          prev.onclick=()=>{queueGroupPages.set(group.id,page-1);refreshState();};next.onclick=()=>{queueGroupPages.set(group.id,page+1);refreshState();};
          nav.append(prev,node('span',`Items ${page*50+1}–${Math.min((page+1)*50,group.count)} of ${group.count}`),next);body.append(nav);
        }
      };draw();
    };
    section.ontoggle=()=>{const changed=section.open!==expandedQueueGroups.has(group.id);section.open?expandedQueueGroups.add(group.id):expandedQueueGroups.delete(group.id);load();if(changed)refreshState().then(()=>{if(section.open && !state.download_groups.find(g=>g.id===group.id)?.loaded)refreshState();});};
    section.append(summary,body);fragment.append(section);load();
  }
  $('download-list').replaceChildren(fragment); $('empty-downloads').hidden=state.download_filtered_total>0;
}
function renderDownloadStartProgress() {
  const job=state.download_job || {};
  for(const [id,source,label] of [['start-downloads','all','Start downloads'],['start-selected-downloads','selected','Start selected']]) {
    const button=$(id),active=job.running && (job.source || 'all')===source;
    button.setAttribute('aria-busy',String(!!active));
    if(active) {
      const count=`${job.done || 0}/${job.total || 0}`;
      button.replaceChildren(node('span',undefined,'button-spinner'),node('span',`${label} ${count}`));
      button.setAttribute('aria-label',`${label}: ${job.done || 0} of ${job.total || 0} files processed`);
      button.disabled=true;
    } else if(!pendingAction) {
      button.textContent=id==='start-downloads'?`▶ ${label}`:label;
      button.removeAttribute('aria-label');
    }
  }
}
