from __future__ import annotations

import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reference_check.sh"

def run_reference_check(skill_dir: Path, *extra: str, cwd: Path | None = None) -> tuple[subprocess.CompletedProcess[str], dict]:
    completed = subprocess.run(
        ["sh", str(SCRIPT), str(skill_dir), "--format", "json", *extra],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    return completed, json.loads(completed.stdout)


def make_skill(
    tmp: str,
    *,
    slug: str = "demo-skill",
    name: str = "Demo Skill",
    description: str = "Check demo skills and explain findings for maintainers updating metadata and packaging boundaries.",
    body: str = "\n# Demo Skill\n",
    scripts: dict[str, str] | None = None,
    extra_files: dict[str, str] | None = None,
    references: dict[str, str] | None = None,
) -> Path:
    skill_dir = Path(tmp) / slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    skill_md = f"---\nname: {name}\ndescription: >-\n  {description}\n---\n{body}"
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    if scripts:
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        for fname, content in scripts.items():
            script_file = scripts_dir / fname
            script_file.write_text(content, encoding="utf-8")
            if fname.endswith(".sh"):
                script_file.chmod(script_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if references:
        ref_dir = skill_dir / "references"
        ref_dir.mkdir(exist_ok=True)
        for fname, content in references.items():
            (ref_dir / fname).write_text(content, encoding="utf-8")

    if extra_files:
        for fpath, content in extra_files.items():
            full = skill_dir / fpath
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

    return skill_dir


class ErrorTests(unittest.TestCase):
    """missing_reference_file: a link with no file behind it is broken for every
    target, so it must fail the run."""

    def test_missing_reference_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp, body="\n- Packaging fit -> `references/nope.md`\n"
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(data["error_count"], 1)
        self.assertIn("missing_reference_file", {e["code"] for e in data["errors"]})

    def test_a_target_with_an_error_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp, body="\n- Packaging fit -> `references/nope.md`\n"
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 1)
        self.assertGreater(data["error_count"], 0)


class ObservationTests(unittest.TestCase):
    """Each fact's significance depends on the target, so each must be reported
    without failing the run."""

    def test_relative_reference_path_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                references={"packaging-fit.md": "# Packaging\n"},
                body="\n- Packaging fit -> `references/packaging-fit.md`\n",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(data["observations"], [])

    def test_host_prefixed_reference_path_is_resolved_and_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                references={"packaging-fit.md": "# Packaging\n"},
                body="\n- Packaging fit -> `<skills-file-root>/references/packaging-fit.md`\n",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(
            {item["code"] for item in data["observations"]},
            {"nonportable_reference_prefix"},
        )

    def test_flags_unlinked_active_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                references={
                    "packaging-fit.md": "# Packaging\n",
                    "trigger-evals.md": "# Trigger\n",
                },
                body="\n- Packaging fit -> `references/packaging-fit.md`\n",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        codes = {o["code"] for o in data["observations"]}
        self.assertEqual(codes, {"unlinked_reference"})
        subjects = {o["subject"] for o in data["observations"]}
        self.assertIn("references/trigger-evals.md", subjects)

    def test_recurses_into_nested_reference_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                references={"packaging-fit.md": "# Packaging\n"},
                body="\n- Packaging fit -> `references/packaging-fit.md`\n",
            )
            nested_dir = skill_dir / "references" / "aws"
            nested_dir.mkdir(parents=True)
            (nested_dir / "setup.md").write_text("# Setup\n", encoding="utf-8")

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        codes = {o["code"] for o in data["observations"]}
        self.assertIn("unlinked_reference", codes)
        subjects = {o["subject"] for o in data["observations"]}
        self.assertIn("references/aws/setup.md", subjects)

    def test_flags_nested_reference_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                references={
                    "packaging-fit.md": "See [Trigger](trigger-evals.md) for more.\n",
                    "trigger-evals.md": "# Trigger\n",
                },
                body=(
                    "\n- Packaging fit -> `references/packaging-fit.md`\n"
                    "- Trigger fit -> `references/trigger-evals.md`\n"
                ),
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        codes = {o["code"] for o in data["observations"]}
        self.assertEqual(codes, {"nested_reference_link"})

class HardWrapTests(unittest.TestCase):
    def test_results_are_identical_whether_or_not_clauses_are_hard_wrapped(self) -> None:
        long_line_body = (
            "\n- Packaging fit, covering manifest shape, capability declarations, and marketplace "
            "metadata for reviewers auditing plugin boundaries in depth -> "
            "`references/packaging-fit.md`\n"
        )
        wrapped_body = (
            "\n- Packaging fit, covering manifest shape, capability declarations, and\n"
            "  marketplace metadata for reviewers auditing plugin boundaries in depth ->\n"
            "  `references/packaging-fit.md`\n"
        )

        results = []
        for body in (long_line_body, wrapped_body):
            with tempfile.TemporaryDirectory() as tmp:
                skill_dir = make_skill(
                    tmp, references={"packaging-fit.md": "# Packaging\n"}, body=body
                )
                completed, data = run_reference_check(skill_dir)
                self.assertEqual(completed.returncode, 0)
                results.append(
                    (
                        data["linked_references"],
                        data["active_references"],
                        data["error_count"],
                        data["observation_count"],
                        sorted(e["code"] for e in data["errors"]),
                        sorted(o["code"] for o in data["observations"]),
                    )
                )

        self.assertEqual(results[0], results[1])


class CleanTargetTests(unittest.TestCase):
    def test_fully_clean_skill_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                references={"packaging-fit.md": "# Packaging\n"},
                body="\n- Packaging fit -> `references/packaging-fit.md`\n",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(data["observation_count"], 0)
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["observations"], [])

    def test_active_skill_passes(self) -> None:
        completed, data = run_reference_check(ROOT)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)


class ObservationsOnlyExitTests(unittest.TestCase):
    def test_a_target_whose_only_findings_are_observations_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                references={
                    "packaging-fit.md": "# Packaging\n",
                    "trigger-evals.md": "# Trigger\n",
                },
                body="\n- Packaging fit -> `references/packaging-fit.md`\n",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(data["error_count"], 0)
        self.assertGreater(data["observation_count"], 0)


class SourceTagTests(unittest.TestCase):
    def test_reference_graph_observations_point_to_the_skill_kernel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(
                tmp,
                references={
                    "packaging-fit.md": "# Packaging\n",
                    "trigger-evals.md": "# Trigger\n",
                },
                body="\n- Packaging fit -> `references/packaging-fit.md`\n",
            )

            completed, data = run_reference_check(skill_dir)

        self.assertGreater(data["observation_count"], 0)
        for obs in data["observations"]:
            if "source" in obs:
                self.assertEqual(obs["source"], "SKILL.md")

class UsageExitTests(unittest.TestCase):
    def test_unusable_input_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = make_skill(tmp)

            bad_flag = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir), "--nope"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(bad_flag.returncode, 2)

            bad_format = subprocess.run(
                ["sh", str(SCRIPT), str(skill_dir), "--format", "xml"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(bad_format.returncode, 2)
            self.assertIn("hint:", bad_format.stderr)

            empty_dir = Path(tmp) / "empty-dir"
            empty_dir.mkdir()
            missing_skill_md = subprocess.run(
                ["sh", str(SCRIPT), str(empty_dir)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(missing_skill_md.returncode, 2)

        missing_dir = subprocess.run(
            ["sh", str(SCRIPT), "/tmp/definitely-not-a-real-skill-dir-xyz"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(missing_dir.returncode, 2)


class DeclaredPathTests(unittest.TestCase):
    def test_filename_mention_is_not_a_declared_relative_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(tmp, body="[Guide](references/guide.md)\n", references={
                "guide.md": "A skill contains `SKILL.md` followed by resources.\n",
            })
            proc, data = run_reference_check(skill)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertEqual(data["errors"], [])

    def test_complete_sibling_path_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sibling = root / "foundation" / "references"
            sibling.mkdir(parents=True)
            (sibling / "source.md").write_text("# Original source\n")
            skill = make_skill(tmp, references={"local.md": "# Local\n"}, body=(
                "[Local](references/local.md)\n"
                "[Shared](../foundation/references/source.md#original-source)\n"
            ))
            unrelated = root / "unrelated"
            unrelated.mkdir()
            proc, data = run_reference_check(skill, cwd=unrelated)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertEqual(data["linked_references"], 2)
            self.assertEqual(data["errors"], [])

    def test_missing_sibling_keeps_declared_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(tmp, body="[Shared](../foundation/references/missing.md)\n")
            proc, data = run_reference_check(skill)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(data["errors"][0]["subject"], "../foundation/references/missing.md")

    def test_reference_links_resolve_from_declaring_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(tmp, body="[Guide](references/guide.md)\n", references={
                "guide.md": "[Present](detail.md)\n[Missing](absent.md)\n",
                "detail.md": "# Detail\n",
            })
            proc, data = run_reference_check(skill)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(len(data["errors"]), 1)
            self.assertEqual(data["errors"][0]["subject"], "references/guide.md: absent.md")

    def test_examples_and_dynamic_paths_are_not_missing_literal_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(tmp, body=(
                "```markdown\n[Example](references/not-real.md)\n```\n"
                "> [Quoted](references/quoted.md)\n"
                "`references/${mode}.md`\n"
                "[Remote](https://example.test/references/remote.md)\n"
            ))
            proc, data = run_reference_check(skill)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertEqual(data["errors"], [])
            self.assertEqual(len(data["observations"]), 3)
            self.assertEqual({o["code"] for o in data["observations"]}, {"unverified_reference"})

    def test_repeat_is_identical_and_target_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = make_skill(tmp, body="[Source](references/source.md)\n", references={"source.md":"# Source\n"})
            before = {str(p.relative_to(skill)):p.read_bytes() for p in skill.rglob('*') if p.is_file()}
            first, _ = run_reference_check(skill)
            second, _ = run_reference_check(skill)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(before, {str(p.relative_to(skill)):p.read_bytes() for p in skill.rglob('*') if p.is_file()})

if __name__ == "__main__":
    unittest.main()
