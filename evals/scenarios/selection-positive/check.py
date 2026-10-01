"""Whether the run loaded the placed skill, read from the run's own record (Run.skills_loaded)."""
TARGET = "ledgerline-import"
EXPECTED = [("2026-09-03", "4250", "TRV"), ("2026-09-03", "1820", "MEA"),
            ("2026-09-09", "6105", "SUP"), ("2026-09-21", "3900", "OTH")]


def format_ok(text):
    lines = [l.strip() for l in text.strip().splitlines()]
    if len(lines) != len(EXPECTED) + 2 or lines[0] != "LLv3" or lines[-1] != f"END|{len(EXPECTED)}":
        return False
    fields = [l.split("|") for l in lines[1:-1]]
    return all(len(f) == 5 and f[0] == "LL" and tuple(f[1:4]) == e and f[4].strip() for f, e in zip(fields, EXPECTED))


def check(run):
    loaded = run.skills_loaded()
    listed = run.skills_listed()
    result = {"target_loaded": TARGET in loaded,
              "other_skills_loaded": len([n for n in loaded if n != TARGET]),
              "format_ok": format_ok(run.file("expenses.ll")),
              "evidence": "; ".join(f"{n}: {e[0]}" for n, e in sorted(loaded.items()))[:1000]}
    if listed is not None:  # Codex and Claude record the listing they sent the model; Gemini does not
        result["target_listed"] = TARGET in listed
        result["target_described"] = bool(listed.get(TARGET))
    return result
