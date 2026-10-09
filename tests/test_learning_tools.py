"""Black-box acceptance tests for the local learning CLI.

Every command runs in a fresh process, so restoration, idempotency, and
Markdown protection are tested through the same interface used by the tutor.
Only temporary learning roots are mutated.
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
CLI = PROJECT / "plugins" / "ai-learning-companion" / "scripts" / "learning_tools.py"


class LearningToolsAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="learning-tools-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input_number = 0
        self.run_cli(
            "topic-init", "--id", "test", "--title", "局部推理学习测试",
            "--mission", "独立解释并使用知识点解决真实问题",
            "--success", "能够完成一道不依赖提示的新题",
        )

    def run_cli(self, *arguments, success=True, expected_code=None):
        result = subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *arguments],
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        description = " ".join(arguments)
        if success:
            self.assertEqual(
                result.returncode, 0,
                f"{description}\nstdout: {result.stdout}\nstderr: {result.stderr}",
            )
        else:
            self.assertNotEqual(result.returncode, 0, description)
        if expected_code is not None:
            self.assertEqual(result.returncode, expected_code, description)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            self.fail(f"{description} did not return JSON: {result.stdout!r}")

    def input_json(self, value):
        self.input_number += 1
        path = self.root / f"input-{self.input_number}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def status(self):
        return self.run_cli("status", "--topic", "test")

    @property
    def workspace(self):
        return self.root / "学习笔记库" / "主题" / "test"

    def choice_spec(self, quiz_id="q1", concept="c1", phase="diagnostic"):
        return {
            "id": quiz_id, "kind": "choice", "phase": phase,
            "concept_id": concept, "question": f"{quiz_id}：哪项推理成立？",
            "options": [
                {"id": "valid", "text": "能够由已给条件推出"},
                {"id": "invalid", "text": "忽略一个必要条件"},
                {"id": "unrelated", "text": "只重复目标结论"},
            ],
            "correct": ["valid"],
            "explanation": "PRIVATE_EXPLANATION_唯一解析标识",
            "source_refs": ["https://example.com/source"], "shuffle": True,
        }

    def create_quiz(self, spec=None):
        return self.run_cli(
            "quiz-create", "--topic", "test", "--file",
            self.input_json(spec or self.choice_spec()),
        )

    def submit(self, quiz="q1", attempt="a1", answer=None, success=True):
        return self.run_cli(
            "quiz-submit", "--topic", "test", "--quiz", quiz,
            "--attempt", attempt, "--answer",
            json.dumps(answer or {"selection": ["valid"]}, ensure_ascii=False),
            success=success,
        )

    def set_route(self, nodes=None, edges=None, success=True):
        if nodes is None:
            nodes = [
                {"id": f"c{number}", "label": f"概念{number}",
                 "status": "unknown", "source_refs": [], "evidence_refs": []}
                for number in range(1, 7)
            ]
        return self.run_cli(
            "route-set", "--topic", "test", "--file",
            self.input_json({"nodes": nodes, "edges": edges or []}),
            success=success,
        )

    def correct_diagnostic_answer(self, number):
        self.create_quiz(self.choice_spec(f"q{number}", f"c{number}"))
        result = self.submit(f"q{number}", f"a{number}")
        self.assertEqual(result["result"]["outcome"], "correct")

    def record(self, evidence_refs=None, kind="demonstrated", success=True):
        spec = {
            "title": "能由前提推出结论", "summary": "可独立应用，后续无需重教。",
            "kind": kind, "evidence_refs": evidence_refs or [],
            "evidence": "用户在不查看答案时独立作答。",
            "implications": "进入下一个必要步骤", "supersedes": None,
        }
        return self.run_cli(
            "record-learning", "--topic", "test", "--file",
            self.input_json(spec), success=success,
        )

    def snapshot(self):
        """Capture actual persistent bytes to detect unintended mutations."""
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }

    @staticmethod
    def sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_six_correct_answers_unlock_teaching_and_resume_without_reprobe(self):
        self.run_cli(
            "checkpoint", "--topic", "test", "--phase", "teaching",
            "--node", "c1", success=False,
        )
        for number in range(1, 7):
            self.correct_diagnostic_answer(number)
        self.run_cli("diagnosis-finish", "--topic", "test")
        self.set_route()
        self.run_cli(
            "checkpoint", "--topic", "test", "--phase", "teaching",
            "--node", "c1",
        )
        first = self.status()
        resumed = self.status()
        self.assertEqual(resumed["phase"], "teaching")
        self.assertEqual(resumed["mode"], "continue")
        self.assertEqual(resumed["current_node"], "c1")
        self.assertEqual(resumed["diagnosis"], first["diagnosis"])
        self.assertEqual(resumed["diagnosis"]["answered"], 6)
        self.assertTrue(resumed["diagnosis"]["finished"])
        for frontier in resumed["diagnosis"]["frontier"].values():
            self.assertIn("上界未定位", frontier["summary"])
        self.assertIsNone(resumed["pending_quiz"])

    def test_six_question_budget_prevents_infinite_diagnostic_loop(self):
        for number in range(1, 7):
            self.correct_diagnostic_answer(number)
        seventh = self.input_json(self.choice_spec("q7", "c7"))
        before = self.snapshot()
        self.run_cli(
            "quiz-create", "--topic", "test", "--file", seventh, success=False,
        )
        self.assertEqual(self.snapshot(), before)

    def test_pending_quiz_restores_same_options_without_revealing_answers(self):
        created = self.create_quiz()
        first = self.status()
        second = self.status()
        pending = first["pending_quiz"]
        self.assertEqual(pending, second["pending_quiz"])
        self.assertEqual(pending["options"], created["quiz"]["options"])
        self.assertEqual(
            {option["id"] for option in pending["options"]},
            {"valid", "invalid", "unrelated"},
        )
        def forbidden_keys(value):
            if isinstance(value, dict):
                self.assertNotIn("correct", value)
                self.assertNotIn("explanation", value)
                for child in value.values():
                    forbidden_keys(child)
            elif isinstance(value, list):
                for child in value:
                    forbidden_keys(child)
        forbidden_keys(created)
        forbidden_keys(first)
        for suffix in ("*.md", "*.html"):
            for file in self.workspace.rglob(suffix):
                self.assertNotIn("PRIVATE_EXPLANATION", file.read_text(encoding="utf-8"))

    def test_pending_quiz_cannot_be_replaced_or_bypassed(self):
        self.run_cli("diagnosis-finish", "--topic", "test", "--skip")
        self.set_route()
        self.create_quiz(self.choice_spec(phase="teaching"))
        original = self.status()["pending_quiz"]
        self.run_cli(
            "quiz-create", "--topic", "test", "--file",
            self.input_json(self.choice_spec("q2", phase="teaching")), success=False,
        )
        self.run_cli("diagnosis-finish", "--topic", "test", success=False)
        self.run_cli("diagnosis-finish", "--topic", "test", "--skip", success=False)
        self.run_cli(
            "checkpoint", "--topic", "test", "--phase", "teaching",
            "--node", "c1", success=False,
        )
        self.assertEqual(self.status()["pending_quiz"], original)

    def test_same_submission_is_idempotent_and_changed_retry_is_rejected(self):
        self.create_quiz()
        first = self.submit()
        before = self.snapshot()
        repeated = self.submit()
        self.assertEqual(repeated["result"], first["result"])
        self.assertEqual(self.snapshot(), before)
        repeated_with_new_attempt = self.submit(attempt="network-retry")
        self.assertEqual(repeated_with_new_attempt["result"], first["result"])
        self.assertEqual(self.snapshot(), before)
        self.submit(answer={"selection": ["invalid"]}, success=False)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_selection_does_not_mutate_or_consume_pending_question(self):
        self.create_quiz()
        before = self.snapshot()
        self.submit(answer={"selection": ["nonexistent-option"]}, success=False)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.status()["pending_quiz"]["id"], "q1")

    def test_dont_know_is_evidence_for_review_and_cancellation_is_not_wrong(self):
        self.create_quiz()
        unknown = self.submit(answer={"dont_know": True})
        self.assertEqual(unknown["result"]["outcome"], "dont_know")
        self.create_quiz(self.choice_spec("q2", "c2"))
        cancelled = self.submit("q2", "a2", {"cancelled": True})
        self.assertEqual(cancelled["result"]["outcome"], "cancelled")
        review = json.dumps(self.run_cli("review-list", "--topic", "test"))
        self.assertIn("c1", review)
        self.assertNotIn('"c2"', review)
        self.assertIsNone(self.status()["pending_quiz"])

    def test_cancelled_question_does_not_consume_diagnostic_budget(self):
        self.create_quiz(self.choice_spec("cancelled", "cancelled-concept"))
        self.submit("cancelled", "cancel-attempt", {"cancelled": True})
        for number in range(1, 7):
            self.correct_diagnostic_answer(number)
        self.run_cli("diagnosis-finish", "--topic", "test")

    def test_reinitialization_preserves_the_existing_mission(self):
        mission = self.workspace / "MISSION.md"
        original = mission.read_bytes()
        self.run_cli(
            "topic-init", "--id", "test", "--title", "意外替换标题",
            "--mission", "意外替换目标", "--success", "意外替换结果",
            success=False,
        )
        self.assertEqual(mission.read_bytes(), original)

    def test_learning_record_requires_real_graded_evidence(self):
        self.record(success=False)
        self.record(["nonexistent-quiz"], success=False)
        self.create_quiz({
            "id": "open1", "kind": "open", "phase": "diagnostic",
            "concept_id": "c1", "question": "请给出推理。",
            "rubric": "必要条件完整且推理有效", "source_refs": [],
        })
        pending = self.submit("open1", "open-attempt", {"text": "我的完整推理"})
        self.assertEqual(pending["result"]["outcome"], "awaiting_evaluation")
        self.record(["open1"], success=False)
        self.run_cli(
            "quiz-assess", "--topic", "test", "--quiz", "open1", "--file",
            self.input_json({
                "outcome": "correct", "rationale": "意外改变评分条件。",
                "model": "test-only-assessor", "rubric": "只要求给出结论",
            }), success=False,
        )
        self.run_cli(
            "quiz-assess", "--topic", "test", "--quiz", "open1", "--file",
            self.input_json({
                "outcome": "correct", "rationale": "必要条件和推理均完整。",
                "model": "test-only-assessor", "rubric": "必要条件完整且推理有效",
            }),
        )
        result = self.record(["open1"])
        self.assertTrue(result["record"]["id"])
        repeated = self.record(["open1"])
        self.assertEqual(repeated["record"]["id"], result["record"]["id"])
        self.assertEqual(len(self.status()["learning_records"]), 1)

    def test_unassessed_open_answer_blocks_progress_but_allows_saving_current_node(self):
        self.run_cli("diagnosis-finish", "--topic", "test", "--skip")
        self.set_route()
        self.run_cli(
            "checkpoint", "--topic", "test", "--phase", "teaching",
            "--node", "c1",
        )
        self.create_quiz({
            "id": "open1", "kind": "open", "phase": "teaching",
            "concept_id": "c1", "question": "请独立给出有效推理。",
            "rubric": "必要条件完整且推理有效", "source_refs": [],
        })
        submitted = self.submit("open1", "open-attempt", {"text": "我的完整推理"})
        self.assertEqual(submitted["result"]["outcome"], "awaiting_evaluation")
        self.assertEqual(self.status()["next_action"], "assess_open_answer")
        next_question = self.input_json(self.choice_spec("q2", "c2", "teaching"))
        before = self.snapshot()
        self.run_cli(
            "quiz-create", "--topic", "test", "--file", next_question,
            success=False,
        )
        self.run_cli(
            "checkpoint", "--topic", "test", "--phase", "teaching",
            "--node", "c2", success=False,
        )
        self.assertEqual(self.snapshot(), before)
        saved = self.run_cli(
            "checkpoint", "--topic", "test", "--phase", "teaching",
            "--node", "c1", "--note", "暂停在当前概念，等待评阅。",
        )
        self.assertEqual(saved["phase"], "teaching")
        self.assertEqual(saved["current_node"], "c1")
        self.run_cli(
            "quiz-assess", "--topic", "test", "--quiz", "open1", "--file",
            self.input_json({
                "outcome": "correct", "rationale": "必要条件和推理均完整。",
                "model": "test-only-assessor", "rubric": "必要条件完整且推理有效",
            }),
        )
        self.run_cli(
            "checkpoint", "--topic", "test", "--phase", "teaching",
            "--node", "c2",
        )
        self.run_cli("quiz-create", "--topic", "test", "--file", next_question)
        resumed = self.status()
        self.assertEqual(resumed["current_node"], "c2")
        self.assertEqual(resumed["pending_quiz"]["id"], "q2")

    def test_confirmed_route_node_requires_existing_learning_record(self):
        self.create_quiz()
        self.submit()
        self.run_cli("diagnosis-finish", "--topic", "test")
        self.set_route(nodes=[{
            "id": "c1", "label": "概念1", "status": "confirmed",
            "evidence_refs": ["nonexistent-record"], "source_refs": [],
        }], success=False)
        record_id = self.record(["q1"])["record"]["id"]
        self.set_route(nodes=[{
            "id": "c1", "label": "概念1", "status": "confirmed",
            "evidence_refs": [record_id], "source_refs": [],
        }])
        self.assertEqual(self.status()["route"]["nodes"][0]["status"], "confirmed")

    def test_route_merge_changes_only_the_affected_branch(self):
        self.run_cli("diagnosis-finish", "--topic", "test", "--skip")
        self.set_route(edges=[["c1", "c2"], ["c3", "c4"]])
        original = {node["id"]: node for node in self.status()["route"]["nodes"]}
        self.set_route(nodes=[{
            "id": "c1", "label": "修正第一支的前置条件", "status": "pending",
            "source_refs": [], "evidence_refs": [],
        }])
        route = self.status()["route"]
        updated = {node["id"]: node for node in route["nodes"]}
        self.assertEqual(updated["c1"]["label"], "修正第一支的前置条件")
        for node_id in ("c2", "c3", "c4", "c5", "c6"):
            self.assertEqual(updated[node_id], original[node_id])
        self.assertEqual({tuple(edge) for edge in route["edges"]},
                         {("c1", "c2"), ("c3", "c4")})

    def test_route_cycle_or_unknown_edge_is_rejected_without_changing_route(self):
        self.run_cli("diagnosis-finish", "--topic", "test", "--skip")
        self.set_route(edges=[["c1", "c2"]])
        original = self.status()["route"]
        self.set_route(nodes=[], edges=[["c2", "c1"]], success=False)
        self.assertEqual(self.status()["route"], original)
        self.set_route(nodes=[], edges=[["c1", "missing"]], success=False)
        self.assertEqual(self.status()["route"], original)

    def test_sync_preserves_manual_edits_and_recreates_missing_generated_view(self):
        self.run_cli("diagnosis-finish", "--topic", "test", "--skip")
        self.set_route()
        mission = self.workspace / "MISSION.md"
        original = mission.read_text(encoding="utf-8")
        manual = original + "\n人工补充：我的工作背景不可丢失。\n"
        mission.write_text(manual, encoding="utf-8")
        untracked = self.workspace / "人工笔记.md"
        untracked.write_text("只属于用户的独立记录。\n", encoding="utf-8")
        index = self.workspace / "课程索引.md"
        manual_index = index.read_text(encoding="utf-8").replace(
            "# 局部推理学习测试", "# 人工改写的课程名称",
        )
        index.write_text(manual_index, encoding="utf-8")
        route = self.workspace / "学习路线.md"
        self.assertTrue(route.exists())
        route.unlink()
        conflict = self.run_cli(
            "sync", "--topic", "test", success=False, expected_code=2,
        )
        self.assertEqual(conflict["error_code"], "conflict")
        self.assertEqual(mission.read_text(encoding="utf-8"), manual)
        self.assertEqual(index.read_text(encoding="utf-8"), manual_index)
        self.assertEqual(untracked.read_text(encoding="utf-8"), "只属于用户的独立记录。\n")
        self.assertTrue(route.exists())
        self.assertTrue(any((self.root / "state" / "conflicts").rglob("*.merge")))
        self.run_cli("sync", "--topic", "test", success=False, expected_code=2)
        self.assertEqual(mission.read_text(encoding="utf-8"), manual)
        self.assertEqual(index.read_text(encoding="utf-8"), manual_index)

    def test_note_patch_checks_hash_and_rejects_path_escape(self):
        note = self.workspace / "人工笔记.md"
        note.write_text("用户原稿\n", encoding="utf-8")
        body = self.root / "approved-body.md"
        body.write_text("经过审阅的合并稿\n", encoding="utf-8")
        self.run_cli(
            "note-patch", "--topic", "test", "--path", "人工笔记.md",
            "--file", str(body), success=False,
        )
        self.run_cli(
            "note-patch", "--topic", "test", "--path", "人工笔记.md",
            "--file", str(body), "--expected-hash", "0" * 64, success=False,
        )
        self.assertEqual(note.read_text(encoding="utf-8"), "用户原稿\n")
        self.run_cli(
            "note-patch", "--topic", "test", "--path", "人工笔记.md",
            "--file", str(body), "--expected-hash", self.sha256(note),
        )
        self.assertEqual(note.read_text(encoding="utf-8"), "经过审阅的合并稿\n")
        outside = self.workspace.parent / "outside.md"
        self.run_cli(
            "note-patch", "--topic", "test", "--path", "../outside.md",
            "--file", str(body), success=False,
        )
        self.assertFalse(outside.exists())

    def test_renderer_validation_error_is_structured_without_traceback(self):
        source = self.root / "remote.mmd"
        source.write_text('flowchart LR\n A[来源] --> B[观点]\n%% https://example.com/source\n', encoding="utf-8")
        result = self.run_cli("render", "--kind", "mermaid", "--input", str(source),
                              "--output-dir", str(self.root / "rendered"), success=False, expected_code=1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["error"])
        self.assertTrue(Path(result["log"]).is_file())
        self.assertFalse(any((self.root / "rendered").glob("*.png")))

    def test_self_reported_knowledge_cannot_confirm_a_route_node(self):
        record = self.record(kind="prior_knowledge")["record"]
        self.run_cli("diagnosis-finish", "--topic", "test", "--skip")
        self.set_route(nodes=[{"id": "c1", "label": "概念", "status": "confirmed",
                              "source_refs": [], "evidence_refs": [record["id"]]}], success=False)
        self.assertFalse(self.status()["route"]["nodes"])

    def test_completed_diagnosis_is_preserved_when_local_checks_are_needed(self):
        self.correct_diagnostic_answer(1)
        self.run_cli("diagnosis-finish", "--topic", "test")
        self.set_route()
        baseline = self.status()["diagnosis"]
        self.run_cli("quiz-create", "--topic", "test", "--file",
                     self.input_json(self.choice_spec("q2", phase="diagnostic")), success=False)
        self.assertEqual(self.status()["diagnosis"], baseline)

        self.create_quiz(self.choice_spec("r1", phase="review"))
        self.submit("r1", "r1-a")
        self.assertEqual(self.status()["diagnosis"], baseline)

    def test_open_answer_can_resume_assessment_from_public_status(self):
        spec = {"id": "open1", "kind": "open", "phase": "diagnostic", "concept_id": "c1",
                "question": "请解释一个必要条件", "rubric": "给出条件并说明为何必要"}
        self.create_quiz(spec)
        self.submit("open1", "open1-a", {"text": "TEST：缺少该条件就不能推出结论。"})
        status = self.status()
        self.assertEqual(status["next_action"], "assess_open_answer")
        restored = status["awaiting_evaluations"][0]
        self.assertEqual(restored["id"], "open1")
        self.assertEqual(restored["attempt_id"], "open1-a")
        self.assertEqual(restored["rubric"], spec["rubric"])
        self.assertEqual(restored["answer"]["text"], "TEST：缺少该条件就不能推出结论。")
        self.assertNotIn("correct", restored)
        self.assertNotIn("explanation", restored)

    def test_failed_note_write_preserves_answer_and_pending_sync_for_retry(self):
        self.create_quiz()
        sessions = self.workspace / "sessions"
        mode = sessions.stat().st_mode & 0o777
        sessions.chmod(0o500)
        try:
            self.submit(success=False)
            status = self.status()
            self.assertEqual(status["diagnosis"]["answered"], 1)
            self.assertIsNone(status["pending_quiz"])
            self.assertEqual(status["sync"]["status"], "pending")
        finally:
            sessions.chmod(mode)
        retry = self.submit()
        self.assertTrue(retry["idempotent"])
        self.run_cli("sync", "--topic", "test")
        self.assertEqual(self.status()["sync"]["status"], "synced")
        self.assertEqual(self.status()["diagnosis"]["answered"], 1)
        log = next(sessions.glob("*.md")).read_text(encoding="utf-8")
        self.assertEqual(log.count("· quiz_answered"), 1)

    def test_verified_route_preview_is_idempotent_and_invalidated_by_changes(self):
        self.run_cli("diagnosis-finish", "--topic", "test", "--skip")
        self.set_route()
        assets = self.workspace / "assets"
        png = assets / "route.png"
        png.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a8yUAAAAASUVORK5CYII="))
        source = assets / "route.mmd"
        source.write_text("graph TD\n c1 --> c2", encoding="utf-8")
        manifest = assets / "route.render.json"
        value = {"status": "rendered", "visual_verified": False, "png": str(png),
                 "source": str(source), "log": str(manifest), "verification_note": "测试夹具：关联已检查的本地预览；不代表新路线人工检查。"}
        manifest.write_text(json.dumps(value), encoding="utf-8")
        self.run_cli("route-visual", "--topic", "test", "--manifest", str(manifest), success=False)
        value["visual_verified"] = True
        manifest.write_text(json.dumps(value), encoding="utf-8")
        self.run_cli("route-visual", "--topic", "test", "--manifest", str(manifest))
        repeated = self.run_cli("route-visual", "--topic", "test", "--manifest", str(manifest))
        self.assertTrue(repeated["idempotent"])
        doc = self.workspace / "学习路线.md"
        self.assertIn("](assets/route.png)", doc.read_text(encoding="utf-8"))
        self.set_route(nodes=[{"id": "new", "label": "新分支", "status": "unknown",
                              "source_refs": [], "evidence_refs": []}], edges=[["c1", "new"]])
        self.assertNotIn("](assets/route.png)", doc.read_text(encoding="utf-8"))
        self.assertIn("图示待渲染或更新", doc.read_text(encoding="utf-8"))
        self.run_cli("route-visual", "--topic", "test", "--manifest", str(manifest))
        png.write_bytes(png.read_bytes() + b"modified")
        self.run_cli("sync", "--topic", "test")
        self.assertNotIn("](assets/route.png)", doc.read_text(encoding="utf-8"))

    def test_mission_update_keeps_constraints_and_other_sections(self):
        mission = self.workspace / "MISSION.md"
        before = mission.read_text(encoding="utf-8")
        self.run_cli("mission-update", "--topic", "test", "--mission", "加入一个新分支",
                     "--success", "独立完成新分支任务", "--confirmed")
        after = mission.read_text(encoding="utf-8")
        self.assertEqual(before.split("## Constraints", 1)[1], after.split("## Constraints", 1)[1])
        self.assertIn("加入一个新分支", after)
        self.assertIn("独立完成新分支任务", after)

    def test_sync_conflict_can_be_merged_and_retried_without_duplicate_records(self):
        index = self.workspace / "课程索引.md"
        index.write_text(index.read_text(encoding="utf-8").replace("# 局部推理学习测试", "# 用户自己改的标题") + "\n人工注释：保留我自己的例子。\n", encoding="utf-8")
        self.create_quiz()
        result = self.run_cli("sync", "--topic", "test", success=False, expected_code=2)
        conflict = next(c for c in result["sync"]["conflicts"] if c["relative_path"] == "课程索引.md")
        self.run_cli("note-patch", "--topic", "test", "--path", "课程索引.md", "--file",
                     conflict["merge_path"], "--expected-hash", conflict["expected_hash"])
        self.run_cli("sync", "--topic", "test")
        self.run_cli("sync", "--topic", "test")
        self.assertIn("人工注释：保留我自己的例子。", index.read_text(encoding="utf-8"))
        session = next((self.workspace / "sessions").glob("*.md")).read_text(encoding="utf-8")
        self.assertEqual(session.count("· quiz_issued"), 1)
        self.assertEqual(self.status()["pending_quiz"]["id"], "q1")


if __name__ == "__main__":
    unittest.main()
