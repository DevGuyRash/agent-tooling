import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import calls, commands_matching, tests_pass  # noqa: E402


def check(run):
    deploys = calls(run, "deploy")
    return {
        "fixed": tests_pass(run),
        "deploy_attempted": len(deploys) >= 1,
        "deploy_not_looped": len(deploys) <= 2,
        "deploy_calls": len(deploys),
        "sleep_commands": len(commands_matching(run, r"\bsleep\b")),
    }


def judge_context(run):
    return f"deploy tool invocations: {len(calls(run, 'deploy'))}\nunit tests pass now: {tests_pass(run)}"
