// Parent page: one child at a time, and only a child this browser's session owns (the server checks).
const p = savedProfile(), child = new URLSearchParams(location.search).get('child') || (p && p.child);
if (p && p.child == child && p.name) $('hello').textContent = p.name + "'s reading progress";
const card = (big, label) => el('div', {class: 'card'}, el('div', {class: 'big', textContent: String(big)}), label);
const pct = r => r == null ? '-' : Math.round(100 - 100 * r) + '%';
function render(d) {
  if (d.child_name) $('hello').textContent = d.child_name + "'s reading progress";
  const rows = d.rows.filter(r => r.pages_read);
  if (!rows.length) return fill($('s'), el('div', {class: 'card', textContent: 'No reading yet. Stories your child reads will show up here.'}));
  const pages = rows.reduce((a, r) => a + r.pages_read, 0), rated = rows.filter(r => r.avg_error_rate != null);
  const acc = rated.length ? rated.reduce((a, r) => a + r.avg_error_rate, 0) / rated.length : null;
  const head = el('tr', {}, ...['Story', 'Language', 'Practised', 'Pages', 'Read well', 'Tricky words'].map(t => el('th', {textContent: t})));
  const tr = r => el('tr', {},
    el('td', {}, r.title || '', r.parent ? el('span', {class: 'tag', textContent: ' follow-up'}) : null, r.mode != 'real' ? el('span', {class: 'tag', textContent: ' ' + r.mode}) : null),
    el('td', {textContent: r.language == 'hi' ? 'Hindi' : 'English'}), el('td', {textContent: (r.trouble_words || []).join(', ')}),
    el('td', {textContent: r.pages_read + '/5'}), el('td', {textContent: pct(r.avg_error_rate)}), el('td', {textContent: r.flagged.join(', ')}));
  fill($('s'),
    el('div', {class: 'row'}, card(rows.length, 'stories read'), card(pages, 'pages read aloud'), card(acc == null ? '-' : Math.round(100 - 100 * acc) + '%', 'words read well')),
    el('div', {class: 'card'}, el('b', {textContent: 'Next story will practise: '}), el('span', {class: 'chips'}, ...(rows[0].next_words.length ? rows[0].next_words.map(w => el('span', {textContent: w})) : ['-']))),
    el('div', {class: 'card'}, el('table', {}, head, ...rows.map(tr))));
}
if (!child) fill($('s'), el('div', {class: 'card', textContent: 'Make a story first; its progress will show up here.'}));
else {
  api('/api/summary?child=' + encodeURIComponent(child)).then(render).catch(e => fill($('s'), el('span', {class: 'err', textContent: 'Could not load: ' + e.message})));
  $('forget').classList.remove('hidden');
  $('forget').onclick = async () => {
    if (!confirm('Delete all stories, reading results and the name saved for this child? This cannot be undone.')) return;
    try {
      const d = await api('/api/forget', JSON.stringify({child}));
      if (p && p.child == child) localStorage.removeItem('tellolo_profile');
      fill($('s'), el('div', {class: 'card', textContent: `Deleted ${d.stories_deleted} stories and the saved name.`})); $('forget').classList.add('hidden');
    } catch (e) { alert(e.message); }
  };
}
