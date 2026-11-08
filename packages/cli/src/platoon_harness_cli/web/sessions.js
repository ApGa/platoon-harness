// platoon-harness: the sessions page, which `platoon-harness web` serves with no session. It spends the link the command
// said for a session token, which it keeps in this tab alone, lists every session under the root as the terminal's
// sessions screen does, and opens, starts, resumes or stops one, going to a control link of the page `web` serves a
// session on to open it. It asks once before a resume, which can spend money, and before a stop, in the terminal's words,
// and asks what the server asks before a start. Whatever a session or the server says is put in as text, never as
// markup.
(function () {
  'use strict';
  const KEY = 'platoon-harness.sessions.token';
  const WAITING = 'Sent, and waiting for its answer.';
  const NO_LINK = 'Open the link `platoon-harness web` says on its terminal. It opens once, within ten minutes.';
  const UNLISTED = 'Start waits for the list, which says where a session starts and that starting can spend money.';
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
  // beside it too, over the page, so nothing under the pointer moves, and a press does nothing else.
  const cannot = el => !token ? NO_LINK : busy ? WAITING : el.xWhy ? el.xWhy() : null;
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
  const showWhy = el => {
    const tip = $('#tip'), r = el.getBoundingClientRect();
    tip.textContent = el.title;
    tip.hidden = false;
    tip.style.left = Math.max(8, Math.min(r.left, innerWidth - 370)) + 'px';
    tip.style.top = r.bottom + 6 + 'px';
  };
  document.addEventListener('focusin', e => {
    const el = disabledAt(e.target);
    if (el) showWhy(el);
  });
  document.addEventListener('focusout', () => { $('#tip').hidden = true; });
  addEventListener('scroll', () => { $('#tip').hidden = true; }, true);
  document.addEventListener('click', e => {
    const el = disabledAt(e.target);
    if (!el) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    showWhy(el);
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
    const td = cell(tr, ''), acts = document.createElement('div');
    acts.className = 'acts';
    acts.append(
      button('Open', 'open', session.name, () => open(session.name)),
      button('Resume', 'resume', session.name, () => resume(session.name),
        () => session.live ? 'A runtime holds this session: Open opens it.' : null),
      button('Stop', 'stop', session.name, () => stop(session.name),
        () => session.live ? null : 'No runtime holds this session, so there is nothing to stop.'));
    td.append(acts);
    return tr;
  }

  // Ask a question in a dialog, and say whether the person said yes. Cancel has focus first, as nothing asked is
  // taken back, and Esc is a no.
  function ask(question, yes) {
    const box = $('#ask');
    $('#question').textContent = question;
    $('#yes').textContent = yes;
    box.returnValue = '';
    box.showModal();
    return new Promise(resolve => box.addEventListener('close', () => resolve(box.returnValue === 'yes'), {once: true}));
  }
  $('#yes').addEventListener('click', () => $('#ask').close('yes'));
  $('#no').addEventListener('click', () => $('#ask').close('no'));

  // Draw what the server found, giving focus back to the act that had it, as the list is drawn anew.
  function draw() {
    const had = document.activeElement && document.activeElement.dataset;
    $('#root').textContent = `Under ${found.root}.`;
    $('#team-about').textContent = found.project
      ? `Read from ${found.here}. Left empty, the project's own, ${found.project}.`
      : `Read from ${found.here}, which has no project file: name a team file, or write one with \`platoon-harness init\`.`;
    $('#cost').textContent = `Starting launches its team's harnesses here, in ${found.here}, which can spend money, ` +
      'and they run on once you leave this page, until you stop them. What the team runs as you, and several agents ' +
      'on one plan login, are asked about first.';
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
    settle();
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

  async function resume(name) {
    if (!await ask(`Resume ${name}? Its harnesses come back, which can spend money.`, 'Resume')) return;
    const p = await act('/x/resume', {name}, `Resuming ${name}.`);
    if (p) location.assign(p.link); else look();
  }

  async function stop(name) {
    if (!await ask(`Stop ${name}? Its turns are interrupted and its harnesses end; it stays resumable.`, 'Stop')) return;
    const p = await act('/x/stop', {name}, `Stopping ${name}: its runtime is letting go.`);
    if (p) say(p.said);
    look();
  }

  // A start asks what the server asks first, each once, and goes again with the answer: never without it.
  async function start(form) {
    let args = {team: form.team.value.trim(), name: form.name.value.trim()};
    for (;;) {
      const p = await act('/x/start', args, 'Starting the session.');
      if (!p) return look();
      if (p.link) return location.assign(p.link);
      if (!await ask(p.ask.question, p.ask.yes)) return say('Nothing was started.');
      args = {...args, ...p.ask.answer};
    }
  }
  $('#start [data-act]').xWhy = () => found ? null : UNLISTED;
  $('#start').addEventListener('submit', e => {
    e.preventDefault();
    if (!cannot(e.target.querySelector('[data-act]'))) start(e.target);
  });

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
