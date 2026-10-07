from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "-X", "utf8", "-m", "workbench.cli"]


class L01WorkbenchBootstrapAcceptanceTests(unittest.TestCase):
    """Behavior tests for the signed WORKBENCH_SPEC v0.1.2 public CLI seam."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="l01-workbench-test-")
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.project_path = self.root / "project"
        self.project_path.mkdir()
        self.materials = self.root / "materials"
        self.materials.mkdir()
        self.observation_index = 0

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*CLI, *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(
                f"CLI stdout is not JSON: {error}\n"
                f"returncode={result.returncode}\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
            )

    def assert_success(self, result: subprocess.CompletedProcess[str], operation: str) -> dict:
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        payload = self.payload(result)
        self.assertEqual("1.0", payload["schema_version"])
        self.assertTrue(payload["ok"])
        self.assertEqual(operation, payload["operation"])
        return payload

    def assert_failure(
        self,
        result: subprocess.CompletedProcess[str],
        error_code: str,
        returncode: int = 1,
    ) -> dict:
        self.assertEqual(returncode, result.returncode, result.stderr or result.stdout)
        payload = self.payload(result)
        self.assertEqual("1.0", payload["schema_version"])
        self.assertFalse(payload["ok"])
        self.assertEqual(error_code, payload["error_code"])
        self.assertTrue(payload["message"])
        return payload

    def next_observed_at(self) -> str:
        value = datetime(2026, 9, 19, 1, 0, tzinfo=timezone.utc) + timedelta(
            seconds=self.observation_index
        )
        self.observation_index += 1
        return value.isoformat()

    def write_text(self, name: str, content: str) -> Path:
        path = self.materials / name
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, name: str, content: dict) -> Path:
        return self.write_text(name, json.dumps(content, ensure_ascii=False, indent=2))

    def complete_material(self, *, change_control: dict | None = None) -> dict:
        material = {
            "schema_version": "1.0",
            "goal": "让任务从需求到验证可追溯，并能判断缺失证据",
            "in_scope": ["五个 CLI 操作", "本地持久化证据账"],
            "out_of_scope": ["自动调用 Codex", "网页", "FlowERP 修改"],
            "acceptance_criteria": [
                {
                    "id": "AC-L01-EXAMPLE",
                    "expected_effect": "关闭程序后仍能查回任务、快照和运行记录",
                    "verification": "新进程使用 workbench-status 查询同一任务",
                }
            ],
            "business_constraints": ["失败不得伪装成成功"],
            "technical_constraints": ["错误请求不得破坏原记录"],
            "architecture": {
                "applicability": "covered_by_existing",
                "decision": "沿用现有 workbench.cli 接缝",
                "reason": "本任务只补充五个子命令",
            },
            "deployment": {
                "applicability": "covered_by_existing",
                "approach": "沿用课程虚拟环境中的本地 CLI",
                "reason": "不引入新部署方式",
            },
            "end_to_end": {
                "applicability": "required",
                "expected_effect": "从任务创建到查询均通过真实 CLI 完成",
                "reason": "需要验证完整用户路径",
            },
            "reuse": {
                "applicability": "not_applicable",
                "approach": "本任务不承诺新增复用资产",
                "reason": "复用性已评估但不是本次验收目标",
            },
        }
        if change_control is not None:
            material["change_control"] = change_control
        return material

    def initialize(self) -> dict:
        result = self.run_cli(
            "workbench-init",
            "--runtime-dir",
            str(self.runtime),
            "--name",
            "My AI Workbench",
            "--owner",
            "codexfde",
        )
        return self.assert_success(result, "workbench-init")

    def add_project(self, project_id: str = "PERSONAL-WORKBENCH") -> dict:
        result = self.run_cli(
            "workbench-project-add",
            "--runtime-dir",
            str(self.runtime),
            "--project-id",
            project_id,
            "--name",
            "Personal AI Workbench",
            "--path",
            str(self.project_path),
            "--purpose",
            "Track human and Codex delivery evidence",
        )
        return self.assert_success(result, "workbench-project-add")

    def create_task(
        self,
        task_id: str = "TASK-001",
        *,
        request: str = "Build the traceable CLI workbench",
        spec_file: Path | None = None,
        problem_file: Path | None = None,
        related_task_id: str | None = None,
        relation: str | None = None,
        expect_success: bool = True,
    ) -> dict | subprocess.CompletedProcess[str]:
        arguments = [
            "workbench-task-create",
            "--runtime-dir",
            str(self.runtime),
            "--project-id",
            "PERSONAL-WORKBENCH",
            "--task-id",
            task_id,
            "--requirement-id",
            task_id,
            "--request",
            request,
            "--actor",
            "codexfde",
        ]
        if spec_file is not None:
            arguments.extend(["--spec-file", str(spec_file)])
        if problem_file is not None:
            arguments.extend(["--problem-file", str(problem_file)])
        if related_task_id is not None:
            arguments.extend(["--related-task-id", related_task_id])
        if relation is not None:
            arguments.extend(["--relation", relation])
        result = self.run_cli(*arguments)
        if not expect_success:
            return result
        return self.assert_success(result, "workbench-task-create")

    def add_evidence(
        self,
        task_id: str,
        phase: str,
        output_file: Path,
        *,
        command_text: str | None = None,
        returncode: int = 0,
        reviewer: str | None = None,
        decision: str | None = None,
        review_note: str | None = None,
        expect_success: bool = True,
    ) -> dict | subprocess.CompletedProcess[str]:
        arguments = [
            "workbench-evidence-add",
            "--runtime-dir",
            str(self.runtime),
            "--task-id",
            task_id,
            "--phase",
            phase,
            "--command-text",
            command_text or f"record {phase}",
            "--output-file",
            str(output_file),
            "--returncode",
            str(returncode),
            "--observed-at",
            self.next_observed_at(),
        ]
        if reviewer is not None:
            arguments.extend(["--reviewer", reviewer])
        if decision is not None:
            arguments.extend(["--decision", decision])
        if review_note is not None:
            arguments.extend(["--review-note", review_note])
        result = self.run_cli(*arguments)
        if not expect_success:
            return result
        return self.assert_success(result, "workbench-evidence-add")

    def status(
        self,
        *,
        task_id: str | None = None,
        require_red_green: bool = False,
        expect_success: bool = True,
    ) -> dict | subprocess.CompletedProcess[str]:
        arguments = ["workbench-status", "--runtime-dir", str(self.runtime)]
        if task_id is not None:
            arguments.extend(
                ["--require-project", "PERSONAL-WORKBENCH", "--require-task", task_id]
            )
        if require_red_green:
            arguments.append("--require-red-green-evidence")
        result = self.run_cli(*arguments)
        if not expect_success:
            return result
        return self.assert_success(result, "workbench-status")

    def bootstrap_task(self, task_id: str = "TASK-001") -> None:
        self.initialize()
        self.add_project()
        self.create_task(task_id)

    def approve_for_development(self, task_id: str) -> None:
        note = self.write_text(f"{task_id}-review.txt", "reviewed")
        design = self.write_json(f"{task_id}-design.json", self.complete_material())
        self.add_evidence(task_id, "design", design)
        self.add_evidence(
            task_id,
            "design_review",
            note,
            reviewer="designer-1",
            decision="approve",
            review_note="Use the existing CLI architecture",
        )
        spec = self.write_json(f"{task_id}-spec.json", self.complete_material())
        self.add_evidence(task_id, "spec", spec)
        self.add_evidence(
            task_id,
            "spec_review",
            note,
            reviewer="reviewer-1",
            decision="approve",
            review_note="Boundaries and acceptance are explicit",
        )

    def accept_task(self, task_id: str) -> None:
        self.approve_for_development(task_id)
        command = f"verify {task_id}"
        self.add_evidence(
            task_id,
            "red",
            self.write_text(f"{task_id}-red.txt", "failed"),
            command_text=command,
            returncode=1,
        )
        self.add_evidence(
            task_id,
            "diff",
            self.write_text(f"{task_id}-diff.txt", "changed source"),
            command_text="git diff",
        )
        self.add_evidence(
            task_id,
            "green",
            self.write_text(f"{task_id}-green.txt", "passed"),
            command_text=command,
        )
        self.add_evidence(
            task_id,
            "final_review",
            self.write_text(f"{task_id}-final-review.txt", "accepted"),
            reviewer="acceptor-1",
            decision="approve",
            review_note="Accept within the reviewed material and evidence",
        )

    def test_public_cli_registers_exactly_the_five_v01_commands(self):
        """Signed interface seam; guards the five-command scope."""
        result = self.run_cli("-h")
        self.assertEqual(0, result.returncode, result.stderr)
        for command in (
            "workbench-init",
            "workbench-project-add",
            "workbench-task-create",
            "workbench-evidence-add",
            "workbench-status",
        ):
            self.assertIn(command, result.stdout)

    def test_initialization_and_project_survive_new_cli_processes(self):
        """AC-01: success is cross-process retrieval, not the create message alone."""
        initialized = self.initialize()
        self.assertEqual("My AI Workbench", initialized["workbench"]["name"])
        self.assertEqual("codexfde", initialized["workbench"]["owner"])
        project = self.add_project()["project"]
        self.assertEqual("PERSONAL-WORKBENCH", project["project_id"])
        self.assertEqual(str(self.project_path.resolve()), project["path"])

        queried = self.status()
        self.assertEqual("My AI Workbench", queried["workbench"]["name"])
        self.assertEqual("codexfde", queried["workbench"]["owner"])
        self.assertEqual("PERSONAL-WORKBENCH", queried["projects"][0]["project_id"])
        self.assertTrue((self.runtime / "workbench.db").exists())

    def test_task_and_multiple_records_keep_project_and_task_ownership(self):
        """AC-02: project -> task -> ordered records are observable via the CLI."""
        self.bootstrap_task()
        self.approve_for_development("TASK-001")
        first = self.write_text("first.txt", "first observed result")
        second = self.write_text("second.txt", "second observed result")
        self.add_evidence("TASK-001", "red", first, returncode=1)
        self.add_evidence("TASK-001", "green", second, returncode=0)

        queried = self.status(task_id="TASK-001")
        self.assertEqual("PERSONAL-WORKBENCH", queried["task"]["project_id"])
        self.assertEqual("TASK-001", queried["task"]["task_id"])
        runs = [item for item in queried["evidence"] if item["phase"] in {"red", "green"}]
        self.assertEqual(["red", "green"], [item["phase"] for item in runs])
        self.assertEqual([1, 0], [item["returncode"] for item in runs])
        self.assertLess(runs[0]["observed_at"], runs[1]["observed_at"])

    def test_task_keeps_creation_time_spec_and_problem_snapshots(self):
        """AC-03: changing source files cannot rewrite the task's historical basis."""
        self.initialize()
        self.add_project()
        spec = self.write_text("spec.md", "spec version A")
        problem = self.write_text("problem.md", "problem version A")
        self.create_task("TASK-SNAPSHOT", spec_file=spec, problem_file=problem)
        spec.write_text("spec version B", encoding="utf-8")
        problem.write_text("problem version B", encoding="utf-8")

        queried = self.status(task_id="TASK-SNAPSHOT")
        self.assertEqual("spec version A", queried["task"]["spec_snapshot"]["content"])
        self.assertEqual("problem version A", queried["task"]["problem_snapshot"]["content"])
        self.assertNotEqual(
            queried["task"]["spec_snapshot"]["sha256"],
            queried["task"]["problem_snapshot"]["sha256"],
        )

    def test_incomplete_material_lists_acceptance_first_and_only_suggests_questions(self):
        """AC-04, AC-15, AC-18, AC-19: gaps stay gaps; suggestions are not answers."""
        self.bootstrap_task()
        partial = self.write_json(
            "clarification.json",
            {
                "schema_version": "1.0",
                "goal": "Track one requirement",
                "in_scope": ["CLI"],
                "out_of_scope": ["web"],
            },
        )
        self.add_evidence("TASK-001", "clarification", partial)

        first = self.status(task_id="TASK-001")
        self.assertEqual("acceptance_criteria", first["missing_items"][0])
        self.assertTrue(first["clarification_questions"])
        self.assertIn("最终效果", first["clarification_questions"][0])
        self.assertNotIn("acceptance_criteria", first["clarification_questions"])
        self.assertFalse(first["ready_for_development"])
        self.assertFalse(first["verifiable"])
        self.assertNotEqual("accepted", first["acceptance"])

        second = self.status(task_id="TASK-001")
        self.assertEqual(first["missing_items"], second["missing_items"])
        self.assertEqual(1, len(second["evidence"]))
        self.assertEqual("Track one requirement", second["evidence"][0]["material"]["goal"])

    def test_review_gates_precede_development_and_final_review_is_separate(self):
        """AC-05, AC-17, AC-19: design/spec reviews gate work; green is not acceptance."""
        self.bootstrap_task()
        premature_red = self.add_evidence(
            "TASK-001",
            "red",
            self.write_text("premature-red.txt", "failed before approval"),
            returncode=1,
            expect_success=False,
        )
        self.assert_failure(premature_red, "review_gate_missing")
        self.assertEqual([], self.status(task_id="TASK-001")["evidence"])

        design = self.write_json("design.json", self.complete_material())
        note = self.write_text("review.txt", "reviewed")
        self.add_evidence("TASK-001", "design", design)
        self.add_evidence(
            "TASK-001",
            "design_review",
            note,
            reviewer="designer-1",
            decision="approve",
            review_note="Use the existing CLI architecture",
        )

        premature = self.add_evidence(
            "TASK-001",
            "spec_review",
            note,
            reviewer="reviewer-1",
            decision="approve",
            review_note="No signed structured spec exists yet",
            expect_success=False,
        )
        self.assert_failure(premature, "review_gate_missing")

        spec = self.write_json("spec.json", self.complete_material())
        self.add_evidence("TASK-001", "spec", spec)
        self.add_evidence(
            "TASK-001",
            "spec_review",
            note,
            reviewer="reviewer-1",
            decision="approve",
            review_note="Boundaries and acceptance are explicit",
        )
        command = "python -m unittest tests.test_l01_workbench_bootstrap -v"
        self.add_evidence(
            "TASK-001", "red", self.write_text("red.txt", "failed"), command_text=command, returncode=1
        )
        self.add_evidence(
            "TASK-001", "diff", self.write_text("diff.txt", "source diff"), command_text="git diff", returncode=0
        )
        self.add_evidence(
            "TASK-001", "green", self.write_text("green.txt", "passed"), command_text=command, returncode=0
        )

        pending = self.status(task_id="TASK-001", require_red_green=True)
        self.assertTrue(pending["evidence_complete"])
        self.assertEqual("pending_human_review", pending["acceptance"])
        self.add_evidence(
            "TASK-001",
            "final_review",
            note,
            reviewer="acceptor-1",
            decision="approve",
            review_note="Accept within the signed Spec only",
        )
        accepted = self.status(task_id="TASK-001", require_red_green=True)
        self.assertEqual("accepted", accepted["acceptance"])

    def test_duplicate_task_id_is_rejected_without_changing_original_task(self):
        """AC-06: the error response and the persisted post-error state must agree."""
        self.bootstrap_task()
        original = self.write_text("original.txt", "original failure")
        self.add_evidence("TASK-001", "observation", original, returncode=1)
        before = self.status(task_id="TASK-001")
        count_before = self.status()["task_count"]

        duplicate = self.create_task(
            "TASK-001", request="different replacement content", expect_success=False
        )
        self.assert_failure(duplicate, "duplicate_task_id")

        after = self.status(task_id="TASK-001")
        self.assertEqual(before["task"], after["task"])
        self.assertEqual(before["evidence"], after["evidence"])
        self.assertEqual(count_before, self.status()["task_count"])

    def test_bad_evidence_and_missing_query_leave_existing_task_recoverable(self):
        """AC-07, AC-09: failures do not create or damage data; correct query recovers."""
        self.bootstrap_task()
        original = self.write_text("original.txt", "kept")
        self.add_evidence("TASK-001", "observation", original, returncode=1)
        before = self.status(task_id="TASK-001")

        missing_evidence = self.add_evidence(
            "TASK-MISSING", "green", original, expect_success=False
        )
        self.assert_failure(missing_evidence, "task_not_found")
        missing_query = self.status(task_id="TASK-MISSING", expect_success=False)
        self.assert_failure(missing_query, "required_task_missing")

        recovered = self.status(task_id="TASK-001")
        self.assertEqual(before["task"], recovered["task"])
        self.assertEqual(before["evidence"], recovered["evidence"])

    def test_failed_and_passing_observations_both_remain_with_bounded_conclusion(self):
        """AC-08, AC-10: a green observation does not erase red or sign acceptance."""
        self.bootstrap_task()
        self.approve_for_development("TASK-001")
        command = "python -m unittest tests.test_l01_workbench_bootstrap -v"
        self.add_evidence(
            "TASK-001", "red", self.write_text("red.txt", "1 test failed"), command_text=command, returncode=1
        )
        self.add_evidence(
            "TASK-001", "diff", self.write_text("diff.txt", "changed bootstrap.py"), command_text="git diff", returncode=0
        )
        self.add_evidence(
            "TASK-001", "green", self.write_text("green.txt", "1 test passed"), command_text=command, returncode=0
        )

        queried = self.status(task_id="TASK-001", require_red_green=True)
        runs = [item for item in queried["evidence"] if item["phase"] in {"red", "diff", "green"}]
        self.assertEqual(["red", "diff", "green"], [item["phase"] for item in runs])
        self.assertEqual([1, 0, 0], [item["returncode"] for item in runs])
        self.assertTrue(queried["evidence_complete"])
        self.assertEqual("pending_human_review", queried["acceptance"])
        self.assertFalse(queried["all_requirements_proven"])

    def test_child_blocks_parent_but_change_task_does_not_rewrite_parent(self):
        """AC-11, AC-12, AC-13: related tasks are distinct and have different gate semantics."""
        self.initialize()
        self.add_project()
        self.create_task("PARENT")
        self.create_task(
            "CHILD",
            related_task_id="PARENT",
            relation="child_requirement",
            request="Required child scope",
        )
        self.create_task(
            "CHANGE",
            related_task_id="PARENT",
            relation="change_of",
            request="Later boundary change",
        )

        parent = self.status(task_id="PARENT")
        relations = {(item["task_id"], item["relation"]) for item in parent["relations"]}
        self.assertIn(("CHILD", "child_requirement"), relations)
        self.assertIn(("CHANGE", "change_of"), relations)
        self.assertIn("CHILD", parent["acceptance_blockers"])
        self.assertNotIn("CHANGE", parent["acceptance_blockers"])
        self.assertEqual("PARENT", self.status(task_id="CHILD")["task"]["related_task_id"])
        self.assertEqual("PARENT", self.status(task_id="CHANGE")["task"]["related_task_id"])

    def test_applicability_requires_explicit_reason_and_never_guesses_free_text(self):
        """AC-14, AC-15, AC-18, AC-19: blank differs from explicit not-applicable."""
        self.bootstrap_task()
        partial = self.complete_material()
        del partial["deployment"]
        partial["acceptance_criteria"] = []
        partial_file = self.write_json("partial-spec.json", partial)
        self.add_evidence("TASK-001", "spec", partial_file)

        incomplete = self.status(task_id="TASK-001")
        self.assertEqual("acceptance_criteria", incomplete["missing_items"][0])
        self.assertIn("deployment", incomplete["missing_items"])
        self.assertFalse(incomplete["ready_for_development"])

        complete_file = self.write_json("complete-spec.json", self.complete_material())
        self.add_evidence("TASK-001", "spec", complete_file)
        complete = self.status(task_id="TASK-001")
        self.assertNotIn("acceptance_criteria", complete["missing_items"])
        self.assertNotIn("deployment", complete["missing_items"])
        latest = [item for item in complete["evidence"] if item["phase"] == "spec"][-1]
        self.assertEqual("covered_by_existing", latest["material"]["deployment"]["applicability"])
        self.assertTrue(latest["material"]["deployment"]["reason"])

    def test_change_task_cannot_pass_spec_review_without_complete_change_control(self):
        """AC-16: intentional constraint changes require explicit change-control fields."""
        self.initialize()
        self.add_project()
        self.create_task("ORIGINAL")
        self.create_task(
            "CHANGE",
            related_task_id="ORIGINAL",
            relation="change_of",
            request="Intentionally replace a technical constraint",
        )
        note = self.write_text("review.txt", "review")
        design = self.write_json("change-design.json", self.complete_material())
        self.add_evidence("CHANGE", "design", design)
        self.add_evidence(
            "CHANGE",
            "design_review",
            note,
            reviewer="designer-1",
            decision="approve",
            review_note="Keep the existing CLI architecture and review the constraint change separately",
        )
        incomplete_spec = self.write_json("change-incomplete.json", self.complete_material())
        self.add_evidence("CHANGE", "spec", incomplete_spec)
        rejected = self.add_evidence(
            "CHANGE",
            "spec_review",
            note,
            reviewer="reviewer-1",
            decision="approve",
            review_note="change control is absent",
            expect_success=False,
        )
        failure = self.assert_failure(rejected, "spec_incomplete")
        self.assertEqual("change_control", failure["missing_items"][0])
        self.assertFalse(self.status(task_id="CHANGE")["ready_for_development"])

        change_control = {
            "changed_constraints": ["old technical limit"],
            "impact_scope": ["CLI consumers"],
            "alternative": "keep compatibility through a versioned response",
            "migration_or_recovery": "retain the old database and provide rollback",
            "new_acceptance_criteria": ["AC-CHANGE-01"],
        }
        complete_spec = self.write_json(
            "change-complete.json", self.complete_material(change_control=change_control)
        )
        self.add_evidence("CHANGE", "spec", complete_spec)
        self.add_evidence(
            "CHANGE",
            "spec_review",
            note,
            reviewer="reviewer-1",
            decision="approve",
            review_note="change impact and recovery are explicit",
        )
        self.assertTrue(self.status(task_id="CHANGE")["ready_for_development"])

    def test_invalid_structured_material_is_rejected_without_partial_record(self):
        """AC-07, AC-19: invalid JSON fails atomically and leaves prior records intact."""
        self.bootstrap_task()
        bad = self.write_text("bad.json", "{not valid json")
        rejected = self.add_evidence("TASK-001", "spec", bad, expect_success=False)
        self.assert_failure(rejected, "structured_material_invalid")
        queried = self.status(task_id="TASK-001")
        self.assertEqual([], queried["evidence"])
        self.assertIn("acceptance_criteria", queried["missing_items"])

    def test_reviews_bind_latest_material_and_stale_approval_cannot_unlock_work(self):
        """AC-17: every approval names its object and only the latest material is approved."""
        self.bootstrap_task()
        note = self.write_text("review-object.txt", "reviewed")
        first_design = self.write_json("design-v1.json", self.complete_material())
        self.add_evidence("TASK-001", "design", first_design)
        first_review = self.add_evidence(
            "TASK-001",
            "design_review",
            note,
            reviewer="designer-1",
            decision="approve",
            review_note="approve design v1",
        )["evidence"]
        self.assertEqual("design", first_review["review_target"]["phase"])

        revised = self.complete_material()
        revised["goal"] = "revised design goal"
        second_design = self.write_json("design-v2.json", revised)
        second_design_record = self.add_evidence("TASK-001", "design", second_design)["evidence"]
        spec = self.write_json("reviewed-spec.json", self.complete_material())
        self.add_evidence("TASK-001", "spec", spec)
        stale = self.add_evidence(
            "TASK-001",
            "spec_review",
            note,
            reviewer="reviewer-1",
            decision="approve",
            review_note="stale design review must not count",
            expect_success=False,
        )
        self.assert_failure(stale, "review_gate_missing")

        current_design_review = self.add_evidence(
            "TASK-001",
            "design_review",
            note,
            reviewer="designer-1",
            decision="approve",
            review_note="approve design v2",
        )["evidence"]
        self.assertEqual(
            second_design_record["evidence_id"],
            current_design_review["review_target"]["evidence_id"],
        )
        first_spec_review = self.add_evidence(
            "TASK-001",
            "spec_review",
            note,
            reviewer="reviewer-1",
            decision="approve",
            review_note="approve spec v1",
        )["evidence"]
        self.assertEqual("spec", first_spec_review["review_target"]["phase"])
        self.assertTrue(self.status(task_id="TASK-001")["ready_for_development"])

        revised_spec = self.complete_material()
        revised_spec["goal"] = "revised spec goal"
        self.add_evidence("TASK-001", "spec", self.write_json("spec-v2.json", revised_spec))
        self.assertFalse(self.status(task_id="TASK-001")["ready_for_development"])
        blocked = self.add_evidence(
            "TASK-001",
            "green",
            self.write_text("blocked-green.txt", "must not be saved"),
            expect_success=False,
        )
        self.assert_failure(blocked, "review_gate_missing")

    def test_non_review_record_rejects_review_fields_without_partial_write(self):
        """AC-07, AC-17: ordinary evidence cannot impersonate a named review."""
        self.bootstrap_task()
        output = self.write_text("ordinary.txt", "ordinary observation")
        rejected = self.add_evidence(
            "TASK-001",
            "observation",
            output,
            reviewer="fake-reviewer",
            decision="approve",
            review_note="must not be stored",
            expect_success=False,
        )
        self.assert_failure(rejected, "review_fields_not_allowed")
        self.assertEqual([], self.status(task_id="TASK-001")["evidence"])

    def test_invalid_nonempty_acceptance_is_not_verifiable(self):
        """AC-18, AC-19: malformed acceptance content remains a highest-risk gap."""
        self.bootstrap_task()
        invalid = self.complete_material()
        invalid["acceptance_criteria"] = [{"id": "AC-BROKEN", "expected_effect": ""}]
        self.add_evidence("TASK-001", "clarification", self.write_json("invalid-ac.json", invalid))
        queried = self.status(task_id="TASK-001")
        self.assertEqual("acceptance_criteria", queried["missing_items"][0])
        self.assertFalse(queried["verifiable"])
        self.assertIn("最终效果", queried["clarification_questions"][0])

    def test_nested_or_rejected_child_still_blocks_parent_acceptance(self):
        """AC-13: child acceptance is recursive and follows the latest final decision."""
        self.initialize()
        self.add_project()
        self.create_task("PARENT")
        self.create_task("CHILD", related_task_id="PARENT", relation="child_requirement")
        self.create_task("GRANDCHILD", related_task_id="CHILD", relation="child_requirement")
        self.accept_task("PARENT")
        self.accept_task("CHILD")

        parent = self.status(task_id="PARENT")
        self.assertIn("CHILD", parent["acceptance_blockers"])
        self.assertEqual("pending_human_review", parent["acceptance"])

        self.accept_task("GRANDCHILD")
        accepted_parent = self.status(task_id="PARENT")
        self.assertNotIn("CHILD", accepted_parent["acceptance_blockers"])
        self.assertEqual("accepted", accepted_parent["acceptance"])

        self.add_evidence(
            "GRANDCHILD",
            "final_review",
            self.write_text("grandchild-reject.txt", "rejected after review"),
            reviewer="acceptor-2",
            decision="reject",
            review_note="latest decision rejects the child",
        )
        rejected_parent = self.status(task_id="PARENT")
        self.assertIn("CHILD", rejected_parent["acceptance_blockers"])
        self.assertEqual("pending_human_review", rejected_parent["acceptance"])

    def test_final_review_target_must_belong_to_valid_red_diff_green_chain(self):
        """AC-08, AC-17: final approval cannot borrow an older verification chain."""
        self.bootstrap_task()
        self.accept_task("TASK-001")
        self.assertEqual("accepted", self.status(task_id="TASK-001")["acceptance"])

        unrelated_green = self.write_text("unrelated-green.txt", "a different command passed")
        self.add_evidence(
            "TASK-001",
            "green",
            unrelated_green,
            command_text="verify something else",
        )
        self.assertEqual("pending_human_review", self.status(task_id="TASK-001")["acceptance"])

        rejected = self.add_evidence(
            "TASK-001",
            "final_review",
            self.write_text("invalid-final-review.txt", "must not approve unrelated green"),
            reviewer="acceptor-2",
            decision="approve",
            review_note="latest green is not part of the valid chain",
            expect_success=False,
        )
        self.assert_failure(rejected, "review_gate_missing")
        queried = self.status(task_id="TASK-001")
        self.assertEqual("pending_human_review", queried["acceptance"])
        self.assertEqual("green", queried["evidence"][-1]["phase"])


if __name__ == "__main__":
    unittest.main()
