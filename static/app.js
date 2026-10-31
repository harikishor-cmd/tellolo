// Child UI. Globals story/cur/flags are read by the browser tests.
let story = null, cur = 0, flags = {}, rec = null, kids = null, W = null, demoHero = null; window.__t = {};
function show(id) { document.querySelectorAll('main>section').forEach(s => s.classList.add('hidden')); $(id).classList.remove('hidden'); window.__screen = id; }
function speak(w) { window.__spoken = (window.__spoken || []).concat(w); if (!window.speechSynthesis) return; const u = new SpeechSynthesisUtterance(w); u.lang = story.language == 'hi' ? 'hi-IN' : 'en-US'; speechSynthesis.cancel(); speechSynthesis.speak(u); }
function renderPage() {
  const p = story.pages[cur]; $('title').textContent = story.title;
  fill($('dots'), ...story.pages.map((_, i) => el('span', {class: i == cur ? 'on' : flags[i] ? 'done' : ''})));
  fill($('chips'), 'Practising: ', ...story.trouble_words.map(w => el('span', {textContent: w})), story.parent ? el('i', {textContent: ' (from your last story)'}) : null);
  const img = typeof p.image == 'string' && p.image.startsWith('/out/') ? p.image : null;
  fill($('picbox'), img ? el('img', {class: 'pic', id: 'pic', src: img, alt: ''}) : el('div', {class: 'pic', textContent: '🎨 drawing…'}));
  const f = flags[cur];
  const words = f ? f.words.map(w => ({t: w.display, c: 'w ' + w.status, h: w.heard ? 'heard: ' + w.heard : ''}))
                  : p.text.split(/\s+/).filter(Boolean).map(t => ({t, c: 'w', h: ''}));
  fill($('text'), ...words.flatMap((w, i) => [i ? ' ' : null, el('span', {class: w.c, title: w.h, textContent: w.t, data: {w: w.t}})]));
  $('result').textContent = f ? (f.errors ? `${f.errors} tricky word${f.errors > 1 ? 's' : ''} on this page. Tap them to hear them!` : '🌟 Perfect reading!') : '';
  $('prev').disabled = cur == 0; $('nextp').disabled = cur == 4; $('nextStory').classList.toggle('hidden', !Object.keys(flags).length);
  const im = $('pic'); if (im && cur == 0 && !window.__t.firstPageMs) im.onload = () => { window.__t.firstPageMs = window.__t.firstPageMs || performance.now() - window.__t.imgStart; };
}
document.addEventListener('click', e => { const w = e.target.dataset && e.target.dataset.w; if (w) speak(w.replace(/[^\p{L}\p{M}\p{N}]/gu, '')); });
$('prev').onclick = () => { cur--; renderPage(); }; $('nextp').onclick = () => { cur++; renderPage(); };
async function drawPictures() {
  window.__t = {imgStart: performance.now()};
  try { await api('/api/images', JSON.stringify({id: story.id})); } catch (e) { return err($('result'), e, drawPictures); }
  const poll = async () => {
    let s; try { s = await api('/api/story/' + story.id); } catch (e) { return err($('result'), e, poll); }
    let changed = false; s.pages.forEach((p, i) => { if (p.image && !story.pages[i].image) { story.pages[i].image = p.image; changed = true; } });
    if (changed) { renderPage(); if (story.pages[0].image && !window.__t.firstSeenMs) window.__t.firstSeenMs = performance.now() - window.__t.imgStart; }
    if (['queued', 'running'].includes(s.images.status)) return setTimeout(poll, 700);
    const missing = s.pages.map((p, i) => p.image ? null : i + 1).filter(Boolean);
    if (missing.length) err($('result'), new Error(`Some pictures didn't draw (page ${missing.join(', ')}).`), s.images.retryable ? drawPictures : null);
    else window.__t.allMs = performance.now() - window.__t.imgStart;
  };
  poll();
}
async function startStory(req, url) {
  show('s-wait'); $('waitMsg').textContent = url ? 'Writing a new story with your tricky words…' : 'Writing your story…'; fill($('werr'));
  try { story = await api(url || '/api/story', JSON.stringify(req)); } catch (e) { return err($('werr'), e, () => startStory(req, url)); }
  cur = 0; flags = {}; show('s-book'); renderPage(); drawPictures(); $('parentLink').href = '/summary?child=' + story.child;
}
// Practice words and interests are picked from the fixed lists in words.json (the server accepts nothing else). Up to 3 each.
function picked(id) { return [...$(id).querySelectorAll('input:checked')].map(x => x.value); }
function renderPicks(sel) {
  const lang = $('lang').value, keep = sel || {int: picked('int'), tw: []};
  const box = (id, items) => fill($(id), ...items.map(([v, label]) => el('label', {}, el('input', {type: 'checkbox', value: v, checked: keep[id].includes(v),
    onchange: e => { if (picked(id).length > 3) e.target.checked = false; }}), label)));
  box('int', Object.entries(W.interests).map(([k, l]) => [k, l[lang]]));
  box('tw', W.practice[lang].map(w => [w, w]));
}
async function childFor(name) {
  if (!kids) kids = (await api('/api/children')).children;
  let k = kids.find(k => k.name == name);
  if (!k) { k = await api('/api/child', JSON.stringify({name})); kids.push(k); }
  return k.child;
}
async function demo(lang) {
  const p = (await api('/seed.json')).profiles[lang]; demoHero = {name: p.name, hero: p.hero};
  $('name').value = p.name; $('lang').value = p.lang; $('level').value = p.level; renderPicks({int: p.interests, tw: p.trouble_words}); $('make').click();
}
$('demoEn').onclick = () => demo('en'); $('demoHi').onclick = () => demo('hi');
$('make').onclick = async () => {
  const tw = picked('tw'), it = picked('int'); if (!tw.length) return err($('perr'), new Error('Pick at least one word to practise.'));
  const name = $('name').value.trim() || 'Reader'; let child;
  try { child = await childFor(name); } catch (e) { return err($('perr'), e); }
  const hero = demoHero && demoHero.name == name ? demoHero.hero : null;
  localStorage.tellolo_profile = JSON.stringify({name, lang: $('lang').value, level: $('level').value, int: it, tw, child});
  $('parentLink').href = '/summary?child=' + child;
  startStory({child, hero, lang: $('lang').value, level: $('level').value, trouble_words: tw, interests: it});
};
$('nextStory').onclick = () => startStory({id: story.id}, '/api/next');
$('lang').onchange = () => renderPicks();
$('rec').onclick = async () => {
  if (rec) { rec.stop(); return; }
  let s; try { s = await navigator.mediaDevices.getUserMedia({audio: true}); } catch (e) { return err($('result'), new Error('The microphone is blocked. Allow it in the browser and try again.')); }
  const ch = [], page = cur; rec = new MediaRecorder(s); rec.ondataavailable = e => ch.push(e.data);
  $('rec').classList.add('on'); $('rec').textContent = '■'; $('recHint').textContent = 'Reading… tap to stop';
  const stopAt = setTimeout(() => rec && rec.stop(), 60000);  // the server only listens to the first 60 s
  rec.onstop = () => {
    clearTimeout(stopAt); s.getTracks().forEach(t => t.stop()); rec = null; $('rec').classList.remove('on'); $('rec').textContent = '●'; $('recHint').textContent = 'Tap to read this page aloud';
    const send = async () => {
      $('result').textContent = 'Listening…'; const f = new FormData(); f.append('id', story.id); f.append('page', page); f.append('audio', new Blob(ch, {type: 'audio/webm'}), 'page.webm');
      try { flags[page] = await api('/api/read', f); if (cur == page) renderPage(); } catch (e) { err($('result'), e, send); }
    };
    send();
  };
  rec.start();
};
$('agree').onchange = () => $('consentGo').disabled = !$('agree').checked;
$('consentGo').onclick = () => { localStorage.tellolo_consent = new Date().toISOString(); show('s-profile'); const dq = new URLSearchParams(location.search).get('demo'); if (dq) demo(dq); };
$('privacyLink').onclick = e => { e.preventDefault(); $('agree').checked = !!localStorage.tellolo_consent; show('s-consent'); };
(async () => {
  try { W = await api('/words.json'); } catch (e) { show('s-profile'); return err($('perr'), e); }
  const p = savedProfile(), arr = x => Array.isArray(x) ? x : [];
  if (p) { $('name').value = p.name || ''; $('lang').value = p.lang == 'hi' ? 'hi' : 'en'; $('level').value = p.level == 'intermediate' ? 'intermediate' : 'beginner'; if (p.child) $('parentLink').href = '/summary?child=' + p.child; }
  renderPicks({int: arr(p && p.int), tw: arr(p && p.tw)});
  const q = new URLSearchParams(location.search), qid = q.get('id'), dq = q.get('demo');
  if (qid) api('/api/story/' + encodeURIComponent(qid)).then(j => { story = j; show('s-book'); renderPage(); $('parentLink').href = '/summary?child=' + j.child; }).catch(e => { show('s-profile'); err($('perr'), e); });
  else show(localStorage.tellolo_consent ? 's-profile' : 's-consent');
  if (dq && localStorage.tellolo_consent && !qid) demo(dq);
  api('/api/info').then(j => { if (j.provider == 'mock') $('prov').textContent = 'DEMO MODE (mock, no Meta calls)'; }).catch(() => {});
})();
