# RFC 0074: The browser lists, starts, resumes and stops sessions, on loopback and for you alone

| | |
|---|---|
| Status | Accepted, 2026-11-08 |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`web/__init__.py`](../../packages/cli/src/platoon_harness_cli/web/__init__.py), [`web/server.py`](../../packages/cli/src/platoon_harness_cli/web/server.py), [`web/credentials.py`](../../packages/cli/src/platoon_harness_cli/web/credentials.py), [`tui/sessions.py`](../../packages/cli/src/platoon_harness_cli/tui/sessions.py), [`teams.py`](../../packages/cli/src/platoon_harness_cli/teams.py), [architecture sections 12 and 15](../architecture.md#12-clients), [security.md](../security.md), [RFC 0016](0016-plan-logins-and-credentials.md), [RFC 0027](0027-the-browser-on-our-backend.md) and [RFC 0064](0064-an-act-is-one-form-and-a-read-one-route.md) |
| Discussion | The owner's ruling of 2026-11-08 on milestone 4's plan, which reversed its default for this question and asked for a security design, kept outside this repository |
| Implementation | `feat: List and open your sessions from the browser with web and no session`; `feat: Start, resume and stop a session from the browser's sessions page` |

## Summary

`platoon-harness web` with no session serves a page of your sessions, as `platoon-harness` alone opens the terminal's sessions
screen: every session under the root and how it stands, with the screen's acts, Open, Start, Resume and Stop. It listens on
loopback alone, and says one link, on the terminal that ran it, which opens once for a token that only its own server keeps, so no
link of a session's page opens it, and it makes no link. Open serves the session on a port of its own, in the same process, as
`web SESSION` serves one, and the page goes to a control link of it. Start reads a team file from where `web` runs and says before
the press that its harnesses can spend money. Before anything runs, it asks once for each thing only you can allow: trusting what
the team's files name to run as you, shown as the team holds it, and several agents on one plan login. Resume asks once, saying it
can spend money, and Stop asks once, saying what it does. `web SESSION` stays as [RFC 0027](0027-the-browser-on-our-backend.md)
has it, and starts and resumes nothing.

## Motivation

`web SESSION` starts and resumes nothing ([RFC 0027](0027-the-browser-on-our-backend.md)), so a person who works in a browser
needs a shell to `run`, `serve`, `session resume` or `session stop` a session, then a `web` of its own for each session, as the page
keeps one session per address. The terminal has had a sessions screen since milestone 1
([`tui/sessions.py`](../../packages/cli/src/platoon_harness_cli/tui/sessions.py)): every session and how it stands, and `n` to start
one from the project's team or a team file, trust asked once, a plan login asked about once, `r` to resume, warning it can spend
money, and `s` to stop, with one confirmation. On 2026-11-08 the owner ruled that the browser may do the same, which milestone 4's
plan had left out by default, and asked for a security design first. What the existing pieces do not settle:

- **Who.** A control link of one session acts in that session, as you, and a person may make one and hand it on. A page that
  starts sessions acts on this machine: what a team file names to run runs as you.
- **Where.** A session on a plan login is served on loopback alone, since a control link acts as you on your login
  ([RFC 0016](0016-plan-logins-and-credentials.md), [security.md](../security.md)). A page that starts any team could start one.
- **Trust.** `--trust`, and the terminal's start form's trust field, take what a file names to run before anyone has seen it.
- **Money.** Starting and resuming launch harnesses, which can spend money, and the person must hear that before the act.
- **One session per origin.** SwarmChat's page keeps one session in the browser per address.

## Proposal

### 1. `web` with no session

```text
platoon-harness web [SESSION] [--host HOST] [--port PORT] [--certificate PEM --key PEM]
```

With a session, `web` is as it was. With none, it serves the sessions page, as `platoon-harness` with no command opens the terminal's
sessions screen and `attach SESSION` one session: the same command, and the same argument left out. It says on stderr where it
serves, under which root, and one link:

```text
platoon-harness: web: your sessions under <home>/.local/state/platoon-harness, on 127.0.0.1:43117. Its link opens once, within ten minutes
platoon-harness: web: sessions link, which lists, starts, resumes and stops your sessions, as you: http://127.0.0.1:43117/#link=9f1c…
platoon-harness: web: from another machine, forward this port under the same number, which the page's requests must name: ssh -N -L 43117:127.0.0.1:43117 devbox
```

The page is ours, not SwarmChat's: a list of sessions and a form, served under a policy that names its one script by hash, with
every request bounded and checked as the session's page's are, by the SDK's HTTP: `Host` against the authority served, `Origin` on
every POST, then the bearer, then a body of a stated length. Ctrl+C or `SIGTERM` stops it, and every page it serves with it, and
leaves every session as it was.

```text
GET  /                                          -> the page
POST /x/exchange                                -> {"token", "class": "control", "expires"}
POST /x/sessions {}                             -> {"root", "here", "project", "rows": [{"name", "live", "state"}]}
POST /x/open {"name"}                           -> {"link"} | {"refused"}
POST /x/start {"team", "name", "trust", "plan_login"} -> {"link"} | {"ask": {"question", "yes", "answer"}} | {"refused"}
POST /x/resume {"name"}                         -> {"link"} | {"refused"}
POST /x/stop {"name"}                           -> {"said"} | {"refused"}
```

A refusal is an answer, with its reason in the words the command line says it, never a success; a request the page could not have
made is refused at the HTTP layer, as at a session's page.

### 2. Its link is yours alone

The sessions link is minted by the sessions page's own server, of the control class, and like every link opens once, within ten
minutes, for a session token that lasts twelve hours, of which the server keeps only the hash, in its memory
([RFC 0027](0027-the-browser-on-our-backend.md)). Each server keeps its own credentials, so no view or control link of a session's
page opens the sessions page, and its token opens no session's page. It makes no link: the terminal that ran `web` gives the only
one, so only the person who ran the command lists or starts anything. There is no view class here: there is nothing on it to show
another person that one session's view link does not show better.

The page keeps its token in the tab's own storage, so a reload, and coming back to it from a session's page, keep it, and closing
the tab or stopping `web` ends it.

### 3. Loopback alone

`web` with no session serves loopback alone: `--host` must name a loopback address or `localhost`, and anything else exits 64,
saying why and how to reach it from another machine. `--certificate` and `--key` stay as they are on loopback, and every page it
opens is served with them. Three reasons:

- **Its link runs code.** It starts any team file this user can read, and trusting one runs what it names, as you. Served to a
  network, the page would be a remote shell by design, however its link was kept.
- **A plan login is yours alone.** Every session it opens is served where it is, on loopback, so it opens a session on a plan login
  as freely as the terminal does, and starts one after asking once, and the refusal of an address past loopback
  ([security.md](../security.md)) never needs to fire later, once an agent has come up on one.
- **Forwarding already works.** As for a session's page, `ssh -L` reaches it from another machine, and the person at the other end
  of the forward is the one who ran `web`.

Every local user reaches loopback, as every loopback service of ours already accepts: the bearer keeps another user from reading or
acting, but not from holding connections ([security.md](../security.md#what-it-does-not-protect)).

### 4. Open: a session on a port of its own, by its own control link

Open serves the session in the same process, on a port of its own on the same host, as `web SESSION` would: its projection, its lock,
its two link classes, its own page that makes links, its forward line on stderr. It answers with a fresh control link of that
server, and the page goes to it in the same tab, where the session's page spends it as it spends any link. Opening a session this
`web` serves already mints a new control link of it. A session another `web` serves is refused, saying where that one serves, as a
second `web SESSION` is, since one projection has one writer. A session no runtime holds opens as its history, which names
Resume's command, as at `web SESSION`. Opening spends nothing: serving a session starts nothing.

A port per session is SwarmChat's page's own rule, one session per address, kept as it is. From another machine each needs a
forward of its own, and `web` says that forward on stderr as it opens one, before the page goes there.

### 5. Start: money said first, and trust and a plan login each asked once

The form takes a team file and a name, as the terminal's does. A team file is read from where `web` runs, as `run --team` reads one,
and left empty the project's own; a name left empty is made from the time. Above Start it says that starting launches the team's
harnesses here, in that folder, which can spend money. It takes no prompt, as the terminal's form takes none: the session's page,
which Start opens, is where you write to it.

The server then asks once for each thing only you can allow, before anything runs, by answering `ask`. The page shows its question,
and on yes sends the start again with the ask's `answer`. Nothing is kept: the next start asks again.

1. **Trust.** One read of the team's files gives both the team that would run and each value its files give that would run code
   as you or pass on a credential, which an untrusted load refuses needing trust: the SDK's `load_trusted`, which reads the layers
   as `load_team` does. A team that cannot load even trusted is refused with its problems. When a value needs trust, the question
   names each, by its place and as the team holds it, defaults filled in, `roles.lead.harness = "tools.lead:Lead"`. The answer is
   the digest of those lines, which the start carries as `trust`, and the server starts only a team whose lines have that digest,
   read again: what you trust is what you were shown, and a file changed since is asked about again. As the question and the team
   come from one read, a file rewritten while it is read cannot run a value the question left out.
2. **A plan login.** Several agents headless on one plan login, which `Session.start` refuses before any harness launches, are asked
   about with the terminal's words, `... Is this your own work?`, and the answer is `plan_login`, which the manifest keeps.

The session runs on a runtime of its own, started in `web`'s folder, as the terminal starts one, and it outlives `web`. Start then
opens it as Open does.

### 6. Resume and Stop, each asked once

Resume, on a session no runtime holds, asks once beside it, in the terminal's words: `Resume fix-auth? Its harnesses come back,
which can spend money.` Its runtime is one of its own, as at a start, and Resume opens it as Open does. A session a runtime holds is
refused, naming Open.

Stop, on a session a runtime holds, asks once beside it, in the terminal's words: `Stop fix-auth? Its turns are interrupted and its
harnesses end; it stays resumable.` It sends the owner's stop, as `session stop` does, and answers once the runtime has let go. A
page this `web` serves of it follows it into its history.

The list is read when the page opens, after each act, when the page is shown again, and on Look again. Each act a row cannot take
now is drawn disabled, saying why, as at a session's page: Resume where a runtime holds it, Stop where none does, Start until
the list has answered, as its answer says where a session starts and the form then says that starting can spend money, and every
act while one waits for its answer. Its reason is its accessible description, and focus or a press shows it in a tip over the page,
as the session's page does, so nothing under the pointer moves.

### 7. What is refused

| Asked | Answer |
|---|---|
| `web` with no session and `--host` past loopback | Exit 64, saying why and how to forward the port |
| A link or token the sessions page's server did not mint, a session page's among them | 401, as a spent link is |
| Any route but the page's, `/x/exchange` and the acts | 404 |
| Opening a session another `web` serves | Refused, saying where it serves |
| Starting a team that cannot load, trusted | Refused with every problem |
| Starting a team that needs trust, without trust in what was shown | Asked, never run |
| Starting several agents on a plan login without saying it is your own work | Asked, never run |
| A name that is taken, or a harness that cannot start | Refused, as `run` refuses it |
| Resuming a session a runtime holds | Refused, naming Open |
| Resuming a program's or a trainable session | Refused, as `Session.resume` refuses it |
| Stopping a session no runtime holds | Refused, as `session stop` refuses it |

## The hard parts

- **Trust that goes stale.** Between the question and the yes, an agent with a shell, at the same user, can write the team file.
  Trust carries the digest of what was shown, so a changed file is asked about again, and the question and the team that would run
  come from one read, so a file rewritten as it is read leaves nothing that runs out of the question, though such an agent could
  already run anything as you (architecture section 15).
- **A start cut short.** A start runs until its runtime is up, and a page that leaves before then cuts it, as every answer of the
  SDK's HTTP is cut when its client goes. A team cut while it prepares leaves no session, and one whose runtime had started runs on,
  which the list shows. No act is sent twice: a page that hears no answer says so and reads the list again.
- **A port per session.** From another machine, each session the page opens needs a forward of its own. `web` says each as it opens
  the session, and the address the page went to opens once the forward is up, within the link's ten minutes.

## Alternatives

| Alternative | Why not |
|---|---|
| A command of its own, such as `web --sessions` | A second way to name what `web` with nothing named already says, as `platoon-harness` alone is the terminal's sessions screen |
| The acts on each session's page, from its control link | A control link of one session, which a person may hand on as theirs, would reach every session and start any team |
| The sessions page past loopback, with TLS, refusing plan logins | Its link would run a team file's commands from the network. On loopback the plan-login refusal never fires, as nothing served from it leaves loopback |
| A view class of the sessions page | Another person gets one session's view link, from that session's page |
| A new link from the sessions page | Only the terminal that ran `web` gives one, so only that person holds it |
| Every session on one port, told apart by a name under `localhost` | A new name for each session, one listener before every session's server, and whether WebKit resolves such a name is unverified |
| Opening a session in a new tab | A browser blocks a window opened by an answer that comes seconds after the press, as a start's does |
| Trust as a field of the start form, as the terminal's | Trust given before anyone has seen what it covers |
| Trust as a yes, not as the digest of what was shown | A file changed between the question and the yes would run unseen |
| A question before every start, saying it can spend money | The form says it above Start, which is the deliberate act, as the terminal's form is |
| Writing a team, and saying what `doctor` finds, as the terminal's screen does | Nobody asked for them in the browser. `init` and `doctor` stay the terminal's and the command line's |
| Doing nothing | A shell for every start, resume and stop, and a `web` of its own for each session |

## Consequences

- `web` with no session is a guest of each session it reads, on a view credential, and of each it serves, on your control credential,
  so while a session's page is served from it an approval nobody else could answer waits for the page, as RFC 0027 says of `web
  SESSION`.
- A session started or resumed from the page runs on a runtime of its own, which outlives `web`. Stopping `web` ends every browser's
  session on every page it serves, and stops no session.
- A team file's trust is asked for each start and shown first, where the terminal's form and `--trust` take it unseen.
- The SDK gains `load_trusted`, a team loaded trusted with what its trust took, from one read, for a client that shows what it
  trusts before it runs it.
- The terminal's start form keeps its trust field: asking the page's way there too waits for the owner (open question 2).
- From another machine each session opened needs its own forward, which `web` says.
- Nothing here has run on macOS, in WebKit, or on a real model.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 List and open | `web` with no session, loopback alone, its one link and its own credentials, the list, Open on a port of its own, and the page | `tests/unit/web/test_sessions.py`, `test_only_the_sessions_link_opens_the_sessions_page_and_no_link_of_a_session_s_page_does`, `test_the_sessions_page_is_served_under_a_policy_that_lets_only_its_own_script_run`, `test_the_sessions_page_lists_every_session_whether_a_runtime_holds_it_and_its_state`, `test_opening_a_session_serves_it_on_a_port_of_its_own_and_answers_a_control_link_of_it`, `test_opening_a_session_another_web_serves_is_refused_saying_where`; `tests/integration/test_web.py`, `test_web_with_no_session_says_one_link_and_serves_loopback_alone`; `tests/e2e/test_sessions.py`, `test_the_sessions_page_lists_your_sessions_and_opens_one_on_its_own_control_link` | `feat: List and open your sessions from the browser with web and no session` |
| M2 Start, resume and stop | Start with trust and a plan login asked once, Resume after saying it can spend money, Stop after one question | `test_a_team_that_names_what_runs_as_you_is_asked_about_once_naming_it_before_anything_runs`, `test_trust_covers_what_was_shown_and_a_team_changed_since_is_asked_about_again`, `test_what_a_start_asks_to_trust_and_the_team_it_would_run_come_from_one_read_of_its_files`, `test_several_agents_on_a_plan_login_are_asked_about_once_and_the_answer_is_plan_login`, `test_resuming_a_session_a_runtime_holds_is_refused_naming_open`, `test_a_stop_answers_once_the_runtime_has_let_go`; `tests/integration/test_web.py`, `test_web_with_no_session_serves_tls_on_loopback_and_each_session_it_opens_with_it`; `tests/e2e/test_sessions.py`, `test_the_sessions_page_starts_a_session_asking_trust_once_and_opens_it`, `test_the_sessions_page_resumes_after_saying_it_can_spend_money_and_stops_after_one_question`, `test_what_the_sessions_page_is_told_stays_text_under_its_policy`, `test_start_is_disabled_until_the_list_has_said_where_it_starts_and_that_it_can_spend_money` | `feat: Start, resume and stop a session from the browser's sessions page` |

## Open questions

1. That other users on this machine are out of scope, which every loopback service of ours rests on, is the default pending the
   owner's ruling on the threat model. The sessions page's bearer keeps another user from reading or acting, and nothing keeps one
   from holding its connections. A ruling the other way would move the page from a port to a socket only you can open, and tear
   nothing else out.
2. Whether the terminal's start form should ask for trust as the page does, naming what it trusts once the team needs it, is the
   owner's. The default, pending the owner's ruling, is that it keeps its field, which no test or guide of this RFC changes. A ruling
   the other way would change that form, and tear nothing here out.

## Evidence

- [`tui/sessions.py`](../../packages/cli/src/platoon_harness_cli/tui/sessions.py) and `tests/integration/test_tui.py`: the
  terminal's screen, its plan login asked about once, its resume saying it can spend money and its stop with one confirmation, whose
  acts and words the page keeps.
- `load_team` ([`config.py`](../../packages/sdk/src/platoon_harness/config.py)) refuses each value that needs trust only once the
  team validates, so a team that loads trusted and not untrusted fails on trust alone, and each refusal names that value's place.
  `load_trusted` gives the team and those refusals from one read of the layers, which
  `test_what_a_start_asks_to_trust_and_the_team_it_would_run_come_from_one_read_of_its_files` holds, with a file rewritten as it
  is read.
- `Session.start` refuses several agents on a plan login in `prepare`, before any harness launches
  ([architecture section 15](../architecture.md#15-security)).
- `Credentials` ([`web/credentials.py`](../../packages/cli/src/platoon_harness_cli/web/credentials.py)) are a server's own, in its
  memory, so two servers in one process share none.
- The tests the rollout plan names.
