// ---------------------------------------------------------------------- platoon-harness

// platoon-harness's overlay, which follows SwarmChat's script in this one script. It uses only the names that script
// declares at its top level, and puts new markup only through its html template, which escapes all it is given. What
// it changes says what is so: delivered where SwarmChat says read, agents and people told apart, and what a person
// may do, each act through /x/command, and each act they may not take shown, disabled, with the reason, which the
// keyboard and a screen reader reach as the mouse does. Every pane of ours reads through x_read, in Python's words.

// What this page may do, read from view_info before the page starts: `credential`, view or control, `live`, whether a
// runtime holds the session, `person`, who acts here, `may`, the ops their grants hold, `forms`, a form for each op the
// person holds that writes, `confirmed`, the ops asked about before they run, `body_limit`, the most bytes a body may
// be, and `cannot`, why this page may do nothing, when it may not. The feed keeps `live` current.
const X = {caps: null};

// What is not built over a session yet, and why: what the brief asks the page to show.
X.unbuilt = {tasks: 'Not built yet: the tasks and board views are planned, with each task open, claimed and by whom ' +
    'under what lease, or done, and each board entry with its versions. This chat holds what its queue or board announced.',
  activity: 'Not built yet: an agent\'s tool calls and their output, apart from its chats, are planned.'};

// What the Provenance pane says first: what the record holds, and what it cannot.
X.RECORD = 'This is what the record holds: a citation is the agent\'s claim, being handed something is not using it, and ' +
  'what reached an agent through a file or a shell leaves nothing here. An estimate is its producer\'s, never a fact.';

// Only an agent leaves evidence of what reached it, so only an agent can be seen as.
X.AS_AGENT = 'Only an agent leaves evidence of what reached it, so only an agent can be seen as.';

// A session's messages take no reactions, so a post's votes are unknown, and nothing can be ranked by them.
X.UNVOTED = 'A session\'s messages take no reactions, so there are no votes to count or to rank by.';

// The acts of a person's page, each a label, the op it runs, and what it adds to the agent: an agent's own, and the
// session's, on the person's own page.
X.acts = {interrupt: ['Interrupt', 'agent.interrupt'], 'stop-below': ['Stop below', 'agent.interrupt', {below: true}],
  retire: ['Retire', 'agent.retire'], cancel: ['Cancel', 'agent.cancel'],
  close: ['Close the session', 'session.close'], 'cancel-session': ['Cancel the session', 'session.cancel']};

// Why the person cannot run `op` here now, or null when they can. A message also needs a `chat` that takes one.
X.cannot = (op, chat) => {
  const caps = X.caps;
  if (!caps) return 'Loading what this page may do.';
  if (caps.cannot) return caps.cannot;
  if (S.route.as) return `You see the session as ${name(S.route.as)}, and an act is yours: see it as everyone to act.`;
  if (chat && !chat.x_to) {
    return chat.kind === 'channel' ? 'A queue or a board takes its work by its own commands, not by a message.'
      : 'This chat is between others, and you are not in it, so it takes no message from you.';
  }
  return caps.may.includes(op) ? null : `Your grants hold no ${op}.`;
};

// A control the person cannot use now, and why. `disabled` would take it out of the keyboard's order, so it is
// `aria-disabled`, and its reason is its title, which is its accessible description: a screen reader reads it with the
// control, and the mouse shows it over it. Focus or a press shows it beside the control too, and a press does nothing
// else. `X.disabled` draws a control so, and `X.disable` makes one so, or with no reason usable again, its own title back.
X.disabled = why => why ? html` aria-disabled="true" title="${why}"` : html``;
X.disable = (el, why) => {
  const was = el.getAttribute('aria-disabled') === 'true';
  if (why) {
    if (!was && el.title) el.dataset.xTitle = el.title;
    el.setAttribute('aria-disabled', 'true');
    el.title = why;
  } else if (was) {
    el.removeAttribute('aria-disabled');
    if (el.dataset.xTitle) el.title = el.dataset.xTitle; else el.removeAttribute('title');
    delete el.dataset.xTitle;
  }
};
X.disabledAt = target => target.closest && target.closest('[aria-disabled="true"]');
X.showWhy = el => {
  const tip = $('#tip'), r = el.getBoundingClientRect();
  clearTimeout(toastTimer);
  tip.textContent = el.title;
  tip.style.transform = '';
  tip.style.left = Math.max(8, Math.min(r.left, innerWidth - 370)) + 'px';
  tip.classList.add('on');
  tip.style.top = (r.bottom + 6 + tip.offsetHeight > innerHeight ? r.top - 6 - tip.offsetHeight : r.bottom + 6) + 'px';
};
document.addEventListener('focusin', e => {
  const el = X.disabledAt(e.target);
  if (el) X.showWhy(el);
});
document.addEventListener('focusout', e => {
  const el = X.disabledAt(e.target);
  if (el && $('#tip').textContent === el.title) $('#tip').classList.remove('on');
});
// SwarmChat hides its tip whenever the pointer is over anything with no tip of its own, as when a list is drawn again
// under a still pointer, so a focused control's reason shows again then: it stays beside it while it has focus. The
// window hears the event after SwarmChat's listener on the document.
addEventListener('mouseover', () => {
  const el = document.activeElement && X.disabledAt(document.activeElement), tip = $('#tip');
  if (el && tip.textContent === el.title) tip.classList.add('on');
});
document.addEventListener('click', e => {
  const el = X.disabledAt(e.target);
  if (!el) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  X.showWhy(el);
}, true);

// What a control the person pressed says while it waits for the act's answer.
X.WAITING = 'Sent, and waiting for its answer.';

// What the page draws as a button that is no button element takes Enter and Space as a button does.
document.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('[role="button"]')) {
    e.preventDefault();
    e.target.click();
  }
});

X.kind = id => (user(id).fields || {}).kind;

// Read what this page may do again, and draw what it shows again with it.
X.refresh = async () => {
  const r = await baseApi('view_info');
  X.caps = r.x;
  S.server.read_only = r.read_only;
  S.liveState = '';
  setLive(r.read_only ? 'ro' : 'on');
  S.viewKey = null; S.paneKey = null;
  route();
  X.needed();
};

document.head.insertAdjacentHTML('beforeend', `<style>
.av.x-human { border-radius: 50%; }
.x-composer { display: grid; grid-template-columns: 1fr auto; gap: 6px 8px; padding: 8px 16px 12px; border-top: 1px solid var(--line); }
.x-composer .x-to, .x-composer .x-why, .x-composer .x-file { grid-column: 1 / -1; margin: 0; color: var(--faint); font-size: 12px; }
.x-composer .x-file:empty, .x-composer .x-why:empty { display: none; }
.x-composer textarea { font: inherit; resize: none; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line2); background: var(--panel); color: inherit; }
.x-composer .x-buttons { display: flex; flex-direction: column; gap: 6px; }
.x-card { margin: 6px 0; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line2); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.x-card.x-done { color: var(--faint); }
.x-acts { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.person > .x-acts { margin-top: 14px; }
.x-said { color: var(--muted); font-size: 12.5px; margin: 8px 0 0; }
.x-said:empty { display: none; }
.pop .it.x-need { display: grid; gap: 6px; cursor: default; }
.pop.x-ask { max-width: 380px; }
.x-provenance .x-part { padding: 12px 14px 4px; font-weight: 700; }
.x-provenance .x-line { display: grid; grid-template-columns: 76px 1fr; gap: 8px; width: 100%; padding: 5px 14px; border: 0; background: none; color: inherit; font: inherit; font-size: 12.5px; line-height: 1.45; text-align: left; overflow-wrap: anywhere; }
.x-provenance .x-line[data-x-follow] { cursor: pointer; }
.x-provenance .x-line[data-x-follow]:hover, .x-provenance .x-line[data-x-follow]:focus-visible { background: var(--hover); }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; max-width: calc(100% - 32px); opacity: 0; pointer-events: none; }
.msg:hover .actions, .msg:focus-within .actions { opacity: 1; pointer-events: auto; }
.x-provenance .x-kind { color: var(--faint); }
.x-provenance .x-warn { color: var(--warn); }
.x-form { display: grid; gap: 12px; padding: 12px 14px; }
.x-form .x-about { margin: 0; color: var(--muted); font-size: 12.5px; }
.x-form .x-field { display: grid; gap: 4px; }
.x-form .x-help { margin: 0; color: var(--faint); font-size: 12px; overflow-wrap: anywhere; }
.x-form input, .x-form textarea, .x-form select { font: inherit; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--line2); background: var(--panel); color: inherit; }
.x-form textarea { resize: vertical; }
.x-form .x-acts { margin-top: 2px; }
.x-form .x-said { margin: 0; overflow-wrap: anywhere; }
.x-review .x-change { display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; padding: 4px 14px; font-size: 12.5px; white-space: pre-wrap; overflow-wrap: anywhere; }
.x-review .x-heading { padding-top: 12px; }
.x-review .x-path, .x-review .x-more { padding-left: 28px; }
.x-review > .x-about, .x-review .x-end, .x-review .x-comment { padding: 8px 14px; margin: 0; font-size: 12.5px; }
.x-tone-strong { font-weight: 700; }
.x-tone-faint { color: var(--faint); }
.x-tone-good { color: var(--good); }
.x-tone-bad { color: var(--bad); }
.x-tone-warn { color: var(--warn); }
.x-patch { font-family: var(--mono); font-size: 12px; line-height: 1.45; overflow-x: auto; }
.x-patch .x-pl { display: grid; grid-template-columns: 52px 1fr; white-space: pre; }
.x-patch .x-pl.x-chosen { background: var(--hover); box-shadow: inset 3px 0 var(--accent); }
.x-patch .x-n { border: 0; background: none; color: var(--faint); font: inherit; text-align: right; padding: 0 8px 0 0; cursor: pointer; }
.x-patch .x-goes-on > span::before { content: "↳ "; color: var(--faint); }
.x-review .x-below { color: var(--warn); margin: 0; }
.x-comment { display: grid; gap: 6px; border-top: 1px solid var(--line); }
.x-comment textarea { font: inherit; resize: vertical; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--line2); background: var(--panel); color: inherit; }
.x-comment .x-said, .x-comment .x-about { margin: 0; }
[aria-disabled="true"] { opacity: .55; cursor: not-allowed; }
</style>`);

$('#find').insertAdjacentHTML('beforebegin', html`<button class="find" data-x-commands title="Each op you hold that writes, run through its form">Commands</button><button class="find" data-x-review="changes" title="What changed: each commit with its test and patch, and each workspace's uncommitted diff">Review changes</button>`.s);

$('#login p').textContent = 'This page opens from a link that platoon-harness web says, or one a page acting for you ' +
  'made. Each link opens once, so ask for a new one.';
$('#login input').placeholder = 'Session token';

const baseApi = api;
api = async (name, params) => {
  const r = await baseApi(name, params);
  if (name === 'view_feed' && r.x && X.caps && r.x.live !== X.caps.live) X.refresh();
  return r;
};

const baseStart = start;
start = async function () {
  try {
    X.caps = (await baseApi('view_info')).x;
  } catch (e) {
    return login(e.status === 401 ? null : e.message);
  }
  await baseStart();
  X.needed();
  X.resend();
};

// SwarmChat says its token was refused, which here means this page's session has ended.
const baseLogin = login;
login = error => baseLogin(!error || /token was refused/.test(error)
  ? 'This page\'s session has ended: web stopped, or twelve hours went by. Open a new link.' : error);

const baseSetLive = setLive;
setLive = state => {
  baseSetLive(state);
  $('#live').title = {on: 'Following the session\'s journal as it grows',
    ro: X.caps && X.caps.cannot ? X.caps.cannot : 'No runtime holds this session, so this is its history.',
    off: 'Lost web. Trying again.'}[state] || '';
};

// An address that names someone who cannot be seen as shows everyone, and a board sorted by votes is sorted new, each
// saying why. A board with no sort is sorted new too, where SwarmChat sorts it hot. The pane is one thing at a time, so
// a thread or what had reached an agent takes it from provenance, an op's form or what changed, provenance from a form
// or what changed, and a form from what changed. A form's `args` go with it.
KEYS.push('provenance', 'act', 'args', 'review');
const baseReadRoute = readRoute;
readRoute = () => {
  const r = baseReadRoute();
  if (r.thread || r.knew) { delete r.provenance; delete r.act; delete r.review; }
  if (r.provenance) { delete r.act; delete r.review; }
  if (r.act) delete r.review;
  if (!r.act) delete r.args;
  if (r.as && X.kind(r.as) && X.kind(r.as) !== 'agent') { toast(X.AS_AGENT); delete r.as; }
  if (r.layout === 'board' && !['new', 'active'].includes(r.sort)) {
    if (r.sort) toast(X.UNVOTED);
    r.sort = 'new';
  }
  return r;
};

// The pane shows a pane of ours while the address names one: an event's provenance, `provenance=`, an op's form,
// `act=`, filled in with `args=` where an action of a place in Needs you opened it with what it fixes, or what changed
// or a diff, `review=`. SwarmChat's own route takes the pane for a thread, for what had reached an agent and for the map,
// and otherwise leaves it to this one. A pane drawn again for the same address keeps what was typed in it, and says
// again what it may do now.
X.ours = pane => pane instanceof X.Provenance || pane instanceof X.Form || pane instanceof X.Review;
const baseRoute = route;
route = async function () {
  if (X.ours(S.pane)) S.paneKey = '';
  await baseRoute();
  const r = S.route, pane = $('#pane');
  if (r.layout === 'map' || r.thread || r.knew) return;
  const [key, Pane] = r.provenance ? ['provenance', X.Provenance] : r.act ? ['act', X.Form]
    : r.review ? ['review', X.Review] : [];
  if (!key) {
    if (X.ours(S.pane)) { S.pane.destroy(); S.pane = null; pane.classList.remove('open'); pane.replaceChildren(); }
    return;
  }
  if (!(S.pane instanceof Pane && S.pane.name === r[key] && S.pane.args === r.args)) {
    if (S.pane && S.pane.destroy) S.pane.destroy();
    S.pane = new Pane(r[key], r.args);
  } else if (S.pane.paint) S.pane.paint();
  S.paneKey = `${key}|${r[key]}|${r.args || ''}`;
  pane.classList.add('open');
};

// Esc closes a pane of ours as it closes SwarmChat's own.
const baseKey = onKey;
onKey = e => e.key === 'Escape' && !overlay.on && (S.route.provenance || S.route.act || S.route.review)
  ? go({provenance: null, act: null, args: null, review: null}, true) : baseKey(e);

// A popover gives focus back as it closes to what had it as it opened, or to what `X.back` finds in its place once that
// was drawn again, so the keyboard goes on from where it was.
const baseOpen = overlay.open, baseClose = overlay.close;
overlay.open = function (content, anchor) {
  const opener = document.activeElement;
  X.back = () => opener;
  baseOpen.call(this, content, anchor);
};
overlay.close = function () {
  const back = X.back && X.back();
  X.back = null;
  baseClose.call(this);
  if (back && back.isConnected && document.activeElement === document.body) back.focus();
};

// A request's card drawn again while focus is in it keeps focus: on the same control, or on what the card now says came
// of it, which a screen reader then reads.
const baseApply = apply;
apply = events => {
  const at = document.activeElement, card = at && at.closest && at.closest('[data-x-card]');
  baseApply(events);
  const again = card && !card.isConnected && $(`[data-x-card="${CSS.escape(card.dataset.xCard)}"]`);
  if (again) ((at.dataset.xDecide && $(`[data-x-decide="${at.dataset.xDecide}"]`, again)) || again).focus();
  X.needed();
};

// ---------------------------------------------------------------------- acting

// Each act is one op, sent to /x/command under a key the page makes once, for one draft or press, and keeps until the
// act is answered. Until then it is kept in this tab's storage and sent again, after a lost connection, a reload, or a
// new link opened in this tab, and web answers a key it has seen with its first answer, whichever link sends it, so the
// act is one operation. A refusal is an answer.
X.ACTS = 'platoon-harness.acts';
X.pending = (() => { try { return JSON.parse(sessionStorage.getItem(X.ACTS)) || {}; } catch (_) { return {}; } })();
X.keep = () => { try { sessionStorage.setItem(X.ACTS, JSON.stringify(X.pending)); } catch (_) { /* kept in memory */ } };
X.key = () => [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join('');
X.UNANSWERED = 'Not answered: this page\'s session ended first. Open a new link in this tab, and it goes again under ' +
  'its key, so it takes effect once.';

// Send one command until it is answered, and give its outcome: the op's result, or its refusal, which a request web
// would not take is too, and one web failed on says that whether it took effect is unknown. A request that reached
// nothing, or that web was too busy for, goes again. A page whose session has ended is answered nothing: null.
X.send = async (key, command) => {
  for (;;) {
    let r = null;
    try {
      r = await fetch('/x/command', {method: 'POST', body: JSON.stringify({...command, key}),
        headers: {'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'}});
    } catch (_) { /* reached nothing: sent again below */ }
    if (r && r.status !== 503) {
      const p = await r.json().catch(() => ({error: `web answered ${r.status}`}));
      if (r.status === 401) { login(p.error); return null; }
      if (r.ok) return p;
      return {refusal: r.status < 500 ? {code: 'refused', detail: p.error}
        : {code: 'failed', detail: `web failed on it (${r.status}): whether it took effect is unknown`}};
    }
    setLive('off');
    await sleep(2000);
  }
};

// One act, kept until it is answered, with what `more` says beside its args: its outcome, or null while it waits for a
// new link.
X.act = async (op, args, more = {}) => {
  const key = X.key(), command = {op, args, ...more};
  X.pending[key] = command;
  X.keep();
  const r = await X.send(key, command);
  if (r) { delete X.pending[key]; X.keep(); }
  return r;
};

// What a reload or a new link found unanswered, sent again under its key. A view link acts on nothing, so what waits
// goes on waiting for a control link opened in this tab, rather than coming back refused when it may have been done.
X.resend = () => {
  const waiting = Object.entries(X.pending);
  if (waiting.length && X.caps.credential !== 'control') {
    toast(`${plural(waiting.length, 'act')} not yet answered ${waiting.length === 1 ? 'waits' : 'wait'} for a control ` +
      'link opened in this tab, as a view link acts on nothing.');
    return;
  }
  for (const [key, command] of waiting) {
    X.send(key, command).then(r => {
      if (!r) return;
      delete X.pending[key]; X.keep();
      toast(`${command.op}, sent before the page was reloaded: ${r.refusal ? X.refused(r.refusal) : 'done'}.`);
    });
  }
};

// A link opened over this page is the gate's to spend, so the page loads again for it, and draws nothing first for an
// address it is leaving, whose reads the reload would cut off.
addEventListener('hashchange', e => {
  if (!/(^#|&)link=/.test(location.hash)) return;
  e.stopImmediatePropagation();
  location.reload();
});

// A refusal as a person reads it. A decision someone made first says who made it and through what.
X.refused = refusal => {
  const d = refusal.detail;
  if (refusal.code === 'conflict' && d && d.resolved_by) {
    return `Already decided by ${d.resolved_by.replace(/^[a-z]+:/, '')}${d.via ? ` via ${d.via}` : ''}.`;
  }
  return `${refusal.code}: ${typeof d === 'string' ? d : JSON.stringify(d)}`;
};

// Ask before an act that nothing takes back, beside what asked for it.
X.ask = (anchor, question, yes) => new Promise(resolve => {
  const box = document.createElement('div');
  box.className = 'pop x-ask';
  box.innerHTML = html`<div class="ph">${question}</div><div class="x-acts"><button class="btn primary" data-x-yes>${yes}</button><button class="btn" data-x-no>Keep it</button></div>`.s;
  overlay.open(box, anchor);
  const answer = yes => { overlay.close(); resolve(yes); };
  $('.shade', overlay.el).onclick = () => answer(false);
  box.addEventListener('click', e => { if (e.target.closest('[data-x-yes]')) answer(true); else if (e.target.closest('[data-x-no]')) answer(false); });
  $('[data-x-no]', box).focus();
});

// ---------------------------------------------------------------------- the composer

// What a person writes, by draft: to a chat, or in reply to one message. A draft keeps its text and its file, and
// while it is sent, what is happening, so that a composer drawn again shows it as it stands.
X.drafts = {};
X.draft = key => X.drafts[key] ||= {text: '', file: null, sending: '', said: ''};

X.composer = (draft, chat, label) => html`<form class="x-composer" data-x-draft="${draft}" data-x-chat="${chat}"><p class="x-to">${label}</p><textarea rows="2" aria-label="Message" placeholder="Enter sends, Shift+Enter starts a new line">${X.draft(draft).text}</textarea><div class="x-buttons"><button class="btn primary">Send</button><button type="button" class="btn" data-x-attach title="A file to send as the message's body, of at most ${bytes(X.caps.body_limit)}">Attach</button></div><input type="file" hidden data-x-file><p class="x-file"></p><p class="x-why" aria-live="polite"></p></form>`;

// Why a composer cannot send now, or null when it can: a reply also needs a message it can cite.
X.unsendable = f => X.cannot('message.send', S.chats.get(f.dataset.xChat) || {}) || f.dataset.xWhy || null;

// Draw a draft's composer as its draft stands.
X.paint = draft => {
  const f = $(`.x-composer[data-x-draft="${CSS.escape(draft)}"]`);
  if (!f) return;
  const d = X.draft(draft), why = X.unsendable(f);
  const t = $('textarea', f);
  t.readOnly = !!(why || d.sending);
  X.disable(t, why);
  for (const b of $$('button', f)) X.disable(b, why || d.sending || null);
  $('.x-file', f).textContent = d.file ? `With ${d.file.name}, ${bytes(d.file.size)}, as its body.` : '';
  $('.x-why', f).textContent = why || d.sending || d.said;
};

document.addEventListener('keydown', e => {
  const t = e.target;
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && t.matches && t.matches('.x-composer textarea')) {
    e.preventDefault();
    t.form.requestSubmit();
  }
});
document.addEventListener('input', e => {
  const f = e.target.closest && e.target.closest('.x-composer');
  if (f && e.target.matches('textarea')) X.draft(f.dataset.xDraft).text = e.target.value;
});
document.addEventListener('change', e => {
  const f = e.target.closest && e.target.closest('.x-composer');
  if (!f || !e.target.matches('[data-x-file]')) return;
  const file = e.target.files[0], d = X.draft(f.dataset.xDraft), limit = X.caps.body_limit;
  e.target.value = '';
  if (!file) return;
  d.said = file.size > limit ? `${file.name} is ${num(file.size)} bytes, more than the ${num(limit)} a body may be.` : '';
  d.file = d.said ? null : file;
  X.paint(f.dataset.xDraft);
});
document.addEventListener('submit', e => {
  const f = e.target.closest('.x-composer');
  if (!f) return;
  e.preventDefault();
  X.post(f);
});

// Send a draft: its file first, if it has one, saying how much has gone, then the message, whose gist web makes of the
// text, said beside its args, and the file's name as the terminal makes it. Once it is sent, the draft lets go of what
// it sent, and of nothing chosen since.
X.post = async f => {
  const draft = f.dataset.xDraft, d = X.draft(draft), text = d.text.trim(), file = d.file;
  if (d.sending || (!text && !file) || X.unsendable(f)) return;
  const args = {to: S.chats.get(f.dataset.xChat).x_to};
  if (f.dataset.xReplyTo) args.reply_to = f.dataset.xReplyTo;
  const show = said => { d.sending = said; X.paint(draft); };
  try {
    if (file) args.body = await X.upload(file, share => show(`Sending ${file.name}: ${Math.round(100 * share)}%`));
    show('Sending…');
    const r = await X.act('message.send', args, file ? {text, file: file.name} : {text});
    d.said = !r ? X.UNANSWERED : r.refusal ? X.refused(r.refusal) : '';
    if (r && !r.refusal) {
      d.text = '';
      if (d.file === file) d.file = null;
      const t = $(`.x-composer[data-x-draft="${CSS.escape(draft)}"] textarea`);
      if (t) t.value = '';
    }
  } catch (error) {
    d.said = `Not sent: ${error.message}.`;
  }
  show('');
};

// Store a file as a body and give its ref, telling `progress` the share of it sent.
X.upload = (file, progress) => new Promise((resolve, reject) => {
  const r = new XMLHttpRequest();
  r.open('POST', '/x/body');
  r.setRequestHeader('Authorization', 'Bearer ' + TOKEN);
  r.setRequestHeader('Content-Type', 'application/octet-stream');
  r.upload.onprogress = e => { if (e.lengthComputable) progress(e.loaded / e.total); };
  r.onload = () => {
    let p;
    try { p = JSON.parse(r.responseText); } catch (_) { p = {error: `the server answered ${r.status}`}; }
    if (r.status === 200 && p.ref) resolve(p.ref);
    else reject(new Error(p.error || X.refused(p.refusal)));
  };
  r.onerror = () => reject(new Error(`${file.name} did not reach web`));
  progress(0);
  r.send(file);
});

// ---------------------------------------------------------------------- where the person must act

// Each place the person must act, with the actions that settle it, read through x_read's attention pane, as it was when
// last read, and why it cannot be shown while it is null: until it is first read, or when web would not read it.
X.needs = null;
X.needsWhy = 'Reading where you must act.';
X.needed = throttle(async () => {
  try {
    X.needs = (await api('x_read', {pane: 'attention'})).rows;
    X.needsWhy = null;
  } catch (e) {
    if (e.status) { X.needs = null; X.needsWhy = e.message; }
  }
  buildSide();
  if (X.needsBox && X.needsBox.isConnected) X.drawNeeds(X.needsBox);
}, 1000);

// The sidebar, drawn again as the session moves or as it scrolls, keeps focus on Needs you, the one row of it that
// takes focus.
const baseDraw = side.draw;
side.draw = function () {
  const had = document.activeElement && document.activeElement.matches('[data-x-needs]');
  baseDraw.call(this);
  const row = had && document.activeElement === document.body && $('[data-x-needs]');
  if (row) row.focus();
};

// Needs you takes focus as it opens, so Tab reaches its actions first, and gives it back to its row, which is drawn
// again as places come and go. Drawn again itself, it keeps focus on the action that had it, or takes it.
X.openNeeds = () => {
  X.needsBox = document.createElement('div');
  X.needsBox.className = 'pop x-needs';
  X.needsBox.tabIndex = -1;
  X.needsBox.setAttribute('role', 'dialog');
  X.needsBox.setAttribute('aria-label', 'Needs you');
  X.drawNeeds(X.needsBox);
  overlay.open(X.needsBox, $('[data-x-needs]'));
  X.back = () => $('[data-x-needs]');
  X.needsBox.focus();
};

X.drawNeeds = box => {
  const rows = X.needs || [], at = box.contains(document.activeElement) && document.activeElement;
  box.innerHTML = html`<div class="ph">${rows.length ? `Needs you: ${plural(rows.length, 'place')}` : 'Nothing needs you now.'}</div>${rows.map(row => html`<div class="it x-need"><span class="t"${row.agent ? html` data-x-goto="${row.agent}"` : ''}>⚠ <b>${row.kind}</b>${row.agent ? html` ${avatar(row.agent, 'sm')} ${name(row.agent)}` : ''}: ${row.gist}</span><span class="x-acts">${row.actions.map((action, i) => {
    const why = X.cannot(action.op);
    return html`<button class="btn" data-x-action="${i}" data-x-place="${row.id}"${X.disabled(why)}>${action.label}</button>`;
  })}</span></div>`)}`.s;
  if (!at || at === box) return;
  const same = $(`[data-x-place="${CSS.escape(at.dataset.xPlace)}"][data-x-action="${at.dataset.xAction}"]`, box);
  (same || box).focus();
};

// ---------------------------------------------------------------------- every op the person holds that writes

// Commands, in the top bar: a form for each op the person holds that writes, as view_info gives them, found by typing
// as Search finds. Choosing one opens its form in the pane.
X.openCommands = () => {
  const box = document.createElement('div');
  box.className = 'palette';
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-label', 'Commands');
  box.innerHTML = html`<input placeholder="Find a command" aria-label="Find a command" spellcheck="false"><div class="res"></div>`.s;
  overlay.open(box);
  const input = $('input', box), res = $('.res', box);
  let found = [], at = 0;
  const mark = () => $$('.it', res).forEach(it => it.classList.toggle('on', +it.dataset.i === at));
  const draw = () => {
    const words = input.value.trim().toLowerCase();
    found = X.caps.forms.filter(form => `${form.title} ${form.op} ${form.summary}`.toLowerCase().includes(words));
    at = Math.min(at, Math.max(0, found.length - 1));
    res.innerHTML = (found.length
      ? html`${found.map((form, i) => html`<div class="it" data-i="${i}"><span class="t">${form.title}</span><span class="s">${form.summary}</span></div>`)}`
      : html`<div class="grp">${X.caps.forms.length ? 'No command holds those words.' : 'You hold no op that writes.'}</div>`).s;
    mark();
  };
  const choose = form => {
    overlay.close();
    go({act: form.op, args: null, provenance: null, review: null, thread: null, knew: null}, true);
  };
  input.addEventListener('input', () => { at = 0; draw(); });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { at = Math.min(found.length - 1, at + 1); mark(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { at = Math.max(0, at - 1); mark(); e.preventDefault(); }
    else if (e.key === 'Enter' && found[at]) choose(found[at]);
  });
  res.addEventListener('click', e => { const it = e.target.closest('[data-i]'); if (it) choose(found[+it.dataset.i]); });
  draw();
  input.focus();
};

// What a form shows of a value: yes or no, several separated by commas, JSON as its text, and nothing for null.
X.shown = value => value === true ? 'yes' : value === false ? 'no' : value == null ? ''
  : Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : String(value);

// One field of a form: its flag, whether it is needed, and its help, which is the field's description until the field
// is disabled and says why instead. What it holds when left empty, the op's own default, shows in it.
X.field = (field, i) => {
  const id = `x-field-${i}`, empty = X.shown(field.default);
  const about = html` id="${id}" data-x-field="${i}" title="${field.help}"`;
  const choices = field.kind === 'yes-no' ? [true, false] : field.choices;
  const input = choices.length
    ? html`<select${about}><option value="">${empty}</option>${choices.map((choice, j) => html`<option value="${j}">${X.shown(choice)}</option>`)}</select>`
    : ['json', 'body'].includes(field.kind) ? html`<textarea${about} rows="3" placeholder="${empty}" spellcheck="false"></textarea>`
      : html`<input${about} placeholder="${empty}" spellcheck="false">`;
  return html`<div class="x-field"><label for="${id}"><code>${field.flag}</code>${field.required ? ' (needed)' : ''}</label>${input}<p class="x-help" aria-hidden="true">${field.help}</p></div>`;
};

// An op's form in the pane, made from what view_info gives of it: what the op does, as its command's help says it, a
// field for each of its command's flags, and Run, which asks once first for an op the terminal asks about. Every field
// and Run are disabled where the page may not run the op, saying why. What came of the act is said under Run. Opened
// by an action of a place in Needs you, its fields hold what that action fixes, `args`, as JSON in the address.
X.Form = class {
  constructor(op, args) {
    this.name = op;
    this.args = args;
    this.form = X.caps.forms.find(form => form.op === op);
    const f = this.form;
    $('#pane').innerHTML = html`<div class="phead"><h2>${f ? f.title : op}</h2><button class="close" data-close-pane title="Close">×</button></div><div class="scroll">${f
      ? html`<form class="x-form" data-x-op="${op}"><p class="x-about">${f.said}</p>${f.fields.map(X.field)}<div class="x-acts"><button class="btn primary" data-x-run>Run</button></div><p class="x-said" aria-live="polite"></p></form>`
      : html`<div class="note">${`No op ${op} that writes is yours to run here: Commands lists each one you hold.`}</div>`}</div>`.s;
    this.box = $('#pane .x-form');
    if (this.box && args) this.fill(args);
    this.paint();
  }
  fill(args) {
    let given = null;
    try { given = JSON.parse(args); } catch (_) { /* said below */ }
    if (!given || typeof given !== 'object' || Array.isArray(given)) {
      $('.x-said', this.box).textContent = 'The address\'s args are no JSON object, so no field is filled in from them.';
      return;
    }
    this.form.fields.forEach((field, i) => {
      if (!Object.hasOwn(given, field.name)) return;
      const el = $(`[data-x-field="${i}"]`, this.box), value = given[field.name];
      if (el.tagName !== 'SELECT') el.value = X.shown(value);
      else el.value = String((field.kind === 'yes-no' ? [true, false] : field.choices).indexOf(value));
    });
  }
  paint() {
    if (!this.box) return;
    const why = X.cannot(this.form.op);
    for (const el of $$('[data-x-field]', this.box)) {
      if (el.tagName !== 'SELECT') el.readOnly = !!why;
      X.disable(el, why);
    }
    X.disable($('[data-x-run]', this.box), why || (this.sending ? X.WAITING : null));
  }
  destroy() { this.dead = true; }
};

// The args a form's fields make, each taking what its kind takes, or an error saying what a field takes. A field left
// empty is left out, so the op's own default stands.
X.args = (form, box) => {
  const args = {};
  form.fields.forEach((field, i) => {
    const el = $(`[data-x-field="${i}"]`, box), text = el.value.trim();
    if (!text) return;
    const wrong = said => { el.focus(); throw new Error(`${field.flag} ${said}`); };
    if (el.tagName === 'SELECT') args[field.name] = (field.kind === 'yes-no' ? [true, false] : field.choices)[+text];
    else if (field.kind === 'json') {
      try { args[field.name] = JSON.parse(text); } catch (error) { wrong(`takes JSON: ${error.message}`); }
    } else if (field.kind === 'integer') args[field.name] = /^-?\d+$/.test(text) ? +text : wrong('is a whole number');
    else if (field.kind === 'number') args[field.name] = isFinite(+text) ? +text : wrong('is a number');
    else if (field.kind === 'list') args[field.name] = text.split(',').map(part => part.trim()).filter(Boolean);
    else args[field.name] = text;
  });
  return args;
};

// Run a form's op: the args its fields make, one question first for an op the terminal asks about, then the act, kept
// until it is answered, whose body's text web stores for the op to cite, and what came of it said under Run: done, with
// what the op answered as text, or its refusal.
X.run = async box => {
  const pane = S.pane, form = pane && pane.form, said = $('.x-said', box), run = $('[data-x-run]', box);
  if (!(pane instanceof X.Form) || pane.box !== box || pane.sending || X.cannot(form.op)) return;
  let args;
  try { args = X.args(form, box); } catch (error) { said.textContent = error.message; return; }
  const asked = [form.title, ...Object.values(args).map(X.shown)].join(' ');
  if (X.caps.confirmed.includes(form.op) && !await X.ask(run, `${asked}? It cannot be taken back.`, 'Run')) return;
  pane.sending = true;
  pane.paint();
  said.textContent = X.WAITING;
  try {
    const r = await X.act(form.op, args);
    said.textContent = !r ? X.UNANSWERED : r.refusal ? `${form.title}: ${X.refused(r.refusal)}`
      : `${form.title}: done.${r.result == null ? '' : ` ${JSON.stringify(r.result)}`}`;
  } catch (error) {
    said.textContent = `Not sent: ${error.message}.`;
  }
  pane.sending = false;
  pane.paint();
};

document.addEventListener('submit', e => {
  const box = e.target.closest('.x-form');
  if (!box) return;
  e.preventDefault();
  X.run(box);
});

// ---------------------------------------------------------------------- what changed

// Review changes, in the pane the address names, `review=`: `changes`, what changed, in the words the terminal's
// /review says, read through x_read's changes pane, each commit with Patch and Test and each workspace with Uncommitted
// diff; or a commit's SHA or a workspace, its diff, asked for with repo.diff each time it opens, read through x_read's
// diff pane and drawn a page at a time, its lines chosen by their numbers, and a comment on them sent below as a
// message to the change's maker. What changed is read as it opens and again when Read again is pressed.
X.Review = class {
  constructor(name) {
    this.name = name;
    const changes = name === 'changes';
    const title = changes ? 'What changed' : /^[0-9a-f]+$/.test(name) ? `Patch of ${name.slice(0, 12)}`
      : `${name === 'shared' ? 'Your checkout' : name}, uncommitted`;
    const back = changes ? html`<button class="btn" data-x-again>Read again</button>`
      : html`<button class="btn" data-x-review="changes">What changed</button>`;
    $('#pane').innerHTML = html`<div class="phead"><h2>${title}</h2>${back}<button class="close" data-close-pane title="Close">×</button></div><div class="scroll"><div class="x-review"><div class="loading">Loading</div></div><p class="x-said" aria-live="polite"></p></div>`.s;
    this.box = $('#pane .x-review');
    this.said = $('#pane .x-review + .x-said');
    if (changes) this.list(); else this.open();
  }
  async list() {
    let r;
    try { r = await api('x_read', {pane: 'changes'}); } catch (e) { return this.note(e.message); }
    if (this.dead) return;
    this.lines = r.lines;
    if (r.repo == null) return this.note('Nothing is observed: the session\'s cwd is in no git repository.');
    this.box.innerHTML = html`${r.lines.map(X.change)}`.s;
    this.paint();
  }
  async open() {
    const why = X.cannot('repo.diff');
    if (why) return this.note(why);
    this.box.innerHTML = html`<div class="loading">Asking for the diff of ${this.name}</div>`.s;
    const r = await X.act('repo.diff', {of: this.name});
    if (this.dead) return;
    if (!r || r.refusal) return this.note(r ? X.refused(r.refusal) : X.UNANSWERED);
    let got;
    try {
      do { got = await api('x_read', {pane: 'diff', effect: r.result.effect}); } while (got.reading && !this.dead);
    } catch (e) { return this.note(e.message); }
    if (this.dead) return;
    const d = this.diff = got.diff;
    this.page = got.page;
    this.shown = Math.min(this.page, (d.lines || []).length);
    this.chosen = null;
    this.box.innerHTML = html`<p class="x-about"><b>${d.above[0]}</b>${d.above.slice(1).map(line => html`<br>${line}`)}</p><div class="x-patch">${X.patchLines((d.lines || []).slice(0, this.shown))}</div><div class="x-end"></div><form class="x-comment"><p class="x-about"></p><textarea rows="3" aria-label="Comment" spellcheck="false"></textarea><div class="x-acts"><button class="btn primary" data-x-comment>Comment</button></div><p class="x-said" aria-live="polite"></p></form>`.s;
    this.end();
    this.paint();
  }
  note(said) {
    if (!this.dead) this.box.innerHTML = html`<div class="note">${said}</div>`.s;
  }
  // What follows the lines drawn so far: Read on while the patch has more, and at its end the words below it.
  end() {
    const lines = this.diff.lines || [], below = this.diff.below;
    $('.x-end', this.box).innerHTML = (this.shown < lines.length
      ? html`<button class="btn" data-x-more>${num(lines.length - this.shown)} more lines: read on</button>`
      : below ? html`<p class="x-below">${below}</p>` : html``).s;
  }
  // Draw the patch's next page, and focus its first line.
  more() {
    const lines = this.diff.lines || [], after = this.shown;
    this.shown = Math.min(after + this.page, lines.length);
    $('.x-patch', this.box).insertAdjacentHTML('beforeend', X.patchLines(lines.slice(after, this.shown)).s);
    this.end();
    this.mark();
    const next = $(`.x-pl[data-n="${lines[after].number}"] [data-x-line]`, this.box);
    if (next) next.focus();
  }
  // Choose line `n`, or with `extend` every line from the one chosen first to it. The one line chosen alone, chosen
  // again, chooses none.
  choose(n, extend) {
    const [first, last] = this.chosen || [];
    if (extend && this.chosen) this.chosen = [Math.min(this.anchor, n), Math.max(this.anchor, n)];
    else if (first === n && last === n) this.chosen = null;
    else { this.chosen = [n, n]; this.anchor = n; }
    this.mark();
  }
  mark() {
    const [first, last] = this.chosen || [0, -1];
    for (const el of $$('.x-pl', this.box)) {
      const on = +el.dataset.n >= first && +el.dataset.n <= last;
      el.classList.toggle('x-chosen', on);
      $('[data-x-line]', el).setAttribute('aria-pressed', String(on));
    }
    this.paint();
  }
  // Every control disabled where the page may not take its act now, saying why, and whom a comment goes to and what
  // it is on, as the terminal says it.
  paint() {
    for (const el of $$('[data-x-diff]', this.box)) X.disable(el, X.cannot('repo.diff'));
    for (const el of $$('[data-x-test]', this.box)) {
      const action = this.lines[+el.dataset.xTest].actions[0];
      X.disable(el, action.disabled || X.cannot(action.op) || (this.testing ? X.WAITING : null));
    }
    const form = $('.x-comment', this.box), d = this.diff;
    if (!form) return;
    const [first, last] = this.chosen || [];
    const on = !this.chosen ? d.about : first === last ? `line ${first} of ${d.of}` : `lines ${first} to ${last} of ${d.of}`;
    $('.x-about', form).innerHTML = (d.to ? html`Comment to <b>${d.to}</b> on ${on}` : html`${d.unsendable}`).s;
    const why = d.unsendable || X.cannot('message.send') || (this.sending ? X.WAITING : null), t = $('textarea', form);
    t.readOnly = !!why;
    X.disable(t, why);
    X.disable($('[data-x-comment]', form), why);
  }
  destroy() { this.dead = true; }
};

// One line of what changed: its words, each part drawn by its tone, and its acts.
X.change = (c, i) => {
  const acts = [];
  if (c.of && c.kind === 'commit') acts.push(html`<button class="btn" data-x-diff="${c.of}">Patch</button>`);
  if (c.of && c.kind === 'heading') acts.push(html`<button class="btn" data-x-diff="${c.of}">Uncommitted diff</button>`);
  if (c.actions.length) acts.push(html`<button class="btn" data-x-test="${i}">Test</button>`);
  return html`<div class="x-change x-${c.kind}"><span>${c.parts.map(([text, tone]) => html`<span class="x-tone-${tone || 'plain'}">${text}</span>`)}</span>${acts.length ? html`<span class="x-acts">${acts}</span>` : ''}</div>`;
};

// Lines of a patch: each its number, a button that chooses it, and its words, drawn by its tone, and led by an arrow
// where it goes on git's line before it.
X.patchLines = lines => html`${lines.map(l => html`<div class="x-pl x-tone-${l.tone || 'plain'}${l.continues ? ' x-goes-on' : ''}" data-n="${l.number}"><button type="button" class="x-n" data-x-line="${l.number}" aria-pressed="false" title="Choose line ${l.number}, or with Shift every line from the one chosen first">${l.number}</button><span>${l.text}</span></div>`)}`;

// Test a commit, after one question, as its act's label says whose code it runs as you, and say what came of it.
X.test = async el => {
  const pane = S.pane, action = pane.lines[+el.dataset.xTest].actions[0];
  if (!await X.ask(el, `${action.label}. Run it?`, 'Test')) return;
  pane.testing = true;
  pane.paint();
  pane.said.textContent = X.WAITING;
  const r = await X.act(action.op, action.args);
  pane.testing = false;
  pane.paint();
  pane.said.textContent = !r ? X.UNANSWERED : r.refusal ? `Test: ${X.refused(r.refusal)}`
    : `Testing ${action.args.commit.slice(0, 12)}: Read again to see what it comes to.`;
};

// Send a comment: a message to the change's maker, its text made its gist as the composer's is, citing the lines
// chosen of the diff, or with none chosen the commit, or an uncommitted diff whole.
X.comment = async form => {
  const pane = S.pane, d = pane && pane.diff, t = $('textarea', form), said = $('.x-said', form);
  if (!(pane instanceof X.Review) || !d || pane.sending || d.unsendable || X.cannot('message.send')) return;
  const text = t.value.trim();
  if (!text) return;
  const cites = pane.chosen ? `${d.ref}#L${pane.chosen[0]}-${pane.chosen[1]}` : d.whole;
  pane.sending = true;
  pane.paint();
  said.textContent = X.WAITING;
  const r = await X.act('message.send', {to: d.to, based_on: [cites]}, {text});
  pane.sending = false;
  said.textContent = !r ? X.UNANSWERED : r.refusal ? `Comment: ${X.refused(r.refusal)}` : `Sent to ${d.to}, citing ${cites}.`;
  if (r && !r.refusal) t.value = '';
  pane.paint();
};

document.addEventListener('submit', e => {
  const form = e.target.closest('.x-comment');
  if (!form) return;
  e.preventDefault();
  X.comment(form);
});

// Shift and Enter on a line's number chooses every line from the one chosen first, as Shift and a click does, and in a
// comment Enter sends, as in the composer.
document.addEventListener('keydown', e => {
  const t = e.target;
  if (e.key !== 'Enter' || e.isComposing || !t.matches) return;
  if (e.shiftKey && t.matches('[data-x-line]') && S.pane instanceof X.Review) {
    e.preventDefault();
    S.pane.choose(+t.dataset.xLine, true);
  } else if (!e.shiftKey && t.matches('.x-comment textarea')) {
    e.preventDefault();
    t.form.requestSubmit();
  }
});

// ---------------------------------------------------------------------- what the page draws

// Agents and people apart: in the count, in rows, and in each picture.
renderTop = function () {
  const r = S.route;
  for (const b of $$('#layouts button')) b.classList.toggle('on', b.dataset.layout === r.layout);
  const all = [...S.users.values()];
  const agents = all.filter(u => (u.fields || {}).kind === 'agent').length;
  const people = all.filter(u => (u.fields || {}).kind === 'human').length;
  const now = Date.now();
  S.rate = S.rate.filter(t => now - t < 10000);
  const rate = S.rate.length / Math.max(1, Math.min(10, (now - S.since) / 1000));
  $('#stats').innerHTML = html`<b>${num(agents)}</b> ${agents === 1 ? 'agent' : 'agents'} · <b>${num(people)}</b> ${people === 1 ? 'person' : 'people'} · <b>${num(S.chats.size)}</b> chats · <b>${num(S.total)}</b> messages${rate ? html` · <b>${rate < 10 ? rate.toFixed(1) : Math.round(rate)}</b>/s` : ''}`;
  const as = $('#as');
  as.classList.toggle('on', !!r.as);
  as.innerHTML = r.as ? html`${avatar(r.as, 'sm')}<span>As <b>${name(r.as)}</b></span><span class="x" data-clear-as title="See everything again">×</span>`
    : html`<span>As everyone</span><span>▾</span>`;
};

const baseAvatar = avatar;
avatar = (id, size = '') => {
  const kind = X.kind(id) || 'unknown';
  return new Safe(baseAvatar(id, size).s.replace('<span class="av ', () => html`<span data-kind="${kind}" class="av x-${kind} `.s));
};

// The people, with each agent's status where SwarmChat draws someone's first field: who is working, and who is held up,
// is what the list is read for, and the picture already says an agent.
const basePeopleRows = peopleRows;
peopleRows = () => {
  const users = S.users;
  S.users = new Map([...users].map(([id, u]) =>
    [id, X.kind(id) === 'agent' && u.status ? {...u, fields: {status: u.status, ...u.fields}} : u]));
  try { return basePeopleRows(); } finally { S.users = users; }
};

// Seeing as someone, offered for everyone, each a button the keyboard reaches, and taken only for an agent.
const baseOpenAsPicker = openAsPicker;
openAsPicker = anchor => {
  baseOpenAsPicker(anchor);
  const box = $('#overlay .pop');
  const off = () => {
    for (const it of $$('[data-as]', box)) {
      it.setAttribute('role', 'button');
      it.tabIndex = 0;
      if (!it.dataset.as || X.kind(it.dataset.as) === 'agent') continue;
      it.removeAttribute('data-as');
      X.disable(it, X.AS_AGENT);
    }
  };
  off();
  $('input', box).addEventListener('input', off);
};

// Delivered, where SwarmChat says read: what a handover landed or a tool's result showed, which is evidence, and never
// that it was understood. A person's reading leaves none. A reply cites the message's entry in the journal, which
// its Reply button carries.
const baseMessageHtml = messageHtml;
messageHtml = (m, prev, o = {}) => {
  const drawn = baseMessageHtml(m, prev, o);
  if (m.kind !== 'message') return drawn;
  const u = user(m.from);
  const knew = html`<button data-knew="${m.id}" title="How far ${u.name} had marked messages read in each chat when sending this">What had ${first(m.from)} read?</button>`.s;
  const reached = X.kind(m.from) === 'agent'
    ? html`<button data-knew="${m.id}" title="How much of each chat had been delivered to ${u.name} when it sent this">What had reached ${first(m.from)}?</button>`
    : html`<button${X.disabled('A person\'s reading leaves no evidence, so nothing says what had reached them')}>What had reached ${first(m.from)}?</button>`;
  const why = X.cannot('message.send', S.chats.get(m.chat)) || (m.x_ref ? null : m.x_approval
    ? 'An approval is answered with Allow or Deny, not a reply.'
    : `What ${first(m.from)} said in its turn is no message a reply can cite: write to ${first(m.from)} in the chat.`);
  const reply = html`<button data-x-reply="${m.id}" data-x-ref="${m.x_ref || ''}"${X.disabled(why)}>Reply</button>`;
  const provenance = html`<button data-x-provenance="${m.x_shows}" title="What ${m.x_shows} rests on, what came of it and whose work it reaches">Provenance</button>`;
  return new Safe(drawn.s
    .replace(knew, () => reached.s)
    .replace(html`<button data-receipts="${m.id}">Read by</button>`.s, () => html`<button data-receipts="${m.id}">Delivered to</button>`.s)
    .replace('\n</div><div class="actions">', () => `${X.card(m).s}\n</div><div class="actions">${reply.s}${provenance.s}`));
};

// An approval left for the person, as a card in the agent's chat with them.
X.card = m => {
  const a = m.x_approval;
  if (!a) return html``;
  if (a.state === 'resolved') {
    return html`<div class="x-card x-done" data-x-card="${a.id}" tabindex="-1">${a.verdict === 'allow' ? 'Allowed' : 'Denied'} by ${name(a.by)}${a.via ? html` via ${a.via}` : ''}</div>`;
  }
  if (a.state === 'moot') return html`<div class="x-card x-done" data-x-card="${a.id}" tabindex="-1">Moot: the turn that asked for it has ended</div>`;
  const why = X.cannot('approval.resolve');
  const button = (verdict, label) => html`<button class="btn" data-x-decide="${verdict}" data-x-approval="${a.id}" data-x-version="${a.version}"${X.disabled(why)}>${label}</button>`;
  return html`<div class="x-card" data-x-card="${a.id}"><span>${first(m.from)} asks you to approve this</span>${button('allow', 'Allow')}${button('deny', 'Deny')}</div>`;
};

// An agent's end, as the terminal says it: its report when it finished with one, and otherwise how it ended and why.
const baseSystemHtml = systemHtml;
systemHtml = e => e.kind !== 'ended' ? baseSystemHtml(e)
  : html`<div class="sys" data-seq="${e.seq}"><span>${['failed', 'lost'].includes(e.x_end.status) ? '✗' : '✓'} ${e.x_end.gist}</span><span class="stamp" title="${full(e.at)}">${clock(e.at)}</span></div>`;

openReceipts = async function (anchor, id) {
  const box = document.createElement('div');
  box.className = 'pop';
  box.innerHTML = '<div class="ph">Delivered to</div><div class="loading">Loading</div>';
  overlay.open(box, anchor);
  let r;
  try { r = await api('view_receipts', {id}); } catch (e) { box.innerHTML = html`<div class="note">${e.message}</div>`.s; return; }
  box.innerHTML = html`<div class="ph">Delivered to ${r.read.length} of ${plural(r.read.length + r.unread.length, 'agent')} it was for</div>
${r.read.map(x => html`<div class="it" data-person="${x.id}">${avatar(x.id, 'sm')} ${name(x.id)}<span class="s">${clockS(x.at)}</span></div>`)}
${r.unread.length ? html`<div class="ph">Not delivered yet</div>${r.unread.map(u => html`<div class="it" data-person="${u}">${avatar(u, 'sm')} ${name(u)}</div>`)}` : ''}
<div class="note">Delivered means a handover landed it or a tool's result showed it, never that it was understood. A person's reading is not recorded.</div>`.s;
  box.addEventListener('click', e => { const it = e.target.closest('[data-person]'); if (it) { overlay.close(); go({person: it.dataset.person}); } });
};

openMembers = function (anchor, chatId) {
  const c = S.chats.get(chatId);
  if (!c) return;
  const pos = S.view && S.view.positions ? S.view.positions : {};
  const last = c.last ? c.last.seq : 0;
  const box = document.createElement('div');
  box.className = 'pop';
  box.innerHTML = html`<div class="ph">${plural(c.members.length, 'member')}</div>${c.members.map(u => {
    const p = pos[u];
    const state = X.kind(u) !== 'agent' ? '' : p == null ? '' : p >= last ? 'everything delivered' : p ? `delivered up to ${chatId}:${p}` : 'nothing delivered';
    return html`<div class="it" data-person="${u}">${avatar(u, 'sm')} ${name(u)}<span class="s">${state}</span></div>`;
  })}`.s;
  overlay.open(box, anchor);
  box.addEventListener('click', e => { const it = e.target.closest('[data-person]'); if (it) { overlay.close(); go({person: it.dataset.person}); } });
};

KnewPane = class extends KnewPane {
  async load() {
    try {
      const r = await api('view_knew', {id: this.id});
      if (this.dead) return;
      S.knew = {id: this.id, user: r.user, at: r.at, chats: r.chats};
      $('#pane h2').textContent = `What had reached ${name(r.user)}`;
      const rows = r.chats.map(k => {
        const c = S.chats.get(k.chat);
        return html`<div class="k" data-had="${k.chat}" data-upto="${k.upto}"><span class="t"><span class="ico ${c ? c.kind : ''}">${c ? KIND[c.kind] : ''}</span> ${title(c, r.user)}${k.chat === r.message.chat ? ' · here' : ''}</span>
<span class="u ${k.unseen ? 'some' : 'zero'}">${k.unseen ? `${num(k.unseen)} not delivered` : 'all delivered'}</span>
<span class="s">${num(k.read)} delivered of ${plural(k.messages, 'message')}${k.read_at ? ` · the last at ${clockS(k.read_at)}` : ' · none yet'}</span></div>`;
      });
      this.box.innerHTML = html`<div class="note">When ${name(r.user)} sent this at <b>${clockS(r.at)}</b>, this is how much of each chat had been delivered to ${first(r.user)}: what a handover landed or a tool's result showed. It is not what ${first(r.user)} understood, and what reached it another way, through a file or a shell, leaves nothing here.</div>
<div class="msgs">${messageHtml(r.message, null, {tree: true})}</div>${rows}`.s;
      if (S.view instanceof ChatView && S.view.o.knew === this.id) S.view.draw();
    } catch (e) { this.box.innerHTML = html`<div class="note">${e.message}</div>`.s; }
  }
};

UnreadView = class extends UnreadView {
  constructor(main) {
    super(main);
    const as = S.route.as;
    $('.mhead', main).innerHTML = html`<span class="ico">✉</span><h1>What waits for ${name(as)}</h1><span class="sub">what was for ${first(as)} and has not been delivered yet, oldest first. Nothing is marked.</span>`.s;
    this.none = `Nothing waits: everything for ${first(as)} has been delivered.`;
    this.draw2();
  }
};

const baseChatRow = chatRow;
chatRow = c => {
  const row = baseChatRow(c);
  return {...row, html: i => row.html(i).replace('title="Unread for ', 'title="Not delivered yet to ')};
};

// The chats, and first where the person must act, with how many places that is.
const baseChatRows = chatRows;
chatRows = () => {
  const as = S.route.as;
  const rows = baseChatRows().map(row => ({...row, html: i => {
    const drawn = row.html(i);
    return as ? drawn.replace(html`<span class="t">${`${first(as)}'s unread`}</span>`.s, () => html`<span class="t">What waits for ${first(as)}</span>`.s) : drawn;
  }}));
  if (S.filter) return rows;
  const why = X.needs ? null : X.needsWhy, n = X.needs ? X.needs.length : 0;
  rows.splice(1, 0, {open: X.openNeeds, html: i => html`<div class="row special" data-i="${i}" data-x-needs role="button" tabindex="0"${why ? X.disabled(why) : html` title="Where you must act"`}><span class="ico">⚠</span><span class="t">Needs you</span>${n ? html`<span class="badge">${num(n)}</span>` : ''}</div>`.s});
  return rows;
};

ChatView = class extends ChatView {
  constructor(main, chatId, o) {
    super(main, chatId, o);
    const c = S.chats.get(chatId);
    if (!c) return;
    main.insertAdjacentHTML('beforeend', X.composer(`chat:${chatId}`, chatId,
      c.x_to ? html`To <b>${c.x_to}</b>` : 'No message goes from you to this chat').s);
    X.paint(`chat:${chatId}`);
  }
  renderHead() {
    super.renderHead();
    const board = $('[data-goto="board"]', this.head);
    if (board) board.insertAdjacentHTML('beforebegin', X.tasksView(S.chats.get(this.id)).s);
  }
  divider() {
    const d = super.divider();
    return d && {...d, label: d.label.replace(' has read up to here', ' has been delivered up to here')
      .replace('had read up to here', 'had been delivered up to here').replace('had read nothing here', 'had been delivered nothing here')};
  }
};

// A thread, with a composer at its foot that replies to the message it was opened on.
ThreadPane = class extends ThreadPane {
  constructor(id) {
    super(id);
    this.draft = `reply:${id}`;
    $('#pane').insertAdjacentHTML('beforeend', X.composer(this.draft, id.split(':')[0], 'Reply').s);
    this.form = $('#pane .x-composer');
    this.form.dataset.xWhy = 'Loading the thread.';
    X.paint(this.draft);
  }
  async load() {
    await super.load();
    const f = this.form, m = $(`.msg[data-id="${CSS.escape(this.id)}"]`, this.box);
    if (this.dead || !f) return;
    const reply = m && $('[data-x-reply]', m);
    delete f.dataset.xWhy;
    if (reply && reply.dataset.xRef) f.dataset.xReplyTo = reply.dataset.xRef;
    else f.dataset.xWhy = reply ? reply.title : 'The thread could not be read.';
    const to = (S.chats.get(f.dataset.xChat) || {}).x_to;
    if (m) $('.x-to', f).innerHTML = html`Reply to <b>${name($('.name', m).dataset.person)}</b>${to ? html`, to <b>${to}</b>` : ''}`.s;
    X.paint(this.draft);
  }
};

// The provenance of one event, in the lines the terminal draws, read when it opens and when its event is asked again:
// what it rests on, what came of it and whose work it reaches, each link by how it is known. Following a link shows that
// event's, and one a chat shows opens there too.
X.Provenance = class {
  constructor(ref) {
    this.ref = this.name = ref;
    const pane = $('#pane');
    pane.innerHTML = html`<div class="phead"><h2>Provenance of ${ref}</h2><button class="close" data-close-pane title="Close">×</button></div><div class="scroll"><div class="x-provenance"><div class="loading">Loading</div></div></div>`.s;
    this.box = $('.x-provenance', pane);
    this.load();
  }
  async load() {
    let r;
    try { r = await api('x_read', {pane: 'provenance', ref: this.ref}); } catch (e) {
      if (!this.dead) this.box.innerHTML = html`<div class="note">${e.message}</div>`.s;
      return;
    }
    if (this.dead) return;
    this.box.innerHTML = html`<div class="note">${X.RECORD}</div>${r.lines.map(X.line)}`.s;
    if (r.at && X.followed === this.ref) X.reveal(r.at, this.ref);
    X.followed = null;
  }
  destroy() { this.dead = true; }
};

// One line of the pane: a part's heading, or the kind a link is known by beside its words. A line that opens an event
// is a button, which the keyboard reaches and follows, and one that opens nothing says why in its words.
X.line = l => l.kind === 'heading' ? html`<div class="x-part">${l.text}</div>`
  : l.ref ? html`<button type="button" class="x-line${l.warn ? ' x-warn' : ''}" data-x-follow="${l.ref}" title="Follow it into the provenance of ${l.ref}"><span class="x-kind">${l.kind}</span><span>${l.text}</span></button>`
  : html`<div class="x-line${l.warn ? ' x-warn' : ''}"><span class="x-kind">${l.kind}</span><span>${l.text}</span></div>`;

// Show an event's provenance in the pane, read again when it is the one shown. One followed there that a chat shows opens
// in that chat too.
X.followed = null;
X.provenance = (ref, followed) => {
  X.followed = followed ? ref : null;
  if (S.pane instanceof X.Provenance && S.pane.ref === ref) return S.pane.load();
  go({provenance: ref, thread: null, knew: null, act: null, args: null, review: null}, true);
};
X.reveal = (at, ref) => {
  const [chat, seq] = at.split(':');
  if (S.view instanceof ChatView && S.view.id === chat) return S.view.jump(+seq);
  go({layout: 'chat', chat, m: seq, provenance: ref});
};

// A queue's or a board's own view, of its tasks or its entries, drawn disabled in its chat, saying why.
X.tasksView = c => c && c.kind === 'channel' && ['queue', 'board'].includes(c.description)
  ? html`<button class="btn"${X.disabled(X.unbuilt.tasks)}>${c.description === 'queue' ? 'Tasks' : 'Entries'}</button>`
  : html``;

// Posts, with the sorts that rank by votes disabled, saying why, and a queue's or a board's own view beside them.
BoardView = class extends BoardView {
  constructor(main, chatId, sort) {
    super(main, chatId, sort);
    for (const b of $$('[data-sort="hot"], [data-sort="top"]', main)) X.disable(b, X.UNVOTED);
    $('.sorts', main).insertAdjacentHTML('afterend', X.tasksView(S.chats.get(chatId)).s);
  }
};

// A post's votes are unknown, so its vote control is drawn disabled, saying why, with no count.
const basePostHtml = postHtml;
postHtml = (p, o) => new Safe(basePostHtml({...p, votes: 0}, o).s.replace(
  html`<div class="votes" title="No reactions">${new Safe(ARROW)}<span>0</span></div>`.s,
  () => html`<div class="votes" role="button" tabindex="0" aria-label="Vote"${X.disabled(X.UNVOTED)}>${new Safe(ARROW)}</div>`.s));

// The map's pane offers to see as whoever is under the mouse, and only an agent can be seen as. Its busiest list holds
// everyone who writes, people and the runtime too. Its timeline and window count the chats of whoever it sees as, so
// they are asked for again when that changes.
MapView = class extends MapView {
  showPane() {
    super.showPane();
    const see = $('#pane [data-see-as]');
    if (see && X.kind(see.dataset.seeAs) !== 'agent') X.disable(see, X.AS_AGENT);
    const busiest = $('#pane .ph3');
    if (busiest && busiest.textContent === 'Agents') busiest.textContent = 'Who writes';
  }
  onAs() {
    super.onAs();
    this.loadActivity();
    if (this.win) this.fetchWindow();
  }
};

// A person's page: an agent's acts, what changed, and what of it is not built yet, or on the person's own, the session's
// acts and new links, which a view link cannot make.
PersonView = class extends PersonView {
  constructor(main, id) {
    super(main, id);
    const card = $('.card', main), agent = X.kind(id) === 'agent', mine = id === X.caps.person;
    if (!agent) {
      const see = $('[data-see-as]', card);
      if (see) X.disable(see, X.AS_AGENT);
    }
    if (!agent && !mine) return;
    const acts = (agent ? ['interrupt', 'stop-below', 'retire', 'cancel'] : ['close', 'cancel-session']).map(act => {
      const why = X.cannot(X.acts[act][1]);
      return html`<button class="btn" data-x-act="${act}" data-x-agent="${id}"${X.disabled(why)}>${X.acts[act][0]}</button>`;
    });
    const why = X.caps.credential === 'view' ? X.caps.cannot : null;
    const more = agent
      ? [html`<button class="btn"${X.disabled(X.unbuilt.activity)}>Tool activity</button>`, html`<button class="btn" data-x-review="changes">Review changes</button>`]
      : ['view', 'control'].map(kind => html`<button class="btn" data-x-link="${kind}"${X.disabled(why)}>New ${kind} link</button>`);
    card.insertAdjacentHTML('afterend', html`<div class="x-acts">${acts}</div><div class="x-acts">${more}</div><p class="x-said" aria-live="polite"></p>`.s);
  }
};

// Make a link of either kind, which opens once, within ten minutes, and say it.
X.mint = async el => {
  const said = $('.x-said', el.closest('.person')), kind = el.dataset.xLink;
  X.disable(el, X.WAITING);
  try {
    const r = await fetch('/x/link', {method: 'POST', body: JSON.stringify({class: kind}),
      headers: {'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'}});
    const p = await r.json().catch(() => ({error: `web answered ${r.status}`}));
    if (r.status === 401) login(p.error);
    said.textContent = r.ok ? `A ${kind} link, which opens once, within ten minutes: ${p.link}` : p.error;
  } catch (_) {
    said.textContent = 'web could not be reached, so no link was made.';
  }
  X.disable(el, null);
};

// Take an act of a person's page, asking first where its op is one that nothing takes back, and say what came of it.
X.lifecycle = async el => {
  const [label, op, more] = X.acts[el.dataset.xAct], agent = X.kind(el.dataset.xAgent) === 'agent' ? `@${el.dataset.xAgent}` : '';
  const said = $('.x-said', el.closest('.person'));
  const what = agent ? `${label} ${agent}` : label;
  if (X.caps.confirmed.includes(op) && !await X.ask(el, `${what}? It cannot be taken back.`, label)) return;
  X.disable(el, X.WAITING);
  const r = await X.act(op, agent ? {agent, ...more} : {});
  X.disable(el, null);
  said.textContent = !r ? X.UNANSWERED : r.refusal ? `${what}: ${X.refused(r.refusal)}`
    : op === 'agent.interrupt' ? `Stopped the turns of ${r.result.stopped.join(', ')}. It stops turns, not waits: one parked on a wait is left to it.`
      : `${what}: done.`;
};

X.decide = async el => {
  const buttons = $$('button', el.closest('[data-x-card]'));
  for (const b of buttons) X.disable(b, X.WAITING);
  const r = await X.act('approval.resolve', {id: el.dataset.xApproval, verdict: el.dataset.xDecide, expected_version: +el.dataset.xVersion});
  if (!r) return toast(X.UNANSWERED);
  if (!r.refusal) return;
  toast(X.refused(r.refusal));
  for (const b of buttons) X.disable(b, X.cannot('approval.resolve'));
};

// An action of a place in Needs you: its op, at once, or where it leaves the rest to its op's form, that form in the
// pane, filled in with what it fixes.
X.action = async el => {
  const row = (X.needs || []).find(found => found.id === el.dataset.xPlace);
  if (!row) return;
  const action = row.actions[+el.dataset.xAction];
  if (action.form) {
    overlay.close();
    return go({act: action.op, args: JSON.stringify(action.args), provenance: null, review: null, thread: null, knew: null}, true);
  }
  X.disable(el, X.WAITING);
  const r = await X.act(action.op, action.args);
  toast(!r ? X.UNANSWERED : r.refusal ? X.refused(r.refusal) : `${action.label}: ${row.gist}`);
  X.needed();
};

const baseClick = onClick;
onClick = e => {
  const el = e.target.closest('[data-x-reply], [data-x-decide], [data-x-act], [data-x-action], [data-x-goto], [data-x-link], [data-x-attach], [data-x-provenance], [data-x-follow], [data-x-commands], [data-x-review], [data-x-diff], [data-x-test], [data-x-more], [data-x-line], [data-x-again]');
  if (!el && (S.route.provenance || S.route.act || S.route.review) && e.target.closest('[data-close-pane]')) {
    return go({provenance: null, act: null, args: null, review: null}, true);
  }
  if (!el) return baseClick(e);
  const d = el.dataset;
  if ('xCommands' in d) return X.openCommands();
  if (d.xReview || d.xDiff) {
    return go({review: d.xReview || d.xDiff, provenance: null, act: null, args: null, thread: null, knew: null}, true);
  }
  if (d.xTest) return X.test(el);
  if ('xMore' in d) return S.pane.more();
  if (d.xLine) return S.pane.choose(+d.xLine, e.shiftKey);
  if ('xAgain' in d) return S.pane.list();
  if (d.xProvenance) return X.provenance(d.xProvenance, false);
  if (d.xFollow) return X.provenance(d.xFollow, true);
  if (d.xReply) return go({thread: d.xReply, knew: null}, true);
  if (d.xDecide) return X.decide(el);
  if (d.xAct) return X.lifecycle(el);
  if (d.xAction) return X.action(el);
  if (d.xLink) return X.mint(el);
  if (d.xGoto) {
    overlay.close();
    const c = [...S.chats.values()].find(c => c.kind === 'direct' && c.members.includes(d.xGoto) && c.members.includes(X.caps.person));
    return c && go({chat: c.id});
  }
  $('[data-x-file]', el.closest('form')).click();
};
