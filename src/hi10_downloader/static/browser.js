async function screenshot() {
  if (!browserOpen || !unlocked || document.hidden || imageBusy || currentView !== 'session') return;
  imageBusy = true;
  try {
    const response = await fetch('/api/browser/image');
    if (!response.ok) return;
    const nextURL = URL.createObjectURL(await response.blob());
    $('browser-image').src = nextURL; $('browser-loading').hidden = true;
    if (imageURL) URL.revokeObjectURL(imageURL); imageURL = nextURL;
  } catch {} finally {imageBusy = false;}
}
function browserInput(data) {
  inputChain = inputChain.then(async () => {
    await api('/api/browser/action', data); await screenshot(); return true;
  }).catch(error => {toast(error.message); return false;});
  return inputChain;
}
