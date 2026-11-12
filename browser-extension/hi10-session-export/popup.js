'use strict';
const button = document.getElementById('export');
const status = document.getElementById('status');
button.addEventListener('click', async () => {
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  status.textContent = 'Reading Hi10 cookies…';
  try {
    let cookies;
    try { cookies = await chrome.cookies.getAll({domain: 'hi10anime.com'}); }
    catch { throw new Error('Cannot read Hi10 cookies. Check this extension’s site permission and browser profile.'); }
    const state = Hi10SessionExport.toStorageState(cookies);
    const json = JSON.stringify(state, null, 2) + '\n';
    if (new TextEncoder().encode(json).length > 2 * 1024 * 1024) throw new Error('Session file exceeds the app’s 2 MB import limit.');
    const url = URL.createObjectURL(new Blob([json], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'session.json';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    status.textContent = 'Download requested. Import session.json in the app; the app will verify access.';
  } catch (error) {
    status.textContent = error.message || 'Could not export the session.';
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
});
