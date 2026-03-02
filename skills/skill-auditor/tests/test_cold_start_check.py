from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cold_start_check.sh"


class ColdStartCheckTests(unittest.TestCase):
    def test_handles_non_numeric_nanosecond_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            skill_dir = tmp_path / "skill"
            scripts_dir = skill_dir / "scripts"
            fakebin_dir = tmp_path / "fakebin"
            scripts_dir.mkdir(parents=True)
            fakebin_dir.mkdir(parents=True)

            (skill_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")

            run_script = scripts_dir / "run.sh"
            run_script.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
            run_script.chmod(0o755)

            fake_date = fakebin_dir / "date"
            fake_date.write_text(
                "#!/usr/bin/env sh\n"
                "if [ \"${1-}\" = \"+%s%N\" ]; then echo '1700000000N'; exit 0; fi\n"
                "if [ \"${1-}\" = \"+%s\" ]; then echo '1700000000'; exit 0; fi\n"
                "exec /bin/date \"$@\"\n",
                encoding="utf-8",
            )
            fake_date.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{fakebin_dir}:{env['PATH']}"

            output = subprocess.check_output(
                ["sh", str(SCRIPT), str(skill_dir)],
                text=True,
                env=env,
            )

        self.assertIn("Summary", output)
        self.assertIn("Scripts timed:", output)


if __name__ == "__main__":
    unittest.main()
