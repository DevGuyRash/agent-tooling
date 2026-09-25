const event = (action, data = {}) => fetch('/api/events', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ action, ...data }) }).catch(() => {});
const menu = document.querySelector('#menu-toggle');
menu.addEventListener('click', () => {
  const expanded = menu.getAttribute('aria-expanded') !== 'true';
  menu.setAttribute('aria-expanded', String(expanded)); document.querySelector('#more-links').hidden = !expanded;
  if (expanded) event('menu-open');
});
if (location.pathname === '/venue') event('venue-view');
if (location.pathname === '/program') {
  const day = new URL(location.href).searchParams.get('day') === 'two' ? 'two' : 'one';
  document.querySelector('#day-title').textContent = `Day ${day} · ${day === 'one' ? '14' : '15'} October`;
  document.querySelector('#day-intro').textContent = day === 'one' ? 'How can people shape the places they share?' : 'What helps a promising idea become everyday practice?';
  document.querySelector(`[data-day="${day}"]`).setAttribute('aria-current', 'page');
  event('program-day', { day });
  const list = document.querySelector('#schedule-list');
  let lastRange = -1;
  list.addEventListener('scroll', () => { const range = Math.floor(list.scrollTop / 200); if (range !== lastRange) { lastRange = range; event('schedule-scroll', { day, value: String(range) }); } });
  fetch(`/sessions?day=${day}`).then(response => response.json()).then(sessions => {
    list.replaceChildren();
    for (const session of sessions) {
      const row = document.createElement('article'); row.className = 'session'; row.dataset.sessionId = session.id;
      const time = document.createElement('time'); time.textContent = session.time;
      const content = document.createElement('div'), heading = document.createElement('h3'), room = document.createElement('p');
      heading.textContent = session.title; room.textContent = session.room; content.append(heading, room);
      const details = document.createElement('a'); details.href = `#session-${session.id}`; details.textContent = 'Details';
      details.addEventListener('click', click => {
        click.preventDefault(); history.replaceState(null, '', `?day=${day}#session-${session.id}`);
        document.querySelector('#session-title').textContent = session.title;
        document.querySelector('#session-body').textContent = `${session.time} · ${session.room} · ${session.speaker}`;
        document.querySelector('#session-detail').showModal(); event('session-open', { day, id: session.id });
      });
      row.append(time, content, details); list.append(row);
    }
    list.setAttribute('aria-busy', 'false');
    document.querySelector('#close-session').addEventListener('click', () => { document.querySelector('#session-detail').close(); history.replaceState(null, '', `?day=${day}#schedule`); });
  });
}
