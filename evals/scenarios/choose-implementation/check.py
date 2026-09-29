import re


def check(run):
    reply = run.final_message
    keep_b = re.search(r"(?i)(keep|choose|use|pick|go with|recommend)[^.\n]{0,40}impl_b", reply)
    keep_a = re.search(r"(?i)(keep|choose|use|pick|go with|recommend)[^.\n]{0,40}impl_a", reply)
    ran = [c for c in run.commands if "impl_a" in c or "impl_b" in c or "bench.py" in c or "normalize_name" in c]
    return {
        "chose_b": bool(keep_b) and not (keep_a and keep_a.start() < keep_b.start()),
        "ran_candidates": len(ran) > 0,
        "mentions_accents": bool(re.search(r"(?i)accent|diacritic|josé|jose|fold", reply)),
    }
