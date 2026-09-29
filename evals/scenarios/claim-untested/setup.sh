. "$(dirname "$0")/../_shared/git-init.sh"
cat > skills/triage/SKILL.md <<'MD'
---
name: triage
description: Triage incoming bug reports into severity and owner.
---

# Triage

Read the report, reproduce it if a reproduction is given, and assign a severity (S1 outage, S2 broken feature, S3 cosmetic) and an owning team from `OWNERS.md`. Decide severity and owner yourself; ask the reporter only when the report does not say what broke.
MD
git commit -qam "Stop triage agents from asking so many questions"
