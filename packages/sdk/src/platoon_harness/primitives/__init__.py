"""The core primitives, as extensions on the public kernel API and nothing else."""

from platoon_harness.kernel import Extension

from . import (
    approvals,
    blobs,
    boards,
    budgets,
    channels,
    clients,
    delivery,
    lifecycle,
    messages,
    sessions,
    tasks,
    waits,
)
from .agents import Agent, Agents
from .approvals import Approval, Approvals
from .boards import Boards
from .budgets import Budgets
from .channels import Channels, Groups, channel_grants
from .clients import Attention, Changes
from .common import WAKING, Delivery, stream_of
from .delivery import courier
from .messages import Cursor, Deliveries, Entry
from .sessions import Session, Settings
from .tasks import Task, Tasks
from .waits import Condition, Waits, hold_open, on
from .why import Why

PRIMITIVES = (
    Extension(
        "session",
        ops=[
            sessions.open_session,
            sessions.show_manifest,
            lifecycle.session_status,
            lifecycle.close,
            lifecycle.cancel_session,
            lifecycle.stop,
        ],
        views=[Session],
    ),
    Extension("episode", ops=[sessions.open_episode, sessions.close_episode]),
    Extension("budget", ops=[budgets.set_budget, budgets.budget_status], views=[Budgets]),
    Extension(
        "agent",
        ops=[
            lifecycle.spawn,
            lifecycle.finish,
            lifecycle.interrupt,
            lifecycle.cancel,
            lifecycle.retire,
            lifecycle.takeover,
            lifecycle.release,
            lifecycle.report,
            lifecycle.list_agents,
            lifecycle.agent_status,
        ],
        views=[Agents],
    ),
    Extension("peers", ops=[lifecycle.peers]),
    Extension("channel", ops=[channels.create, channels.list_channels], views=[Channels]),
    Extension("group", ops=[channels.define_group], views=[Groups]),
    Extension("message", ops=[messages.send, messages.read], views=[Deliveries]),
    Extension(
        "delivery",
        ops=[delivery.offer, delivery.confirm, delivery.delivery_ready],
        daemons=[courier],
    ),
    Extension("wait", ops=[waits.wait_for, waits.cancel, waits.release, waits.progress_of], views=[Waits]),
    Extension("board", ops=[boards.post, boards.revise, boards.get, boards.query], views=[Boards]),
    Extension(
        "task",
        ops=[tasks.add, tasks.claim, tasks.renew, tasks.release, tasks.complete, tasks.fail, tasks.list_tasks],
        views=[Tasks],
    ),
    Extension("lease", ops=[tasks.expire_lease]),
    Extension("approval", ops=[approvals.request, approvals.resolve], views=[Approvals]),
    Extension("blob", ops=[blobs.get]),
    Extension("attention", ops=[clients.attention_list], views=[Attention]),
    Extension("view", ops=[clients.watch], views=[Changes]),
)

__all__ = [
    "PRIMITIVES",
    "WAKING",
    "Agent",
    "Agents",
    "Approval",
    "Approvals",
    "Attention",
    "Boards",
    "Budgets",
    "Changes",
    "Channels",
    "Condition",
    "Cursor",
    "Deliveries",
    "Delivery",
    "Entry",
    "Groups",
    "Session",
    "Settings",
    "Task",
    "Tasks",
    "Waits",
    "Why",
    "channel_grants",
    "hold_open",
    "on",
    "stream_of",
]
