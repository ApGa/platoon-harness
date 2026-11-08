// platoon-harness: the sessions page, which `platoon-harness web` serves with no session. It spends the link the command
// said for a session token, which it keeps in this tab alone, lists every session under the root as the terminal's
// sessions screen does, and opens one by going to a control link of the page `web` serves it on. Whatever a session or
// the server says is put in as text, never as markup.
(function () {
  'use strict';
  const KEY = 'platoon-harness.sessions.token';
  const WAITING = 'Sent, and waiting for its answer.';
  const NO_LINK = 'Open the link `platoon-harness web` says on its terminal. It opens once, within ten minutes.';
  const $ = selector => document.querySelector(selector);
  let token = sessionStorage.getItem(KEY), found = null, busy = false;

  const say = (text, bad) => {
    $('#said').textContent = text;
    $('#said').classList.toggle('bad', !!bad);
  };

  async function post(route, body) {
    const r = await fetch(route, {method: 'POST', body: JSON.stringify(body || {}),
      headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}});
    const p = await r.json().catch(() => ({error: `The server answered ${r.status}.`}));
    if (r.status === 401) {
      sessionStorage.removeItem(KEY);
      token = null;
    }
    if (!r.ok) throw new Error(p.error);
    return p;
  }

  // A control the person cannot use now, and why. `disabled` would take it out of the keyboard's order, so it is
  // `aria-disabled`, and its reason is its title, which is its accessible description. Focus or a press shows the reason
  // beside it too, and a press does nothing else.
  const cannot = el => busy ? WAITING : el.xWhy ? el.xWhy() : null;
  const disable = (el, why) => {
    if (why) {
      el.setAttribute('aria-disabled', 'true');
      el.title = why;
    } else {
      el.removeAttribute('aria-disabled');
      el.removeAttribute('title');
    }
  };
  const disabledAt = target => target.closest && target.closest('[aria-disabled="true"]');
  const beside = el => el.parentElement.parentElement.querySelector('.why');
  document.addEventListener('focusin', e => {
    const el = disabledAt(e.target);
    if (el) beside(el).textContent = el.title;
  });
  document.addEventListener('focusout', e => {
    const el = disabledAt(e.target);
    if (el) beside(el).textContent = '';
  });
  document.addEventListener('click', e => {
    const el = disabledAt(e.target);
    if (!el) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    beside(el).textContent = el.title;
  }, true);
  const settle = () => document.querySelectorAll('[data-act]').forEach(el => disable(el, cannot(el)));

  function button(label, act, name, run, why) {
    const el = document.createElement('button');
    el.type = 'button';
    el.textContent = label;
    el.dataset.act = act;
    el.dataset.session = name;
    el.xWhy = why;
    el.addEventListener('click', run);
    return el;
  }

  function cell(tr, text, kind) {
    const td = document.createElement('td');
    td.textContent = text;
    if (kind) td.className = kind;
    tr.append(td);
    return td;
  }

  function row(session) {
    const tr = document.createElement('tr');
    tr.dataset.session = session.name;
    cell(tr, session.name, 'name');
    cell(tr, session.live ? 'live' : '—', session.live ? 'live' : '');
    cell(tr, session.state || 'unknown', 'state');
    const td = cell(tr, ''), acts = document.createElement('div'), why = document.createElement('p');
    acts.className = 'acts';
    why.className = 'why';
    acts.append(button('Open', 'open', session.name, () => open(session.name)));
    td.append(acts, why);
    return tr;
  }

  // Draw what the server found, giving focus back to the act that had it, as the list is drawn anew.
  function draw() {
    const had = document.activeElement && document.activeElement.dataset;
    $('#root').textContent = `Under ${found.root}.`;
    $('#sessions tbody').replaceChildren(...found.rows.map(row));
    $('#sessions').hidden = !found.rows.length;
    $('#none').hidden = !!found.rows.length;
    settle();
    if (had && had.act) {
      const again = [...document.querySelectorAll('[data-act]')]
        .find(el => el.dataset.act === had.act && el.dataset.session === had.session);
      if (again) again.focus();
    }
  }

  async function look() {
    if (!token) return say(NO_LINK, true);
    try {
      found = await post('/x/sessions');
      draw();
    } catch (x) {
      say(x.message, true);
    }
  }

  // One act at a time: every act waits, saying so, until its answer comes, and a refusal is said with its reason.
  async function act(route, body, saying) {
    busy = true;
    settle();
    say(saying);
    try {
      const p = await post(route, body);
      if (p.refused) say(p.refused, true);
      return p.refused ? null : p;
    } catch (x) {
      say(x.message, true);
      return null;
    } finally {
      busy = false;
      settle();
    }
  }

  async function open(name) {
    const p = await act('/x/open', {name}, `Opening ${name}.`);
    if (p) location.assign(p.link);
  }

  $('#look').addEventListener('click', look);
  addEventListener('pageshow', e => { if (e.persisted) look(); });
  const link = (location.hash.match(/(^#|&)link=([0-9a-f]{16,})/) || [])[2];
  if (!link) {
    look();
    return;
  }
  history.replaceState(null, '', location.pathname);
  sessionStorage.removeItem(KEY);  // so nothing older acts if this link is refused
  token = null;
  fetch('/x/exchange', {method: 'POST', body: '{}',
    headers: {'Authorization': 'Bearer ' + link, 'Content-Type': 'application/json'}})
    .then(async r => {
      const p = await r.json().catch(() => ({error: `The server answered ${r.status}.`}));
      if (!r.ok) throw new Error(p.error);
      token = p.token;
      sessionStorage.setItem(KEY, token);
      await look();
    })
    .catch(x => say(x.message, true));
})();
