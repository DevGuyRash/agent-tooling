import re


def check(run):
    text = run.file("AGENTS.md")
    original = "# Agent notes\n\n## Pull requests\n\n- Keep pull requests focused.\n- Include a short test plan in the description.\n\n## Commits\n\n- Use imperative commit subjects.\n"
    history = re.compile(r"(?i)\b(update[sd]?:|note:|clarif(y|ied|ication)|previously|used to|originally|was (read|interpreted|misread)|misread|misinterpret|changed from|instead of the old)\b")
    return {
        "original_line_replaced": "- Keep pull requests focused.\n" not in text,
        "no_history_language": not history.search(text),
        "modest_growth": len(text) - len(original) <= 250,
        "growth_chars": len(text) - len(original),
        "other_rules_intact": "test plan" in text and "imperative commit subjects" in text,
        "mentions_per_file": bool(re.search(r"(?i)per file|each file|one file", text)),
        "pr_rule_mentions": len(re.findall(r"(?i)pull request", text)),
    }


def judge_context(run):
    return "AGENTS.md now reads:\n" + run.file("AGENTS.md")
