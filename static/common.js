// Shared by index.html and summary.html. Page content is only ever built with DOM nodes and textContent (never parsed as HTML),
// so story text, titles and names from the model or a parent can't turn into markup.
const $ = id => document.getElementById(id);
function el(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const k in props || {}) {
    if (k == 'class') e.className = props[k]; else if (k == 'data') Object.assign(e.dataset, props[k]); else e[k] = props[k];
  }
  for (const c of kids) if (c != null) e.append(c);
  return e;
}
function fill(box, ...kids) { box.replaceChildren(...kids.filter(k => k != null)); }
function err(box, e, retry) { fill(box, '⚠ ' + e.message, retry ? el('button', {class: 'btn alt mini', textContent: 'Try again', onclick: retry}) : null); }
// Every API call sends X-Tellolo (blocks cross-site requests) and the session cookie. A 401 asks for the passcode once.
async function api(u, b, again) {
  const h = {'X-Tellolo': '1'}; if (b !== undefined && !(b instanceof FormData)) h['Content-Type'] = 'application/json';
  let r;
  try { r = await fetch(u, {method: b === undefined ? 'GET' : 'POST', body: b, headers: h, credentials: 'same-origin'}); }
  catch (e) { throw new Error("Can't reach Tellolo. Is it running?"); }
  const j = await r.json().catch(() => ({error: 'Unexpected reply'}));
  if (r.status == 401 && j.passcode && !again) {
    const p = prompt('Tellolo passcode (ask the person who shared this link):');
    if (p !== null) { await api('/api/login', JSON.stringify({passcode: p}), true).catch(() => {}); return api(u, b, true); }
  }
  if (!r.ok) throw new Error(j.error || 'Error ' + r.status);
  return j;
}
function savedProfile() { try { return JSON.parse(localStorage.tellolo_profile || 'null'); } catch (e) { return null; } }
