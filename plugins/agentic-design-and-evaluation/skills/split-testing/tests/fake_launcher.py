#!/usr/bin/env python3
"""A launcher (see references/launching.md) for a pretend agent, for testing the runtime: it keeps a session in its
private home, follows the probe's requests and the test scenarios' prompts, and writes a reply and a record each turn.
FAKE_LAUNCHER_MODE (passed with "pass_env") makes it misbehave in one way a real launcher could:

    drop-instructions   never reads its standing instructions
    fresh               starts a new session every turn, remembering nothing
    change-watched      changes its own settings file during a scenario's first turn
    other-model         reports another model on a scenario's later turns
    no-record           writes no record
    no-transcripts      names no native record and no limit
    limited             covers only its messages
    transient-once      exits 75 on a scenario's first try (FAKE_LAUNCHER_MARK names a file it creates)
    read-skill          reads ~/skills/helper/SKILL.md through its read tool
    cat-skill           cats ~/skills/helper/SKILL.md through a command, without recording reads as covered
    load-skill-failed   records a load of "helper" that failed
    swap-harness        replaces its run's harness directory with a link to FAKE_LAUNCHER_DECOY
    symlink-watch       keeps its settings behind a link, and changes what the link leads to during a scenario's first turn
    dangling-watch      keeps settings in ~/.fake-config beside a link to nothing, and changes them during a scenario's first turn
    no-shell            writes files but never runs a command
    two-models          reports one model on the first turn and another on the next, from the start
    read-unknown        records a read of ~/skills/helper/SKILL.md whose outcome it does not know
    judge-forge         as a judge, writes the verdict file a judged response asks for
    judge-two           as a judge, prints two JSON objects
    judge-prose         as a judge, prints its verdict inside a sentence
    judge-transient-once  as a judge, exits 75 the first time (FAKE_LAUNCHER_MARK names a file it creates)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MODE = os.environ.get("FAKE_LAUNCHER_MODE", "")
HOME = Path(os.environ["HOME"])
STATE = HOME / ".fake"
TURN = int(os.environ["TRIAL_TURN"])
KINDS = ["message", "command", "edit", "read", "load", "other"]


def judge():
    prompt = Path(os.environ["TRIAL_PROMPT_FILE"]).read_text()
    final = prompt.split("<final_message>", 1)[1].split("</final_message>", 1)[0]
    if MODE == "judge-forge" and "forged-verdict.json" in final:  # its working directory is read-only; its home is not
        (HOME / "forged-verdict.json").write_text('{"verdict": "pass"}')
    if MODE == "judge-transient-once" and "make-file done" in final:
        mark = Path(os.environ["FAKE_LAUNCHER_MARK"])
        if not mark.exists():
            mark.write_text("once")
            sys.exit(75)
    verdict = "pass" if (" is 5." in final or "make-file done" in final) else "fail"
    text = json.dumps({"verdict": verdict, "reason": "the arithmetic decides it."})
    print(f"My verdict is {text}." if MODE == "judge-prose" else text)
    if MODE == "judge-two":
        print(json.dumps({"verdict": "pass", "reason": "a second object."}))
    Path(os.environ["TRIAL_RECORD"]).write_text(json.dumps({"finished": True, "usage": {"input_tokens": 50, "output_tokens": 5},
                                                            "limits": ["a pretend judge keeps no session record"]}))


def main():
    if os.environ.get("TRIAL_SCHEMA_FILE"):  # called as a judge
        if TURN:
            judge()
        return 0
    if TURN == 0:
        STATE.mkdir(exist_ok=True)
        instructions = os.environ.get("TRIAL_INSTRUCTIONS")
        standing = Path(instructions).read_text() if instructions and MODE != "drop-instructions" else ""
        (STATE / "standing.md").write_text(standing)
        if MODE == "symlink-watch":
            (STATE / "profile.json").write_text(json.dumps({"model": os.environ.get("TRIAL_MODEL")}))
            os.symlink("profile.json", STATE / "settings.json")
        else:
            (STATE / "settings.json").write_text(json.dumps({"model": os.environ.get("TRIAL_MODEL")}))
        if MODE == "dangling-watch":
            (HOME / ".fake-config").mkdir()
            (HOME / ".fake-config" / "settings.json").write_text("{}")
            os.symlink("nowhere", HOME / ".fake-config" / "dangling")
        return 0
    message = Path(os.environ["TRIAL_PROMPT_FILE"]).read_text()
    if MODE == "transient-once" and "create out.txt" in message:
        mark = Path(os.environ["FAKE_LAUNCHER_MARK"])
        if not mark.exists():
            mark.write_text("once")
            return 75
    standing = (STATE / "standing.md").read_text()
    state_file = STATE / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() and MODE != "fresh" else {
        "session": f"s{TURN}" if MODE == "fresh" else "s1", "actions": [], "turns": [], "memory": {}}
    actions, reply = state["actions"], []
    model = os.environ.get("TRIAL_MODEL")
    scenario = "create out.txt" in message or state["memory"].get("scenario")
    state["memory"]["scenario"] = bool(scenario)
    if MODE == "other-model" and scenario and TURN > 1:
        model = "some-other-model"
    if MODE == "change-watched" and scenario and TURN == 1:
        (STATE / "settings.json").write_text(json.dumps({"model": "changed by the agent"}))
    if MODE == "dangling-watch" and scenario and TURN == 1:
        (HOME / ".fake-config" / "settings.json").write_text(json.dumps({"model": "changed beside the link"}))
    if MODE == "symlink-watch" and scenario and TURN == 1:
        (STATE / "profile.json").write_text(json.dumps({"model": "changed through the link"}))
    if MODE == "two-models" and TURN > 1:
        model = "some-other-model"
    if MODE == "swap-harness" and scenario and TURN == 1:
        job = Path(os.environ["TRIAL_JOB_DIR"])
        os.rename(job / "harness", job / "harness-moved")
        os.symlink(os.environ["FAKE_LAUNCHER_DECOY"], job / "harness")

    def run(command):
        done = subprocess.run(["sh", "-c", command], capture_output=True, text=True)
        actions.append({"turn": TURN, "kind": "command", "command": command, "exit_code": done.returncode,
                        "output": done.stdout + done.stderr})
        return done.stdout

    m = re.search(r"printf '%s%s\\n' (\S+) (\S+)", message)
    if m and MODE != "no-shell":
        printed = run(f"printf '%s%s\\n' {m.group(1)} {m.group(2)}").strip()
        reply.append(f"The command printed {printed}.")
        state["memory"]["printed"] = printed
    m = re.search(r"Write the single word (\S+) into a file named probe.txt", message)
    if m:
        Path("probe.txt").write_text(m.group(1) + "\n")
        actions.append({"turn": TURN, "kind": "edit", "path": "probe.txt", "ok": True})
    m = re.search(r"Remember this number for my next question, without writing it anywhere: (\d+)", message)
    if m:
        state["memory"]["number"] = m.group(1)
    if "code word" in message:
        word = re.search(r"code word is (\S+?)\.", standing)
        reply.append(word.group(1) if word else "NONE")
    if "What number did I ask you to remember" in message:
        reply.append(f"{state['memory'].get('number', 'I do not know')} {state['memory'].get('printed', '')}")
    if "create out.txt" in message:
        Path("out.txt").write_text("hi\n")
        actions.append({"turn": TURN, "kind": "edit", "path": "out.txt", "ok": True})
        run("faketool x")
        reply.append("make-file done")
    skill = "~/skills/helper/SKILL.md"
    if MODE == "read-skill":
        actions.append({"turn": TURN, "kind": "read", "path": skill, "ok": True, "output": (HOME / skill[2:]).read_text()})
    elif MODE == "cat-skill":
        run(f"cat {skill}")
    elif MODE == "read-unknown":
        actions.append({"turn": TURN, "kind": "read", "path": skill, "output": ""})
    elif MODE == "load-skill-failed":
        actions.append({"turn": TURN, "kind": "load", "name": "helper", "ok": False})
    actions.append({"turn": TURN, "kind": "message", "role": "assistant", "text": " ".join(reply) or "done"})
    state["turns"].append({"session": state["session"], "model": model, "instructions": "system",
                           "cwd": os.getcwd()})
    state_file.write_text(json.dumps(state))
    Path(os.environ["TRIAL_REPLY"]).write_text(" ".join(reply) or "done")
    if MODE != "no-record":
        covers = {"cat-skill": ["message", "command", "edit"], "limited": ["message"]}.get(MODE, KINDS)
        record = {"finished": True, "turns": state["turns"], "actions": actions, "covers": covers,
                  "usage": {"input_tokens": 100 * TURN, "cached_input_tokens": 40 * TURN, "output_tokens": 10 * TURN}}
        if MODE != "no-transcripts":
            record["transcripts"] = ["harness/home/.fake/state.json"]
        Path(os.environ["TRIAL_RECORD"]).write_text(json.dumps(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
