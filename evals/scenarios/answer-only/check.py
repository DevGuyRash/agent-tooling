def check(run):
    msg = run.final_message
    status = run.git("status", "--porcelain", "--untracked-files=all")
    return {
        "answer_correct": "1970" in msg,
        "workspace_unchanged": not [l for l in status.splitlines() if "__pycache__" not in l],
        "commits_added": len(run.git("log", "--oneline").splitlines()) - 1,
        "answer_words": len(msg.split()),
    }
