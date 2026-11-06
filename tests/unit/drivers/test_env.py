"""The harness environment: an allowlist, proved on real children."""

import asyncio
import json
import os

import pytest

from platoon_harness.config import Secret
from platoon_harness.drivers import Gateway, ToolBinding
from platoon_harness.drivers.env import Held, Redactor, harness_env, open_beneath, private, secrets_of
from platoon_harness.drivers.process import LOG, RECORD, Process
from platoon_harness.tools.ph import TOKEN_VARIABLE, URL_VARIABLE

from .support import Heard, make_spec

pytestmark = pytest.mark.timeout(30)


async def child_env(tmp_path, spec) -> tuple[dict[str, str], str]:
    """What a real child sees, and the raw text of its environment."""
    output = bytearray()

    async def read(process: Process) -> None:
        output.extend(await process.stdout.read())

    heard = Heard()
    process = await Process.launch(["env", "-0"], spec, heard, read=read)
    await process.exited()
    await process.stop(1)
    text = output.decode()
    return dict(line.split("=", 1) for line in text.split("\0") if line), text


async def test_a_value_nobody_named_cannot_reach_a_child(tmp_path, monkeypatch):
    for name in ("PLATOON_TEST_SECRET", "ANTHROPIC_API_KEY", "CLAUDECODE", "AWS_SECRET_ACCESS_KEY", "LD_PRELOAD"):
        monkeypatch.setenv(name, "this must never pass")

    env, text = await child_env(tmp_path, make_spec(tmp_path))

    assert "this must never pass" not in text
    assert set(env) - {"PWD", "_", "SHLVL", "OLDPWD"} == {"PATH", "HOME", "TMPDIR"}


async def test_path_and_home_are_inherited_and_tmpdir_is_supplied(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", "/somewhere/else")
    spec = make_spec(tmp_path)

    env, _ = await child_env(tmp_path, spec)

    assert env["PATH"] == os.environ["PATH"]
    assert env["HOME"] == os.environ["HOME"]
    assert env["TMPDIR"] == str(spec.folder / "tmp")
    assert (spec.folder / "tmp").stat().st_mode & 0o777 == 0o700


async def test_what_the_auth_profile_names_reaches_the_child_and_nothing_else_does(tmp_path):
    spec = make_spec(tmp_path, access={"MODEL_KEY": Secret("the-key"), "MODEL_URL": Secret("http://gateway/secret")})

    env, _ = await child_env(tmp_path, spec)

    assert (env["MODEL_KEY"], env["MODEL_URL"]) == ("the-key", "http://gateway/secret")


async def test_a_credential_stays_out_of_every_file_of_the_agent(tmp_path):
    spec = make_spec(tmp_path, access={"MODEL_KEY": Secret("the-key-value")})

    await child_env(tmp_path, spec)

    for path in spec.folder.rglob("*"):
        if path.is_file():
            assert b"the-key-value" not in path.read_bytes(), path


def test_a_write_beneath_a_folder_does_not_follow_a_symlink_planted_in_it(tmp_path):
    """Neither one at the file's own name, nor one where a folder on the way should be: so a confined agent cannot
    redirect the runtime's write to a path outside its folder."""
    folder, outside = tmp_path / "folder", tmp_path / "outside"
    (folder / "sub").mkdir(parents=True)
    outside.write_text("canary")
    (folder / "at-name").symlink_to(outside)
    (folder / "sub" / "deep").symlink_to(outside)
    (folder / "as-dir").symlink_to(tmp_path / "elsewhere")

    with pytest.raises(OSError):
        open_beneath(folder, folder / "at-name", os.O_WRONLY | os.O_TRUNC)
    with pytest.raises(OSError):
        private(folder, folder / "sub" / "deep", "hello")
    with pytest.raises(OSError):
        private(folder, folder / "as-dir" / "file", "hello")

    assert outside.read_text() == "canary"
    assert not (tmp_path / "elsewhere").exists()
    assert private(folder, folder / "fresh", "ok") == str(folder / "fresh")
    assert (folder / "fresh").read_text() == "ok"


def test_the_tool_binding_reaches_ph_and_nothing_prints_it(tmp_path):
    bin = tmp_path / "bin"
    tools = ToolBinding(url="http://127.0.0.1:1/mcp", token=Secret("tool-token"), namespace="ph", bin=bin)
    spec = make_spec(tmp_path, tools=tools)

    env = harness_env(spec, environ={"PATH": "/usr/bin"})

    assert env["PATH"] == f"{bin}{os.pathsep}/usr/bin"
    assert (env[URL_VARIABLE], env[TOKEN_VARIABLE]) == ("http://127.0.0.1:1/mcp", "tool-token")
    assert "tool-token" not in repr(spec)


def test_later_entries_win(tmp_path):
    spec = make_spec(tmp_path, env={"HOME": "/from/spec", "X": "1"}, access={"X": Secret("2")})

    env = harness_env(spec, environ={"HOME": "/inherited"})

    assert (env["HOME"], env["X"]) == ("/from/spec", "2")


def test_a_home_the_spec_names_is_the_harness_s_home(tmp_path):
    """So none of the variables that keep a harness's state elsewhere than under its home is inherited over it, and
    what signs it in from your shell, as a proxy, still is."""
    spec = make_spec(tmp_path, env={"HOME": str(tmp_path / "home")})
    state = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR", "PI_CODING_AGENT_SESSION_DIR")
    yours = {name: f"/yours/{name}" for name in state} | {"HOME": "/yours", "HTTPS_PROXY": "http://proxy:3128"}

    env = harness_env(spec, *state, "HTTPS_PROXY", environ=yours)
    unset = harness_env(make_spec(tmp_path), *state, environ=yours)

    assert env["HOME"] == str(tmp_path / "home")
    assert env["HTTPS_PROXY"] == "http://proxy:3128"
    assert not set(state) & set(env)
    assert {name: unset[name] for name in state} == {name: f"/yours/{name}" for name in state}


def test_a_spec_refuses_to_serialize_a_credential(tmp_path):
    spec = make_spec(tmp_path, access={"MODEL_KEY": Secret("the-key")})

    for dump in (spec.model_dump, spec.model_dump_json):
        with pytest.raises((TypeError, ValueError), match="refuses"):
            dump()


def test_secrets_of_finds_every_credential(tmp_path):
    token, key = Secret("t"), Secret("k")
    tools = ToolBinding(url="http://x", token=token, namespace="ph", bin=tmp_path)

    assert set(secrets_of(make_spec(tmp_path, tools=tools, access={"K": key}))) == {token, key}


def test_a_gateway_s_bearer_is_a_credential_its_spec_holds(tmp_path):
    bearer, token = Secret("b"), Secret("t")
    tools = ToolBinding(url="http://x", token=token, namespace="ph", bin=tmp_path)
    gateway = Gateway(origin="http://127.0.0.1:9", bearer=bearer, model="m")
    spec = make_spec(tmp_path, tools=tools, access=gateway)

    assert set(secrets_of(spec)) == {bearer, token}
    for dump in (spec.model_dump, spec.model_dump_json):
        with pytest.raises((TypeError, ValueError), match="refuses"):
            dump()


def test_redaction_masks_each_form_longest_first():
    redact = Redactor([Secret("abc"), Secret("abcdef")])

    assert redact(b"xabcdefx abc") == b"x***x ***"
    assert redact("xabcdefx") == "x***x"


def test_redaction_with_nothing_to_hide_changes_nothing():
    redact = Redactor([Secret("")])

    assert redact(b"anything") == b"anything"
    assert redact("anything") == "anything"
    assert redact.reach == 0


def test_redaction_survives_text_that_is_not_quite_text():
    redact = Redactor([Secret("abc")])

    assert redact("\ud83d abc") == "\ud83d ***"


def test_a_secret_with_specials_is_masked_as_json_carries_it():
    secret = 'qu"ote\\back'
    redact = Redactor([Secret(secret)])

    assert b"***" in redact(json.dumps({"key": secret}).encode())


async def test_the_record_holds_no_more_than_a_pid_and_a_start(tmp_path):
    spec = make_spec(tmp_path, goal="a secret plan", access={"K": Secret("value")})
    done = asyncio.Event()

    async def read(process: Process) -> None:
        assert set(json.loads((spec.folder / RECORD).read_text())) == {"pid", "started"}
        await process.stdout.read()
        done.set()

    process = await Process.launch(["true"], spec, Heard(), read=read)
    await done.wait()
    await process.stop(1)

    assert (spec.folder / LOG).read_bytes() == b""


def test_a_stream_held_for_a_secret_is_never_cut_inside_a_character():
    held = Held(Redactor([Secret("a-secret-of-some-length")]))
    text = "日本語" * 100

    chunks = [held.feed(text[index : index + 7].encode()) for index in range(0, len(text), 7)]

    assert all(chunk.decode() is not None for chunk in chunks)
    assert b"".join(chunks).decode() + held.flush().decode() == text
