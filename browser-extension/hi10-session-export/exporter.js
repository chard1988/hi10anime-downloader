'use strict';
function toStorageState(cookies, now = Date.now() / 1000) {
  const sameSites = {strict: 'Strict', lax: 'Lax', no_restriction: 'None', unspecified: 'Lax'};
  const selected = cookies.filter(cookie =>
    typeof cookie.domain === 'string' && cookie.domain.replace(/^\./, '') === 'hi10anime.com' &&
    !cookie.partitionKey && (cookie.session || cookie.expirationDate === undefined || cookie.expirationDate > now)
  );
  if (!selected.length) throw new Error('No Hi10 cookies found. Use the Chrome profile where you are signed in to Hi10.');
  if (selected.length > 1000) throw new Error('Too many cookies to import. No file was saved.');
  return {cookies: selected.map(cookie => {
    if (!['name', 'value', 'domain', 'path'].every(key => typeof cookie[key] === 'string') ||
        !cookie.path.startsWith('/') ||
        (cookie.expirationDate !== undefined && !Number.isFinite(cookie.expirationDate))) {
      throw new Error('Invalid Hi10 cookie data. No file was saved.');
    }
    return {name: cookie.name, value: cookie.value, domain: cookie.domain, path: cookie.path,
      expires: cookie.session || cookie.expirationDate === undefined ? -1 : cookie.expirationDate,
      httpOnly: !!cookie.httpOnly, secure: !!cookie.secure, sameSite: sameSites[cookie.sameSite] || 'Lax'};
  }), origins: []};
}
globalThis.Hi10SessionExport = {toStorageState};
if (typeof module !== 'undefined') module.exports = {toStorageState};
