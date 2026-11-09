function fileRow(file, disabled = false) {
  const row = node('div', undefined, 'detail-row'), description = node('div');
  description.append(node('strong', file.filename), node('small', `Selected: ${qualityLabel(file.selected)} · ${file.qualities.length} quality option${file.qualities.length === 1 ? '' : 's'}`));
  const select = node('select'); select.dataset.key = file.key; select.setAttribute('aria-label', `Quality for ${file.filename}`);
  select.append(new Option(file.section_id ? 'Section preference' : 'Project preference', '0'));
  file.qualities.filter(q => q > 0).forEach(q => select.append(new Option(qualityLabel(q), String(q))));
  select.value = detail.choices[file.key] || 0; select.disabled = operationsBusy() || disabled;
  row.append(description, select); return row;
}
function updateSectionCount() {
  const enabled = new Set([...$('detail-files').querySelectorAll('input[data-section]:checked')].map(input => input.dataset.section));
  const count = detail.files.filter(file => !detail.sections.length || enabled.has(file.section_id)).length;
  $('detail-count').textContent = `${count} file${count === 1 ? '' : 's'} selected${detail.sections.length ? ` · ${enabled.size} of ${detail.sections.length} sections` : ' · one variant per file'}`;
}
async function openDetails(id) {
  if (pendingAction) return;
  pendingAction={path:'/api/details',ids:[id],label:'Loading project files…'}; render();
  try {
    detail = await api(`/api/project/${id}`); detail.sections ||= []; $('detail-title').textContent = detail.title;
    $('detail-description').textContent = detail.sections.length ? 'Choose which series to include and a preferred quality for each section. Individual file choices override the section preference. Each series gets its own subfolder.' : 'Choose a quality for each file. “Project preference” uses your project’s setting, with a fallback to highest available.';
    const fragment = document.createDocumentFragment();
    if (detail.sections.length) {
      const tools = node('div', undefined, 'section-tools');
      for (const [text, checked] of [['Include all sections', true], ['Clear selection', false]]) {
        const button = node('button', text, 'text-button'); button.disabled = operationsBusy();
        button.onclick = () => $('detail-files').querySelectorAll('input[data-section]').forEach(input => {input.checked = checked; input.dispatchEvent(new Event('change'));});
        tools.append(button);
      }
      fragment.append(tools);
      for (const section of detail.sections) {
        const card = node('section', undefined, 'collection-section'), toolbar = node('div', undefined, 'section-toolbar');
        const label = node('label'), checkbox = node('input'); checkbox.type = 'checkbox'; checkbox.dataset.section = section.id; checkbox.checked = section.enabled; checkbox.disabled = operationsBusy();
        checkbox.setAttribute('aria-label', `Include ${section.title}`);
        const title = node('div'); title.append(node('strong', section.title), node('small', `${section.count} file${section.count === 1 ? '' : 's'} · ${section.qualities.map(qualityLabel).join(' / ')}`));
        label.append(checkbox, title);
        const quality = node('select'); quality.dataset.sectionQuality = section.id; quality.setAttribute('aria-label', `Quality preference for section ${section.title}`);
        quality.append(new Option('Project preference', '0')); section.qualities.filter(q => q > 0).forEach(q => quality.append(new Option(`Prefer ${q}p`, String(q)))); quality.value = section.preferred;
        toolbar.append(label, quality);
        const files = node('details', undefined, 'section-files'); files.open = section.count <= 5;
        files.append(node('summary', `Review ${section.count} file${section.count === 1 ? '' : 's'}`));
        let loaded=false;
        const loadFiles=()=>{if(loaded || !files.open) return;loaded=true;for(const file of detail.files.filter(file=>file.section_id===section.id)) files.append(fileRow(file,!checkbox.checked));};
        files.addEventListener('toggle',loadFiles); loadFiles();
        checkbox.onchange = () => {card.classList.toggle('section-disabled', !checkbox.checked); card.querySelectorAll('select').forEach(select => select.disabled = operationsBusy() || !checkbox.checked); updateSectionCount();};
        quality.disabled = operationsBusy() || !section.enabled; card.classList.toggle('section-disabled', !section.enabled);
        card.append(toolbar, files); fragment.append(card);
      }
    } else {
      for (const file of detail.files) fragment.append(fileRow(file));
    }
    $('detail-files').replaceChildren(fragment); updateSectionCount();
    $('save-details').disabled = operationsBusy() || !!pendingAction; $('detail-dialog').showModal();
  } catch(error) {toast(error.message);}
  finally {pendingAction=null;render(); $('save-details').disabled=operationsBusy();}
}
