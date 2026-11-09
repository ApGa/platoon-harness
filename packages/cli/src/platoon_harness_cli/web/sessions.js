// platoon-harness: the sessions page, which `platoon-harness web` serves with no session. It spends the link the command
// said for a session token, which it keeps in this tab alone, lists every session under the root as the terminal's
// sessions screen does, and opens, starts, resumes, stops or replays one, going to a control link of the page `web`
// serves a session or its replay on to open it. It asks once before a resume, which can spend money, and before a stop,
// in the terminal's words, and asks what the server asks before a start and a save. Its team editor draws the
// project's team as the server makes its fields, from the team's schema, with each problem at its field. Whatever a
// session or the server says is put in as text, never as markup.
(function () {
  'use strict';
  const KEY = 'platoon-harness.sessions.token';
  const WAITING = 'Sent, and waiting for its answer.';
  const NO_LINK = 'Open the link `platoon-harness web` says on its terminal. It opens once, within ten minutes.';
  const UNLISTED = 'Start waits for the list, which says where a session starts and that starting can spend money.';
  const CHECKING = 'Waiting for the check of your last change.';
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
        () => session.live ? null : 'No runtime holds this session, so there is nothing to stop.'),
      button('Replay', 'replay', session.name, () => replay(session.name)));
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

  // One act at a time: every act waits, saying so, until its answer comes, and a refusal is said with its reason, where
  // `tell` says it.
  async function act(route, body, saying, tell = say) {
    busy = true;
    settle();
    tell(saying);
    try {
      const p = await post(route, body);
      if (p.refused) tell(p.refused, true);
      return p.refused ? null : p;
    } catch (x) {
      tell(x.message, true);
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

  async function replay(name) {
    const p = await act('/x/replay', {name}, `Opening a replay of ${name}, which acts on nothing.`);
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

  // A start asks what the server asks first, each once, and goes again with the answer: never without it. From the
  // project's team, the team editor's changes are saved first.
  async function start(form) {
    let args = {team: form.team.value.trim(), name: form.name.value.trim()};
    if (!args.team && changes() && !await save()) return;
    for (;;) {
      const p = await act('/x/start', args, 'Starting the session.');
      if (!p) return look();
      if (p.link) return location.assign(p.link);
      if (!await ask(p.ask.question, p.ask.yes)) return say('Nothing was started.');
      args = {...args, ...p.ask.answer};
    }
  }
  $('#start [data-act]').xWhy = () => {
    if (!found) return UNLISTED;
    if (T.edits.length && T.asked !== T.drawn) return CHECKING;
    if (!changes()) return null;
    if (!$('#start').team.value.trim()) return T.draft.blocked;
    return `Team file names another file, and the team editor holds changes to ${T.draft.file} not yet saved: save `
      + 'them, or leave Team file empty to start from them.';
  };
  $('#start').team.addEventListener('input', settle);
  $('#start').addEventListener('submit', e => {
    e.preventDefault();
    if (!cannot(e.target.querySelector('[data-act]'))) start(e.target);
  });

  // The team editor. A person's changes are edits the page keeps and sends whole with each check, so the server keeps no
  // draft: a field's change, an entry added or removed, each asks for a check, of which only the newest answer is drawn.
  // An add or a removal that could not be made is said once and dropped; a field keeps what was typed in it until it is
  // changed again. Save writes what the diff shows, asking what the server asks first, and refused because the file
  // changed since, the check that follows shows what it holds now with the changes on it.
  const T = {open: false, draft: null, edits: [], asked: 0, drawn: 0};
  const same = (a, b) => a.length === b.length && a.every((key, i) => key === b[i]);
  const changes = () => !!(T.edits.length && T.draft && T.draft.diff);
  const teamSay = (text, bad) => {
    $('#team-said').textContent = text;
    $('#team-said').classList.toggle('bad', !!bad);
  };
  let ids = 0;

  function element(tag, text, kind) {
    const el = document.createElement(tag);
    if (text != null) el.textContent = text;
    if (kind) el.className = kind;
    return el;
  }

  // Words that name keys and values between backticks, as the reference writes them, each name drawn as code, as text.
  function prose(tag, text, kind) {
    const el = element(tag, null, kind);
    el.append(...text.split('`').map((part, i) => i % 2 ? element('code', part) : part));
    return el;
  }

  function problemList(problems) {
    const list = element('ul', null, 'problems');
    list.id = `t${++ids}`;
    list.append(...problems.map(problem => prose('li', problem.said, problem.level)));
    return list;
  }

  function control(field, value) {
    let el;
    if (field.kind === 'choice' || field.kind === 'yes-no') {
      el = element('select');
      const option = (key, said) => Object.assign(element('option', said), {value: key});
      el.append(option('', field.empty), ...field.choices.map(choice => option(choice.value, choice.said)));
    } else if (field.kind === 'lines') {
      el = element('textarea');
      el.rows = 4;
    } else {
      el = element('input');
      el.placeholder = field.empty;
      el.autocomplete = 'off';
      if (field.kind === 'integer') el.inputMode = 'numeric';
      if (field.kind === 'number') el.inputMode = 'decimal';
    }
    el.spellcheck = false;
    el.value = value;
    return el;
  }

  // A field: its key, what it holds, what it takes, and each problem at it, which are its accessible description. One
  // that cannot be changed here says why first, and takes focus but no change. It shows what was typed in it last, until
  // a save or a read takes that change, and what is typed goes as a change once focus leaves it or Enter is pressed, so
  // a field drawn again as it is typed in, which keeps what was typed, loses none of it.
  function fieldBox(field, label, changed) {
    const box = element('div', null, 'field');
    const typed = [...T.edits].reverse().find(edit => edit.set && same(edit.set, field.path));
    const value = typed ? typed.to : field.text, el = control(field, value);
    const help = prose('p', field.fixed ? `${field.fixed} ${field.help}` : field.help, 'help');
    const problems = problemList(field.problems), name = element('label', label);
    el.id = `t${++ids}`;
    el.dataset.where = field.where;
    name.htmlFor = el.id;
    help.id = `${el.id}-help`;
    el.setAttribute('aria-describedby', `${help.id} ${problems.id}`);
    if (field.problems.some(problem => problem.level === 'error')) el.setAttribute('aria-invalid', 'true');
    if (field.kind === 'lines') box.classList.add('wide');
    if (field.fixed) {
      disable(el, field.fixed);
      if (el.tagName !== 'SELECT') el.readOnly = true;
    }
    let known = value;
    const commit = () => {
      const to = el.tagName === 'TEXTAREA' ? el.value : el.value.trim();
      if (field.fixed) el.value = known;
      else if (to !== known) changed(known = to);
    };
    if (el.tagName === 'SELECT') el.addEventListener('change', commit);
    else el.addEventListener('focusout', commit);
    if (el.tagName === 'INPUT') el.addEventListener('keydown', e => { if (e.key === 'Enter') commit(); });
    box.append(name, el, help, problems);
    return box;
  }

  function actButton(label, act, run) {
    const el = element('button', label);
    el.type = 'button';
    el.dataset.act = act;
    el.addEventListener('click', run);
    return el;
  }

  function groupBox(group) {
    const box = element('fieldset'), legend = element('legend', group.title);
    box.dataset.where = group.where;
    box.append(legend);
    if (group.about) box.append(prose('p', group.about, 'help'));
    const fields = element('div', null, 'fields');
    for (const field of group.fields) {
      const label = field.path.slice(group.path.length).join('.');
      fields.append(fieldBox(field, label, to => change({set: field.path, to})));
    }
    box.append(problemList(group.problems), fields);
    if (group.kept) box.append(prose('p', group.kept, 'help'));
    if (group.removable) {
      box.append(element('div', null, 'acts'));
      box.lastChild.append(actButton(`Remove ${group.title}`, 'remove', () => change({remove: group.path})));
    }
    return box;
  }

  // An entry to add: its name, typed or chosen, and the field it needs, given as it is added.
  function addingBox(adding) {
    const box = element('div', null, 'adding'), name = adding.names.length
      ? control({kind: 'choice', empty: 'choose one', choices: adding.names.map(value => ({value, said: value}))}, '')
      : control({kind: 'text', empty: 'a name'}, '');
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', adding.title);
    name.id = `t${++ids}`;
    const named = element('label', adding.names.length ? 'preset' : 'name');
    named.htmlFor = name.id;
    box.append(named, name);
    let first = null;
    if (adding.first) {
      first = control(adding.first, '');
      first.id = `t${++ids}`;
      const help = prose('p', adding.first.help, 'help');
      const label = element('label', adding.first.path.join('.') || 'values');
      help.id = `${first.id}-help`;
      first.setAttribute('aria-describedby', help.id);
      label.htmlFor = first.id;
      box.append(label, first, help);
    }
    box.append(element('div', null, 'acts'));
    box.lastChild.append(actButton(adding.title, 'add', () => {
      const to = first ? (first.tagName === 'TEXTAREA' ? first.value : first.value.trim()) : '';
      change({add: [...adding.under, name.value.trim()], to});
    }));
    return box;
  }

  function sectionBox(section) {
    const box = element('section'), heading = element('h3', section.title);
    heading.id = `t${++ids}`;
    box.setAttribute('aria-labelledby', heading.id);
    box.append(heading, ...section.groups.map(groupBox), ...section.adding.map(addingBox));
    return box;
  }

  function diffLines(diff) {
    if (!diff) return [element('span', 'Nothing: the draft is the file as it stands.')];
    return diff.replace(/\n$/, '').split('\n').map(line => element('span', `${line}\n`,
      /^\+(?!\+\+ )/.test(line) ? 'added' : /^-(?!-- )/.test(line) ? 'removed' : ''));
  }

  // Draw the newest answer, giving focus back to the field or act that had it, with what was typed in it.
  function drawTeam() {
    const had = document.activeElement, where = had && had.dataset && had.dataset.where;
    const typed = where && 'value' in had ? [had.value, had.selectionStart, had.selectionEnd] : null;
    const act = had && had.dataset && had.dataset.act, d = T.draft;
    if (d) {
      $('#editor-about').textContent = `${d.file}, in ${d.here}, which Start starts from when Team file is empty.`
        + (changes() ? ' Your changes are not saved yet: Save saves them, and Start saves them first.' : '');
      const top = element('div');
      if (d.kept) top.append(prose('p', d.kept, 'help'));
      top.append(problemList(d.problems));
      $('#team-top').replaceChildren(top);
      $('#team-form').replaceChildren(...d.sections.map(sectionBox));
      $('#preview').textContent = d.shown
        || 'Nothing yet: the loader takes no team from this draft, as its problems say.';
      $('#diff').replaceChildren(...diffLines(d.diff));
    }
    settle();
    const again = where ? $(`#team-form [data-where="${CSS.escape(where)}"]`)
      : act ? $(`#editor [data-act="${act}"]`) : null;
    if (again && !$('#editor').contains(had)) {
      again.focus();
      if (typed && again.value !== typed[0]) {
        again.value = typed[0];
        if (again.setSelectionRange && typed[1] != null) again.setSelectionRange(typed[1], typed[2]);
      }
    }
  }

  // Check the draft the edits make, `route` reading the file and this machine's harnesses again as well.
  async function check(route = '/x/check') {
    const n = ++T.asked, sent = T.edits.slice();
    settle();
    let d;
    try {
      d = await post(route, {edits: sent});
    } catch (x) {
      if (n === T.asked) {
        T.drawn = n;
        teamSay(x.message, true);
        settle();
      }
      return;
    }
    if (n !== T.asked) return;
    T.drawn = n;
    if (d.refused) {
      teamSay(d.refused, true);
      settle();
      return;
    }
    const unmade = new Set(d.unmade.map(i => sent[i]).filter(edit => !edit.set));
    T.edits = T.edits.filter(edit => !unmade.has(edit));
    T.draft = d;
    drawTeam();
  }

  function change(edit) {
    if (edit.set) T.edits = T.edits.filter(old => !(old.set && same(old.set, edit.set)));
    T.edits.push(edit);
    check();
  }

  async function save() {
    const sent = T.edits.slice();
    let args = {base: T.draft.base, edits: sent};
    for (;;) {
      const p = await act('/x/save', args, `Saving ${T.draft.file}.`, teamSay);
      if (!p) {
        await check();
        return false;
      }
      if (p.said) {
        T.edits = T.edits.filter(edit => !sent.includes(edit));
        teamSay(p.said);
        await check();
        return true;
      }
      if (!await ask(p.ask.question, p.ask.yes)) {
        teamSay('Nothing was saved.');
        return false;
      }
      args = {...args, ...p.ask.answer};
    }
  }

  $('#save').xWhy = () => !T.draft ? 'Edit reads the team first.' : T.asked !== T.drawn ? CHECKING : T.draft.blocked;
  $('#save').addEventListener('click', () => { if (!cannot($('#save'))) save(); });
  $('#reread').addEventListener('click', async () => {
    if (cannot($('#reread'))) return;
    const file = T.draft ? T.draft.file : 'the team file';
    const question = `Read ${file} and this machine's harnesses again, dropping your changes?`;
    if (T.edits.length && !await ask(question, 'Read again')) return;
    T.edits = [];
    teamSay('');
    check('/x/team');
  });
  $('#edit').addEventListener('click', () => {
    if (cannot($('#edit'))) return;
    T.open = !T.open;
    $('#editor').hidden = !T.open;
    $('#edit').setAttribute('aria-expanded', String(T.open));
    $('#edit').textContent = T.open ? 'Close' : 'Edit';
    if (T.open && !T.draft && T.asked === T.drawn) check('/x/team');
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
