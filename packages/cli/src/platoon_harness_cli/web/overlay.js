// ---------------------------------------------------------------------- platoon-harness

// platoon-harness's overlay, which follows SwarmChat's script in this one script. It uses only the names that script
// declares at its top level, and puts new markup only through its html template, which escapes all it is given. What
// it changes says what is so: delivered where SwarmChat says read, agents and people told apart, and every act this
// page cannot take shown, disabled, with the reason.

// What this page may do, read from view_info before the page starts: `credential`, view or control, `live`, whether a
// runtime holds the session, `person`, who acts here, `may`, the ops their grants hold, `confirmed`, the ops asked
// about before they run, and `cannot`, why this page may do nothing, when it may not. The feed keeps `live` current.
const X = {caps: null};

// An act of the page, by the op it runs.
X.ops = {send: 'message.send', reply: 'message.send', file: 'message.send', decide: 'approval.resolve',
  interrupt: 'agent.interrupt', 'stop-below': 'agent.interrupt', retire: 'agent.retire', cancel: 'agent.cancel'};

// The acts this stage of the page has not built, and why.
X.unbuilt = Object.fromEntries(Object.keys(X.ops).map(act =>
  [act, 'Not built yet: acting from the page is the next stage. The terminal and the command line act now.']));

// The parts of SwarmChat's page not built over a session yet, and why.
X.layouts = {board: 'Not built yet: the board layout, and the tasks and board views, are planned.',
  map: 'Not built yet: the map is planned.'};

// Why an act cannot be taken now, in `chat` if it is about one, or null when it can.
X.cannot = (act, chat) => {
  const caps = X.caps;
  if (!caps) return 'Loading what this page may do.';
  if (caps.cannot) return caps.cannot;
  if (S.route.as) return `You see the session as ${name(S.route.as)}, and an act is yours: see it as everyone to act.`;
  if (chat && ['send', 'reply', 'file'].includes(act) && !chat.x_to) {
    return chat.kind === 'channel' ? 'A queue or a board takes its work by its own commands, not by a message.'
      : 'This chat is between others, and you are not in it, so it takes no message from you.';
  }
  if (!caps.may.includes(X.ops[act])) return `Your grants hold no ${X.ops[act]}.`;
  return X.unbuilt[act] || null;
};

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
};

document.head.insertAdjacentHTML('beforeend', `<style>
.av.x-human { border-radius: 50%; }
.x-composer { display: grid; grid-template-columns: 1fr auto; gap: 6px 8px; padding: 8px 16px 12px; border-top: 1px solid var(--line); }
.x-composer .x-to, .x-composer .x-why { grid-column: 1 / -1; margin: 0; color: var(--faint); font-size: 12px; }
.x-composer textarea { font: inherit; resize: none; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line2); background: var(--panel); color: inherit; }
.x-card { margin: 6px 0; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line2); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.x-card.x-done { color: var(--faint); }
.x-acts { display: flex; gap: 6px; flex-wrap: wrap; }
button[disabled] { opacity: .55; cursor: not-allowed; }
</style>`);

$('#login p').textContent = 'This page opens from a link that platoon-harness web says, or one a page acting for you ' +
  'made. Each link opens once, so ask for a new one.';
$('#login input').placeholder = 'Session token';
for (const b of $$('#layouts button')) {
  if (X.layouts[b.dataset.layout]) { b.disabled = true; b.title = X.layouts[b.dataset.layout]; }
}

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
  return baseStart();
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

const baseReadRoute = readRoute;
readRoute = () => {
  const r = baseReadRoute();
  if (X.layouts[r.layout]) { toast(X.layouts[r.layout]); r.layout = 'chat'; }
  return r;
};

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
  return new Safe(baseAvatar(id, size).s.replace('<span class="av ', html`<span data-kind="${kind}" class="av x-${kind} `.s));
};

// Delivered, where SwarmChat says read: what a handover landed or a tool's result showed, which is evidence, and never
// that it was understood. A person's reading leaves none.
const baseMessageHtml = messageHtml;
messageHtml = (m, prev, o = {}) => {
  const drawn = baseMessageHtml(m, prev, o);
  if (m.kind !== 'message') return drawn;
  const u = user(m.from);
  const knew = html`<button data-knew="${m.id}" title="How far ${u.name} had marked messages read in each chat when sending this">What had ${first(m.from)} read?</button>`.s;
  const reached = X.kind(m.from) === 'agent'
    ? html`<button data-knew="${m.id}" title="How much of each chat had been delivered to ${u.name} when it sent this">What had reached ${first(m.from)}?</button>`
    : html`<button disabled title="A person's reading leaves no evidence, so nothing says what had reached them">What had reached ${first(m.from)}?</button>`;
  const reply = X.cannot('reply', S.chats.get(m.chat));
  const acts = html`<button data-x-reply="${m.id}"${reply ? html` disabled title="${reply}"` : ''}>Reply</button>`;
  return new Safe(drawn.s
    .replace(knew, reached.s)
    .replace(html`<button data-receipts="${m.id}">Read by</button>`.s, html`<button data-receipts="${m.id}">Delivered to</button>`.s)
    .replace('<div class="actions">', X.card(m).s + '<div class="actions">' + acts.s));
};

// An approval left for the person, as a card in the agent's chat with them.
X.card = m => {
  const a = m.x_approval;
  if (!a) return html``;
  if (a.state === 'resolved') {
    return html`<div class="x-card x-done">${a.verdict === 'allow' ? 'Allowed' : 'Denied'} by ${name(a.by)}${a.via ? html` via ${a.via}` : ''}</div>`;
  }
  if (a.state === 'moot') return html`<div class="x-card x-done">Moot: the turn that asked for it has ended</div>`;
  const why = X.cannot('decide');
  const button = (verdict, label) => html`<button class="btn" data-x-decide="${verdict}" data-x-approval="${a.id}" data-x-version="${a.version}"${why ? html` disabled title="${why}"` : ''}>${label}</button>`;
  return html`<div class="x-card" data-x-card="${a.id}"><span>${first(m.from)} asks you to approve this</span>${button('allow', 'Allow')}${button('deny', 'Deny')}</div>`;
};

const baseSystemHtml = systemHtml;
systemHtml = e => e.kind !== 'ended' ? baseSystemHtml(e)
  : html`<div class="sys" data-seq="${e.seq}"><span><b>${name(e.from)}</b> ended, ${e.x_end.status}${e.x_end.reason ? html`: ${e.x_end.reason}` : ''}</span><span class="stamp" title="${full(e.at)}">${clock(e.at)}</span></div>`;

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

const baseChatRows = chatRows;
chatRows = () => baseChatRows().map(row => ({...row, html: i => {
  const as = S.route.as;
  const drawn = row.html(i);
  return as ? drawn.replace(html`<span class="t">${`${first(as)}'s unread`}</span>`.s, html`<span class="t">What waits for ${first(as)}</span>`.s) : drawn;
}}));

ChatView = class extends ChatView {
  constructor(main, chatId, o) {
    super(main, chatId, o);
    const c = S.chats.get(chatId);
    if (!c) return;
    const why = X.cannot('send', c);
    main.insertAdjacentHTML('beforeend', html`<form class="x-composer" data-x-composer="${chatId}"><p class="x-to">${c.x_to ? html`To <b>${c.x_to}</b>` : 'No message goes from you to this chat'}</p><textarea rows="2" aria-label="Message"${why ? html` disabled title="${why}"` : ''}></textarea><button class="btn primary"${why ? html` disabled title="${why}"` : ''}>Send</button>${why ? html`<p class="x-why">${why}</p>` : ''}</form>`.s);
  }
  renderHead() {
    super.renderHead();
    const board = $('[data-goto="board"]', this.head);
    if (board) { board.disabled = true; board.title = X.layouts.board; }
  }
  divider() {
    const d = super.divider();
    return d && {...d, label: d.label.replace(' has read up to here', ' has been delivered up to here')
      .replace('had read up to here', 'had been delivered up to here').replace('had read nothing here', 'had been delivered nothing here')};
  }
};

PersonView = class extends PersonView {
  constructor(main, id) {
    super(main, id);
    const card = $('.card', main);
    if (X.kind(id) !== 'agent') {
      const see = $('[data-see-as]', card);
      if (see) { see.disabled = true; see.title = 'Only an agent leaves evidence of what reached it, so only an agent can be seen as.'; }
      return;
    }
    const acts = [['interrupt', 'Interrupt'], ['stop-below', 'Stop below'], ['retire', 'Retire'], ['cancel', 'Cancel']];
    card.insertAdjacentHTML('beforeend', html`<div class="x-acts">${acts.map(([act, label]) => {
      const why = X.cannot(act);
      return html`<button class="btn" data-x-act="${act}" data-x-agent="${id}"${why ? html` disabled title="${why}"` : ''}>${label}</button>`;
    })}</div>`.s);
  }
};
