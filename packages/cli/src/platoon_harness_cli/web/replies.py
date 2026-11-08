"""The `view_*` replies SwarmChat's page asks for, over the projection, in the shapes its own server gives them.

Each reads the projection and writes nothing. Where SwarmChat says a member has read a message, these say it was
delivered to that agent, from the journal's evidence alone, and a person, whose reading is no evidence, is in neither
list."""

import bisect
import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .projection import Projection

PREVIEW = 160
RECENT = 900.0
LIMIT = 500
FEED_LIMIT = 5000
UNVOTED = "a session's messages take no reactions, so there are no votes to rank by: sort is new or active"
_POSTS = """
WITH RECURSIVE thread(chat, post, seq) AS (
    SELECT chat, seq, seq FROM lines
    WHERE kind = 'message' AND parent IS NULL AND chat IN (SELECT value FROM json_each(?))
    UNION ALL
    SELECT lines.chat, thread.post, lines.seq FROM lines
    JOIN thread ON (lines.chat, lines.parent) = (thread.chat, thread.seq)
),
posts(chat, post, comments, newest) AS (SELECT chat, post, count(*) - 1, max(seq) FROM thread GROUP BY chat, post)
SELECT post.*, posts.comments, newest.time AS active_at FROM posts
JOIN lines AS post ON (post.chat, post.seq) = (posts.chat, posts.post)
JOIN lines AS newest ON (newest.chat, newest.seq) = (posts.chat, posts.newest)
ORDER BY {order} DESC, post.seq DESC, post.chat DESC LIMIT ? OFFSET ?
"""
"""Each top-level message of the chats named, with how many messages are below it in its thread and when the newest of
them was written, or the post itself when none is."""

Statuses = Mapping[str, str]
"""Each agent's status, as the roster says it now."""


class Error(Exception):
    """A request the projection cannot answer, with SwarmChat's status for it and why."""

    def __init__(self, status: int, why: str) -> None:
        super().__init__(why)
        self.status = status


def _int(params: Mapping[str, Any], key: str, default: int, most: int) -> int:
    value = params.get(key)
    if value in (None, ""):
        return default
    try:
        return max(0, min(most, int(value)))
    except (TypeError, ValueError, OverflowError):
        raise Error(400, f"{key} is a whole number") from None


def _names(params: Mapping[str, Any], key: str) -> list[str]:
    value = params.get(key) or []
    if not (isinstance(value, list) and all(isinstance(name, str) for name in value)):
        raise Error(400, f"{key} is a list of names")
    return value


def _epoch(at: Any) -> float:
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00")).timestamp()
    except ValueError:
        raise Error(400, f"{at!r} is no time") from None


def _seconds(params: Mapping[str, Any], key: str) -> float:
    try:
        return float(params[key])
    except (TypeError, ValueError):
        raise Error(400, f"{key} is a time in seconds since 1970") from None


def _line(projection: Projection, id: Any) -> sqlite3.Row:
    chat, _, seq = str(id or "").partition(":")
    row = projection.db.execute("SELECT * FROM lines WHERE chat = ? AND seq = ?", (chat, seq)).fetchone()
    if row is None or row["kind"] != "message":
        raise Error(404, f"There is no message {id}.")
    return row


def _chat_row(projection: Projection, id: Any) -> sqlite3.Row:
    row = projection.db.execute("SELECT * FROM chats WHERE id = ?", (str(id or "").strip(),)).fetchone()
    if row is None:
        raise Error(404, f"There is no chat {id}.")
    return row


def _members(projection: Projection, chat: str) -> list[str]:
    return [row[0] for row in projection.db.execute("SELECT user FROM members WHERE chat = ? ORDER BY user", (chat,))]


def _kind(chat: sqlite3.Row, members: list[str]) -> str:
    return "channel" if chat["name"] else "direct" if len(members) == 2 else "group"


def _short(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "seq": row["seq"],
        "from": row["sender"],
        "at": row["at"],
        "text": row["text"][:PREVIEW],
        "deleted": False,
        "files": 1 if row["file"] else 0,
    }


def message(projection: Projection, row: sqlite3.Row) -> dict[str, Any]:
    """A line as the page shows it: a message, with whatever answers it and what it answers, or a line of its chat's
    own. `x_ref` names the journal's entry, which a reply cites, `x_shows` the event a message shows, which its
    Provenance follows, and `x_approval` an approval's card."""
    chat, seq = row["chat"], row["seq"]
    shown: dict[str, Any] = {"id": f"{chat}:{seq}", "chat": chat, "seq": seq, "kind": row["kind"]}
    shown |= {"from": row["sender"], "at": row["at"]}
    if row["kind"] != "message":
        return shown | json.loads(row["extra"])
    shown |= {"text": row["text"], "x_shows": row["shows"]}
    db = projection.db
    if row["parent"] is not None:
        parent = db.execute("SELECT * FROM lines WHERE chat = ? AND seq = ?", (chat, row["parent"])).fetchone()
        shown |= {"reply_to": f"{chat}:{parent['seq']}", "reply_to_from": parent["sender"]}
    shown |= json.loads(row["extra"])
    if row["file"]:
        shown["attachments"] = [json.loads(row["file"])]
    shown["replies"] = db.execute("SELECT count(*) FROM lines WHERE chat = ? AND parent = ?", (chat, seq)).fetchone()[0]
    if row["parent"] is not None:
        shown["parent"] = _short(parent)
    if row["stream"] is not None:
        shown["x_ref"] = row["ref"]
    return shown


def summary(projection: Projection, chat: sqlite3.Row) -> dict[str, Any]:
    """A chat for the page's lists, with `x_to`, the address a person's message to it goes to, or None for a chat
    that takes none from them."""
    db, id = projection.db, chat["id"]
    members = _members(projection, id)
    last = db.execute(
        "SELECT * FROM lines WHERE chat = ? AND kind = 'message' ORDER BY seq DESC LIMIT 1", (id,)
    ).fetchone()
    tally = db.execute(
        "SELECT sender, count(*), max(time) FROM lines WHERE chat = ? AND kind = 'message' GROUP BY sender", (id,)
    ).fetchall()
    return {
        "id": id,
        "kind": _kind(chat, members),
        "name": chat["name"],
        "description": chat["about"],
        "public": False,
        "archived": False,
        "members": members,
        "managers": [],
        "created_by": chat["created_by"],
        "created_at": chat["created_at"],
        "seq": chat["seq"],
        "messages": sum(row[1] for row in tally),
        "last_at": last["at"] if last else chat["created_at"],
        "last": _short(last) if last else None,
        "sent": {row[0]: row[1] for row in tally},
        "last_by": {row[0]: row[2] for row in tally},
        "x_to": chat["address"],
    }


def _newest(projection: Projection) -> float:
    return projection.db.execute("SELECT coalesce(max(time), 0) FROM lines WHERE kind = 'message'").fetchone()[0]


def person(projection: Projection, id: str, statuses: Statuses) -> dict[str, Any]:
    row = projection.db.execute("SELECT fields FROM users WHERE id = ?", (id,)).fetchone()
    fields = json.loads(row[0]) if row else {}
    return {"id": id, "name": id, "fields": fields, "status": statuses.get(id, "")}


def snapshot(projection: Projection, server: dict[str, Any], statuses: Statuses, now: float) -> dict[str, Any]:
    """Every person and chat, each chat with how many messages it had in the `RECENT` seconds before the newest
    anywhere. `feed` is taken first, so whatever comes after it comes through the feed."""
    db, feed, since = projection.db, projection.count, _newest(projection) - RECENT
    recent = "SELECT count(*) FROM lines WHERE chat = ? AND kind = 'message' AND time >= ?"
    chats = [
        summary(projection, chat) | {"recent": db.execute(recent, (chat["id"], since)).fetchone()[0]}
        for chat in db.execute("SELECT * FROM chats ORDER BY id")
    ]
    users = [person(projection, row[0], statuses) for row in projection.db.execute("SELECT id FROM users ORDER BY id")]
    return {"feed": feed, "server": server, "users": users, "chats": chats, "now": now}


def _positions(projection: Projection, chat: str) -> dict[str, int]:
    """How far each agent of a chat has been delivered it, by the seq of the newest line delivered."""
    rows = projection.db.execute(
        "SELECT reader, coalesce(max(CASE WHEN event IS NOT NULL THEN seq END), 0) FROM deliveries WHERE chat = ? "
        "GROUP BY reader ORDER BY reader",
        (chat,),
    )
    return dict(rows.fetchall())


def messages(projection: Projection, params: Mapping[str, Any]) -> dict[str, Any]:
    """A run of a chat's messages, oldest first: the newest `limit`, or those just `before` or `after` a seq, or those
    `around` one, with the chat's own lines in the same stretch."""
    chat = _chat_row(projection, params.get("chat"))["id"]
    db = projection.db
    limit = _int(params, "limit", 100, LIMIT) or 1
    seqs = [
        row[0] for row in db.execute("SELECT seq FROM lines WHERE chat = ? AND kind = 'message' ORDER BY seq", (chat,))
    ]
    n = len(seqs)
    if params.get("around") is not None:
        i = bisect.bisect_left(seqs, _int(params, "around", 0, 2**62))
        lo = max(0, min(i - limit // 2, n - limit))
        hi = min(n, lo + limit)
    elif params.get("before") is not None:
        hi = bisect.bisect_left(seqs, _int(params, "before", 0, 2**62))
        lo = max(0, hi - limit)
    elif params.get("after") is not None:
        lo = bisect.bisect_right(seqs, _int(params, "after", 0, 2**62))
        hi = min(n, lo + limit)
    else:
        hi, lo = n, max(0, n - limit)
    low = 0 if lo == 0 else seqs[lo]
    high = 2**62 if hi == n else seqs[hi - 1]
    rows = db.execute("SELECT * FROM lines WHERE chat = ? AND seq BETWEEN ? AND ? ORDER BY seq", (chat, low, high))
    return {
        "chat": chat,
        "messages": [message(projection, row) for row in rows],
        "first": lo == 0,
        "last": hi == n,
        "index": lo,
        "total": n,
        "positions": _positions(projection, chat),
    }


def thread(projection: Projection, params: Mapping[str, Any]) -> dict[str, Any]:
    """The whole thread a message is in, each message with its depth."""
    row = _line(projection, params.get("id"))
    db, chat = projection.db, row["chat"]
    while row["parent"] is not None:
        row = db.execute("SELECT * FROM lines WHERE chat = ? AND seq = ?", (chat, row["parent"])).fetchone()
    found, below = [], [(row, 0)]
    while below:
        line, depth = below.pop()
        found.append({**message(projection, line), "depth": depth})
        replies = db.execute("SELECT * FROM lines WHERE chat = ? AND parent = ? ORDER BY seq DESC", (chat, line["seq"]))
        below += [(reply, depth + 1) for reply in replies]
    return {"chat": chat, "messages": found, "positions": _positions(projection, chat)}


def receipts(projection: Projection, params: Mapping[str, Any]) -> dict[str, Any]:
    """Which agents a message was delivered to, and when, and which it was for and has not reached yet."""
    row = _line(projection, params.get("id"))
    rows = projection.db.execute(
        "SELECT reader, at FROM deliveries WHERE chat = ? AND seq = ? ORDER BY at, reader", (row["chat"], row["seq"])
    ).fetchall()
    return {
        "id": f"{row['chat']}:{row['seq']}",
        "read": [{"id": reader, "at": at} for reader, at in rows if at is not None],
        "unread": [reader for reader, at in rows if at is None],
    }


def posts(projection: Projection, params: Mapping[str, Any]) -> dict[str, Any]:
    """Top-level messages as posts, from one chat or from every channel and group, newest first by when each was
    written, `new`, or last answered, `active`, each with how many messages are below it in its thread. With `as`, only
    the chats that agent is in. A session's messages take no reactions, so a post's votes are unknown, and hot and top,
    which rank by votes, are refused."""
    sort = params.get("sort") or "new"
    if sort not in ("new", "active"):
        raise Error(400, UNVOTED if sort in ("hot", "top") else "sort is new or active")
    limit, offset = _int(params, "limit", 30, 200) or 1, _int(params, "offset", 0, 10**9)
    db = projection.db
    if params.get("chat"):
        chats = [_chat_row(projection, params["chat"])["id"]]
    else:
        every = db.execute("SELECT * FROM chats ORDER BY id").fetchall()
        chats = [chat["id"] for chat in every if _kind(chat, _members(projection, chat["id"])) != "direct"]
    if params.get("as"):
        user = _agent(projection, params["as"])
        chats = [chat for chat in chats if user in _members(projection, chat)]
    order = "post.time" if sort == "new" else "newest.time"
    rows = db.execute(_POSTS.format(order=order), (json.dumps(chats), limit + 1, offset)).fetchall()
    found = [
        message(projection, row) | {"comments": row["comments"], "votes": None, "active_at": row["active_at"]}
        for row in rows[:limit]
    ]
    return {"posts": found, "more": len(rows) > limit}


def search(projection: Projection, params: Mapping[str, Any]) -> dict[str, Any]:
    """Messages, newest first, from every chat or only `chats`, or an agent's chats with `as`, narrowed by `from`,
    `mentions`, `files`, `after` and `before`, with `text` found in any case in the text a message shows. For the next
    page, pass the reply's `until`."""
    limit = _int(params, "limit", 50, LIMIT) or 1
    where, args = ["kind = 'message'"], []
    if chats := _names(params, "chats"):
        where.append(f"chat IN ({', '.join('?' * len(chats))})")
        args += chats
    if params.get("as"):
        where.append("chat IN (SELECT chat FROM members WHERE user = ?)")
        args.append(str(params["as"]))
    if senders := _names(params, "from"):
        where.append(f"sender IN ({', '.join('?' * len(senders))})")
        args += senders
    if params.get("mentions"):
        where.append("EXISTS (SELECT 1 FROM json_each(extra, '$.mentions') WHERE value = ?)")
        args.append(str(params["mentions"]))
    if params.get("files"):
        where.append("file IS NOT NULL")
    if params.get("after"):
        where.append("time >= ?")
        args.append(_epoch(params["after"]))
    if params.get("before"):
        where.append("time < ?")
        args.append(_epoch(params["before"]))
    if params.get("until"):
        try:
            time, chat, seq = params["until"]
            args += [float(time), str(chat), int(seq)]
        except (TypeError, ValueError, OverflowError):
            raise Error(400, "until is the one a reply gave") from None
        where.append("(time, chat, seq) < (?, ?, ?)")
    text = str(params.get("text") or "").strip().casefold()
    found = []
    rows = projection.db.execute(
        f"SELECT * FROM lines WHERE {' AND '.join(where)} ORDER BY time DESC, chat DESC, seq DESC", args
    )
    for row in rows:
        if text in row["text"].casefold():
            found.append(row)
            if len(found) == limit:
                break
    until = [found[-1]["time"], found[-1]["chat"], found[-1]["seq"]] if len(found) == limit else None
    return {"messages": [message(projection, row) for row in found], "until": until}


def activity(projection: Projection, params: Mapping[str, Any]) -> dict[str, Any]:
    """Messages over time, by the journal's times: how many fell in each of `buckets` stretches, from the first message
    to the last, across every chat or the chats an agent is in, with `as`. With `from` and `to`, in seconds since 1970,
    how many each chat had from the one through the other, and from whom."""
    where, args = "kind = 'message'", []
    if params.get("as"):
        where += " AND chat IN (SELECT chat FROM members WHERE user = ?)"
        args.append(_agent(projection, params["as"]))
    db = projection.db
    first, last = db.execute(f"SELECT min(time), max(time) FROM lines WHERE {where}", args).fetchone()
    if first is None:
        return {"start": None, "end": None, "width": None, "counts": [], "window": {}}
    buckets = _int(params, "buckets", 200, 2000) or 1
    width = max((last - first) / buckets, 0.001)
    counts = [0] * buckets
    for bucket, n in db.execute(
        f"SELECT min(?, CAST((time - ?) / ? AS INTEGER)), count(*) FROM lines WHERE {where} GROUP BY 1",
        (buckets - 1, first, width, *args),
    ):
        counts[bucket] = n
    shown: dict[str, Any] = {"start": first, "end": last, "width": width, "counts": counts}
    if params.get("from") is not None and params.get("to") is not None:
        window: dict[str, dict[str, Any]] = {}
        rows = db.execute(
            f"SELECT chat, sender, count(*) FROM lines WHERE {where} AND time BETWEEN ? AND ? GROUP BY chat, sender",
            (*args, _seconds(params, "from"), _seconds(params, "to")),
        )
        for chat, sender, n in rows:
            counted = window.setdefault(chat, {"messages": 0, "sent": {}})
            counted["messages"] += n
            counted["sent"][sender] = n
        shown["window"] = window
    return shown


def _agent(projection: Projection, id: Any) -> str:
    row = projection.db.execute("SELECT kind FROM users WHERE id = ?", (str(id or ""),)).fetchone()
    if row is None:
        raise Error(404, f"There is no one called {id}.")
    if row[0] != "agent":
        raise Error(400, f"{id} is no agent, and only an agent leaves evidence of what reached it")
    return str(id)


def _as_read(projection: Projection, row: sqlite3.Row, user: str) -> dict[str, Any]:
    """A message as an agent's own reads give it: its sender's name, and on its own messages, whom each was delivered
    to and when, and whom not yet."""
    shown = {key: value for key, value in message(projection, row).items() if key not in ("replies", "parent")}
    shown["from_name"] = row["sender"]
    if row["sender"] == user:
        rows = projection.db.execute(
            "SELECT reader, at FROM deliveries WHERE chat = ? AND seq = ? ORDER BY reader", (row["chat"], row["seq"])
        ).fetchall()
        shown["read_by"] = [{"id": reader, "name": reader, "at": at} for reader, at in rows if at is not None]
        shown["unread_by"] = [reader for reader, at in rows if at is None]
    return shown


def seen_as(projection: Projection, params: Mapping[str, Any], statuses: Statuses) -> dict[str, Any]:
    """What one agent's chats are, how far each was delivered to it, and with `unread`, what waits to reach it, oldest
    first. Nothing is marked."""
    user = _agent(projection, params.get("user"))
    db = projection.db
    chats, positions = [], {}
    rows = db.execute("SELECT c.* FROM chats AS c JOIN members AS m ON m.chat = c.id WHERE m.user = ?", (user,))
    for chat in rows:
        members = _members(projection, chat["id"])
        last = db.execute(
            "SELECT * FROM lines WHERE chat = ? AND kind = 'message' ORDER BY seq DESC LIMIT 1", (chat["id"],)
        ).fetchone()
        unread = db.execute(
            "SELECT count(*) FROM deliveries WHERE chat = ? AND reader = ? AND event IS NULL", (chat["id"], user)
        ).fetchone()[0]
        others = [member for member in members if member != user] or members
        chats.append(
            {
                "id": chat["id"],
                "kind": "channel" if chat["name"] else "direct",
                "name": chat["name"],
                "description": chat["about"],
                "public": False,
                "archived": False,
                "managers": [],
                "title": f"#{chat['name']}" if chat["name"] else ", ".join(others),
                "members": [{"id": member, "name": member} for member in members],
                "unread": unread,
                "mentioned": False,
                "notify": "all",
                "last_at": last["at"] if last else chat["created_at"],
                "last": _as_read(projection, last, user) if last else None,
            }
        )
        positions[chat["id"]] = _positions(projection, chat["id"]).get(user, 0)
    chats.sort(key=lambda chat: chat["last_at"], reverse=True)
    shown: dict[str, Any] = {"user": person(projection, user, statuses), "chats": chats, "positions": positions}
    if params.get("unread"):
        waiting = db.execute(
            "SELECT l.* FROM deliveries AS d JOIN lines AS l ON (l.chat, l.seq) = (d.chat, d.seq) "
            "WHERE d.reader = ? AND d.event IS NULL ORDER BY l.event",
            (user,),
        ).fetchall()
        shown["unread"] = [_as_read(projection, row, user) for row in waiting[: _int(params, "limit", 50, LIMIT) or 50]]
        shown["unread_left"] = len(waiting)
    return shown


def knew(projection: Projection, params: Mapping[str, Any]) -> dict[str, Any]:
    """How far each of its chats had been delivered to the agent that sent a message, when it sent it: what a handover
    landed or a tool's result showed, which is not what it understood."""
    row = _line(projection, params.get("id"))
    user, sent = _agent(projection, row["sender"]), row["event"]
    db = projection.db
    chats = {row["chat"]} | {
        found[0] for found in db.execute("SELECT DISTINCT chat FROM deliveries WHERE reader = ?", (user,))
    }
    found = []
    for chat in sorted(chats):
        messages = db.execute(
            "SELECT count(*), coalesce(max(seq), 0) FROM lines WHERE chat = ? AND kind = 'message' AND event <= ?",
            (chat, sent),
        ).fetchone()
        delivered = db.execute(
            "SELECT count(*), coalesce(max(d.seq), 0), max(d.at) FROM deliveries AS d "
            "WHERE d.chat = ? AND d.reader = ? AND d.event < ?",
            (chat, user, sent),
        ).fetchone()
        unseen = db.execute(
            "SELECT count(*) FROM deliveries AS d JOIN lines AS l ON (l.chat, l.seq) = (d.chat, d.seq) "
            "WHERE d.chat = ? AND d.reader = ? AND l.event <= ? AND (d.event IS NULL OR d.event >= ?)",
            (chat, user, sent, sent),
        ).fetchone()[0]
        found.append(
            {
                "chat": chat,
                "upto": delivered[1],
                "read_at": delivered[2],
                "messages": messages[0],
                "read": delivered[0],
                "last": messages[1],
                "unseen": unseen,
            }
        )
    found.sort(key=lambda shown: (shown["chat"] != row["chat"], -shown["unseen"], shown["chat"]))
    return {"message": message(projection, row), "user": user, "at": row["at"], "chats": found}


def at(projection: Projection, ref: str, seq: int) -> str | None:
    """The message an event is in its chat, by the ref the message shows or by the seq of the event that made it, the
    first where several are, or None for an event no chat shows."""
    row = projection.db.execute(
        "SELECT chat, seq FROM lines WHERE kind = 'message' AND (shows = ? OR event = ?) ORDER BY event, chat LIMIT 1",
        (ref, seq),
    ).fetchone()
    return None if row is None else f"{row['chat']}:{row['seq']}"


def asked(projection: Projection, id: str) -> int:
    """The journal's seq of the request of the approval `id`, which its card shows."""
    row = projection.db.execute(
        "SELECT lines.event FROM approvals JOIN lines ON (lines.chat, lines.seq) = (approvals.chat, approvals.seq) "
        "WHERE approvals.id = ?",
        (id,),
    ).fetchone()
    if row is None:
        raise Error(404, f"There is no approval {id} with a card.")
    return row[0]


def attachment(projection: Projection, params: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """An attachment and the ref of its body, from any chat."""
    id = str(params.get("id") or "")
    row = projection.db.execute(
        "SELECT file, body FROM lines WHERE json_extract(file, '$.id') = ? LIMIT 1", (id,)
    ).fetchone()
    if row is None:
        raise Error(404, f"There is no file {id}.")
    return {key: value for key, value in json.loads(row["file"]).items() if key != "text"}, row["body"]


def feed(projection: Projection, after: int, statuses: Statuses) -> dict[str, Any]:
    """The feed past `after`, each entry as it stands now: a message, a change to one, a line of a chat's own with
    the chat, a person, how far a chat was delivered to an agent, or a queue's or a board's chat whose view moved."""
    db = projection.db
    entries = list(projection.entries(after, FEED_LIMIT))
    events = []
    for entry in entries:
        n, kind, chat, seq = entry["n"], entry["kind"], entry["chat"], entry["seq"]
        if kind == "user":
            events.append({"n": n, "kind": "user", "user": person(projection, entry["user"], statuses)})
            continue
        if kind == "x_moved":
            events.append({"n": n, "kind": "x_moved", "chat": chat})
            continue
        if kind == "read":
            line = db.execute("SELECT at FROM lines WHERE chat = ? AND seq = ?", (chat, entry["upto"])).fetchone()
            current = db.execute("SELECT seq FROM chats WHERE id = ?", (chat,)).fetchone()[0]
            events.append(
                {
                    "n": n,
                    "kind": "read",
                    "chat": chat,
                    "seq": current,
                    "user": entry["user"],
                    "upto": entry["upto"],
                    "at": line["at"],
                }
            )
            continue
        row = db.execute("SELECT * FROM lines WHERE chat = ? AND seq = ?", (chat, seq)).fetchone()
        if kind == "message":
            count = db.execute(
                "SELECT count(*) FROM lines WHERE chat = ? AND kind = 'message' AND seq <= ?", (chat, seq)
            ).fetchone()[0]
            events.append(
                {
                    "n": n,
                    "kind": "message",
                    "chat": chat,
                    "seq": seq,
                    "count": count,
                    "message": message(projection, row),
                }
            )
        elif kind == "change":
            events.append(
                {
                    "n": n,
                    "kind": "change",
                    "chat": chat,
                    "seq": seq,
                    "change": "edit",
                    "from": row["sender"],
                    "message": message(projection, row),
                }
            )
        else:
            chat_row = db.execute("SELECT * FROM chats WHERE id = ?", (chat,)).fetchone()
            line = {key: value for key, value in message(projection, row).items() if key not in ("id", "chat")}
            events.append(
                {
                    "n": n,
                    "kind": "chat",
                    "chat": chat,
                    "seq": seq,
                    "event": line,
                    "summary": summary(projection, chat_row),
                }
            )
    return {"feed": entries[-1]["n"] if entries else after, "events": events}
