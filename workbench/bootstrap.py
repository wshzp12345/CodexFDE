"""L01 personal workbench bootstrap commands and evidence ledger."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3


SCHEMA_VERSION = "1.0"
STRUCTURED_PHASES = {"clarification", "design", "spec"}
REVIEW_PHASES = {"design_review", "spec_review", "final_review"}
PHASES = STRUCTURED_PHASES | REVIEW_PHASES | {"red", "diff", "green", "observation"}
RELATIONS = {"child_requirement", "change_of"}
APPLICABILITY = {"required", "covered_by_existing", "not_applicable"}
REVIEW_TARGETS = {
    "design_review": "design",
    "spec_review": "spec",
    "final_review": "green",
}
DEVELOPMENT_PHASES = {"red", "diff", "green"}
CLARIFICATION_QUESTIONS = {
    "acceptance_criteria": "期待的最终效果是什么，怎样从外部验证它已经实现？",
    "goal": "这项任务要解决谁在什么场景中的哪个困难？",
    "in_scope": "这次明确包含哪些结果？",
    "out_of_scope": "这次明确不包含哪些结果？",
    "business_constraints": "哪些业务行为和既有边界不能被破坏？",
    "technical_constraints": "实现必须遵守哪些技术、数据或兼容性约束？",
    "architecture": "本任务需要改变架构还是沿用现有架构，理由是什么？",
    "deployment": "本任务是否涉及部署；若沿用或不适用，理由是什么？",
    "end_to_end": "最终用户路径需要怎样做端到端验证？",
    "reuse": "是否需要评估复用；若不适用，理由是什么？",
    "change_control": "改变了哪些约束，影响、替代方案、迁移恢复和新验收分别是什么？",
    "design": "在已确认边界内采用什么设计，怎样满足业务和技术约束？",
    "design_review": "谁审核当前设计，决定和理由是什么？",
    "spec": "当前 Spec 是否写清目标、边界、约束和最终效果验收？",
    "spec_review": "谁审核当前 Spec，决定和理由是什么？",
}


class WorkbenchError(Exception):
    def __init__(self, code: str, message: str, missing_items=()):
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing_items = list(missing_items)


def add_bootstrap_commands(subparsers):
    init = subparsers.add_parser("workbench-init", help="初始化个人 AI 研发工作台")
    init.add_argument("--runtime-dir", default=".runtime/course/L01-workbench")
    init.add_argument("--name", required=True)
    init.add_argument("--owner", required=True)

    project = subparsers.add_parser("workbench-project-add", help="登记工作台项目")
    project.add_argument("--runtime-dir", default=".runtime/course/L01-workbench")
    project.add_argument("--project-id", required=True)
    project.add_argument("--name", required=True)
    project.add_argument("--path", required=True)
    project.add_argument("--purpose", required=True)

    task = subparsers.add_parser("workbench-task-create", help="创建可追溯任务")
    task.add_argument("--runtime-dir", default=".runtime/course/L01-workbench")
    task.add_argument("--project-id", required=True)
    task.add_argument("--task-id", required=True)
    task.add_argument("--requirement-id", required=True)
    task.add_argument("--request", required=True)
    task.add_argument("--actor", required=True)
    task.add_argument("--spec-file")
    task.add_argument("--problem-file")
    task.add_argument("--related-task-id")
    task.add_argument("--relation", choices=sorted(RELATIONS))

    evidence = subparsers.add_parser("workbench-evidence-add", help="追加任务运行记录")
    evidence.add_argument("--runtime-dir", default=".runtime/course/L01-workbench")
    evidence.add_argument("--task-id", required=True)
    evidence.add_argument("--phase", choices=sorted(PHASES), required=True)
    evidence.add_argument("--command-text", required=True)
    evidence.add_argument("--output-file", required=True)
    evidence.add_argument("--returncode", type=int, required=True)
    evidence.add_argument("--observed-at", required=True)
    evidence.add_argument("--reviewer")
    evidence.add_argument("--decision", choices=("approve", "reject"))
    evidence.add_argument("--review-note")

    status = subparsers.add_parser("workbench-status", help="查询工作台材料与缺项")
    status.add_argument("--runtime-dir", default=".runtime/course/L01-workbench")
    status.add_argument("--require-project")
    status.add_argument("--require-task")
    status.add_argument("--require-red-green-evidence", action="store_true")


def run_bootstrap_command(args):
    operation = args.command
    try:
        handlers = {
            "workbench-init": _initialize,
            "workbench-project-add": _add_project,
            "workbench-task-create": _create_task,
            "workbench-evidence-add": _add_evidence,
            "workbench-status": _status,
        }
        result = handlers[operation](args)
        print(json.dumps(_payload(True, operation, **result), ensure_ascii=False, indent=2))
        return 0
    except WorkbenchError as error:
        print(json.dumps(_payload(False, operation, error_code=error.code,
                                  message=error.message, missing_items=error.missing_items),
                         ensure_ascii=False, indent=2))
        return 1
    except (OSError, sqlite3.Error, UnicodeError) as error:
        print(json.dumps(_payload(False, operation, error_code="request_failed",
                                  message=str(error), missing_items=[]),
                         ensure_ascii=False, indent=2))
        return 1


def _payload(ok: bool, operation: str, **values):
    return {"schema_version": SCHEMA_VERSION, "ok": ok, "operation": operation, **values}


def _database(runtime_dir) -> Path:
    return Path(runtime_dir).resolve() / "workbench.db"


def _connect(runtime_dir, *, create=False):
    database = _database(runtime_dir)
    if create:
        database.parent.mkdir(parents=True, exist_ok=True)
    elif not database.exists():
        raise WorkbenchError("workbench_not_initialized", "工作台尚未初始化，请先运行 workbench-init")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _create_schema(connection):
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS workbench_identity (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1), name TEXT NOT NULL, owner TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, purpose TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id),
            requirement_id TEXT NOT NULL, request TEXT NOT NULL, actor TEXT NOT NULL,
            spec_path TEXT, spec_content TEXT, spec_sha256 TEXT,
            problem_path TEXT, problem_content TEXT, problem_sha256 TEXT,
            related_task_id TEXT REFERENCES tasks(task_id),
            relation TEXT CHECK (relation IS NULL OR relation IN ('child_requirement', 'change_of'))
        );
        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(task_id),
            phase TEXT NOT NULL, command_text TEXT NOT NULL, output_path TEXT NOT NULL,
            output_content BLOB NOT NULL, output_sha256 TEXT NOT NULL,
            returncode INTEGER NOT NULL, observed_at TEXT NOT NULL, material_json TEXT,
            reviewer TEXT, decision TEXT CHECK (decision IS NULL OR decision IN ('approve', 'reject')),
            review_note TEXT,
            reviewed_evidence_id INTEGER REFERENCES evidence(evidence_id),
            reviewed_sha256 TEXT
        );
        """
    )


def _initialize(args):
    with _connect(args.runtime_dir, create=True) as connection:
        _create_schema(connection)
        existing = connection.execute(
            "SELECT name,owner FROM workbench_identity WHERE singleton=1"
        ).fetchone()
        if existing and (existing["name"] != args.name or existing["owner"] != args.owner):
            raise WorkbenchError("workbench_already_initialized", "工作台已经使用不同身份初始化")
        if not existing:
            connection.execute("INSERT INTO workbench_identity VALUES(1,?,?)", (args.name, args.owner))
    return {"workbench": {"name": args.name, "owner": args.owner,
                           "database": str(_database(args.runtime_dir))}}


def _require_identity(connection):
    row = connection.execute("SELECT name,owner FROM workbench_identity WHERE singleton=1").fetchone()
    if not row:
        raise WorkbenchError("workbench_not_initialized", "工作台尚未初始化")
    return {"name": row["name"], "owner": row["owner"]}


def _add_project(args):
    path = Path(args.path).resolve()
    if not path.is_dir():
        raise WorkbenchError("project_path_invalid", f"项目目录不存在：{path}")
    with _connect(args.runtime_dir) as connection:
        _require_identity(connection)
        if connection.execute("SELECT 1 FROM projects WHERE project_id=?", (args.project_id,)).fetchone():
            raise WorkbenchError("duplicate_project_id", f"项目编号已存在：{args.project_id}")
        connection.execute("INSERT INTO projects VALUES(?,?,?,?)",
                           (args.project_id, args.name, str(path), args.purpose))
    return {"project": {"project_id": args.project_id, "name": args.name,
                         "path": str(path), "purpose": args.purpose}}


def _snapshot(path_value):
    if not path_value:
        return None
    path = Path(path_value).resolve()
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise WorkbenchError("snapshot_unreadable", f"无法读取快照文件 {path}：{error}") from error
    return {"path": str(path), "content": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}


def _create_task(args):
    if bool(args.related_task_id) != bool(args.relation):
        raise WorkbenchError("relation_invalid", "关联任务和关系类型必须同时提供")
    spec, problem = _snapshot(args.spec_file), _snapshot(args.problem_file)
    with _connect(args.runtime_dir) as connection:
        _require_identity(connection)
        if not connection.execute("SELECT 1 FROM projects WHERE project_id=?",
                                  (args.project_id,)).fetchone():
            raise WorkbenchError("project_not_found", f"项目不存在：{args.project_id}")
        if connection.execute("SELECT 1 FROM tasks WHERE task_id=?", (args.task_id,)).fetchone():
            raise WorkbenchError("duplicate_task_id", f"任务编号已存在：{args.task_id}")
        if args.related_task_id:
            related = connection.execute("SELECT project_id FROM tasks WHERE task_id=?",
                                         (args.related_task_id,)).fetchone()
            if not related:
                raise WorkbenchError("related_task_not_found", f"关联任务不存在：{args.related_task_id}")
            if related["project_id"] != args.project_id:
                raise WorkbenchError("relation_cross_project", "关联任务必须属于同一项目")
        connection.execute(
            """INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (args.task_id, args.project_id, args.requirement_id, args.request, args.actor,
             None if spec is None else spec["path"], None if spec is None else spec["content"],
             None if spec is None else spec["sha256"],
             None if problem is None else problem["path"], None if problem is None else problem["content"],
             None if problem is None else problem["sha256"], args.related_task_id, args.relation),
        )
        row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (args.task_id,)).fetchone()
    return {"task": _task_dict(row)}


def _task_dict(row):
    task = {key: row[key] for key in
            ("task_id", "project_id", "requirement_id", "request", "actor",
             "related_task_id", "relation")}
    task["spec_snapshot"] = None if row["spec_content"] is None else {
        "path": row["spec_path"], "content": row["spec_content"], "sha256": row["spec_sha256"]}
    task["problem_snapshot"] = None if row["problem_content"] is None else {
        "path": row["problem_path"], "content": row["problem_content"],
        "sha256": row["problem_sha256"]}
    return task


def _read_output(path_value):
    path = Path(path_value).resolve()
    try:
        return path, path.read_bytes()
    except OSError as error:
        raise WorkbenchError("output_unreadable", f"无法读取输出文件 {path}：{error}") from error


def _structured_material(phase, content):
    if phase not in STRUCTURED_PHASES:
        return None
    try:
        material = json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise WorkbenchError("structured_material_invalid", f"结构化材料不是有效 UTF-8 JSON：{error}") from error
    if not isinstance(material, dict) or material.get("schema_version") != SCHEMA_VERSION:
        raise WorkbenchError("structured_material_invalid", "结构化材料必须是 schema_version 1.0 的 JSON 对象")
    return material


def _has_phase(connection, task_id, phase, decision=None):
    sql, values = "SELECT 1 FROM evidence WHERE task_id=? AND phase=?", [task_id, phase]
    if decision is not None:
        sql += " AND decision=?"
        values.append(decision)
    return connection.execute(sql + " LIMIT 1", values).fetchone() is not None


def _latest_evidence(connection, task_id, phase):
    return connection.execute(
        "SELECT * FROM evidence WHERE task_id=? AND phase=? ORDER BY evidence_id DESC LIMIT 1",
        (task_id, phase),
    ).fetchone()


def _current_review(connection, task_id, review_phase):
    target = _latest_evidence(connection, task_id, REVIEW_TARGETS[review_phase])
    review = _latest_evidence(connection, task_id, review_phase)
    if not target or not review or review["reviewed_evidence_id"] != target["evidence_id"]:
        return None
    return review


def _is_currently_approved(connection, task_id, review_phase):
    review = _current_review(connection, task_id, review_phase)
    return bool(review and review["decision"] == "approve")


def _latest_material(connection, task_id, phase=None):
    sql, values = "SELECT material_json FROM evidence WHERE task_id=? AND material_json IS NOT NULL", [task_id]
    if phase:
        sql += " AND phase=?"
        values.append(phase)
    row = connection.execute(sql + " ORDER BY evidence_id DESC LIMIT 1", values).fetchone()
    return None if not row else json.loads(row["material_json"])


def _add_evidence(args):
    output_path, output_content = _read_output(args.output_file)
    material = _structured_material(args.phase, output_content)
    with _connect(args.runtime_dir) as connection:
        _require_identity(connection)
        task = connection.execute("SELECT * FROM tasks WHERE task_id=?", (args.task_id,)).fetchone()
        if not task:
            raise WorkbenchError("task_not_found", f"任务不存在：{args.task_id}")
        review_target = None
        if args.phase in REVIEW_PHASES:
            if not args.reviewer or not args.decision or not args.review_note:
                raise WorkbenchError("review_fields_missing", "审核记录必须包含审核人、决定和理由")
            review_target = _latest_evidence(connection, args.task_id, REVIEW_TARGETS[args.phase])
            if not review_target:
                raise WorkbenchError("review_gate_missing", "缺少可绑定的审核对象")
            if args.decision == "approve":
                _validate_review_gate(connection, task, args.phase, review_target)
        elif args.reviewer or args.decision or args.review_note:
            raise WorkbenchError("review_fields_not_allowed", "非审核记录不得包含审核字段")
        if args.phase in DEVELOPMENT_PHASES and not (
            _is_currently_approved(connection, args.task_id, "design_review")
            and _is_currently_approved(connection, args.task_id, "spec_review")
        ):
            raise WorkbenchError("review_gate_missing", "设计和 Spec 的当前版本均审核通过后才能追加开发记录")
        connection.execute(
            """INSERT INTO evidence(task_id,phase,command_text,output_path,output_content,
               output_sha256,returncode,observed_at,material_json,reviewer,decision,review_note,
               reviewed_evidence_id,reviewed_sha256)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (args.task_id, args.phase, args.command_text, str(output_path), output_content,
             hashlib.sha256(output_content).hexdigest(), args.returncode, args.observed_at,
             None if material is None else json.dumps(material, ensure_ascii=False),
             args.reviewer, args.decision, args.review_note,
             None if review_target is None else review_target["evidence_id"],
             None if review_target is None else review_target["output_sha256"]),
        )
        evidence_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = connection.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
    return {"evidence": _evidence_dict(row)}


def _validate_review_gate(connection, task, phase, review_target):
    task_id = task["task_id"]
    if phase == "design_review":
        return
    elif phase == "spec_review":
        material = json.loads(review_target["material_json"])
        missing = _material_missing(material, task["relation"])
        if missing:
            raise WorkbenchError("spec_incomplete", "结构化 Spec 尚不完整", missing)
        if not _is_currently_approved(connection, task_id, "design_review"):
            raise WorkbenchError("review_gate_missing", "设计审核尚未通过")
    elif phase == "final_review":
        if not _is_currently_approved(connection, task_id, "spec_review"):
            raise WorkbenchError("review_gate_missing", "Spec 审核尚未通过")
        rows = connection.execute("SELECT * FROM evidence WHERE task_id=? ORDER BY evidence_id",
                                  (task_id,)).fetchall()
        if not _red_diff_green_complete(rows, required_green_id=review_target["evidence_id"]):
            raise WorkbenchError("review_gate_missing", "缺少同命令红灯—Diff—绿灯证据")


def _evidence_dict(row):
    output = row["output_content"]
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    review_target = None
    if row["reviewed_evidence_id"] is not None:
        review_target = {"evidence_id": row["reviewed_evidence_id"],
                         "phase": REVIEW_TARGETS[row["phase"]],
                         "sha256": row["reviewed_sha256"]}
    return {"evidence_id": row["evidence_id"], "task_id": row["task_id"],
            "phase": row["phase"], "command_text": row["command_text"],
            "output_path": row["output_path"], "output": output,
            "sha256": row["output_sha256"], "returncode": row["returncode"],
            "observed_at": row["observed_at"],
            "material": None if row["material_json"] is None else json.loads(row["material_json"]),
            "reviewer": row["reviewer"], "decision": row["decision"],
            "review_note": row["review_note"], "review_target": review_target}


def _valid_acceptance(material):
    acceptance = material.get("acceptance_criteria")
    return (isinstance(acceptance, list) and bool(acceptance) and all(
        isinstance(item, dict) and item.get("id") and item.get("expected_effect")
        and item.get("verification") for item in acceptance
    ))


def _material_missing(material, relation):
    missing = []
    if not _valid_acceptance(material):
        missing.append("acceptance_criteria")
    if not material.get("goal"):
        missing.append("goal")
    for field in ("in_scope", "out_of_scope", "business_constraints", "technical_constraints"):
        if field not in material or not isinstance(material[field], list):
            missing.append(field)
    for field, detail in {"architecture": "decision", "deployment": "approach",
                          "end_to_end": "expected_effect", "reuse": "approach"}.items():
        value = material.get(field)
        if not isinstance(value, dict) or value.get("applicability") not in APPLICABILITY or not value.get("reason"):
            missing.append(field)
        elif value["applicability"] in {"required", "covered_by_existing"} and not value.get(detail):
            missing.append(field)
    if relation == "change_of":
        control = material.get("change_control")
        fields = ("changed_constraints", "impact_scope", "alternative",
                  "migration_or_recovery", "new_acceptance_criteria")
        if not isinstance(control, dict) or any(not control.get(field) for field in fields):
            missing.append("change_control")
    return missing


def _red_diff_green_complete(rows, required_green_id=None):
    for red_index, red in enumerate(rows):
        if red["phase"] != "red" or red["returncode"] == 0:
            continue
        for green_index in range(red_index + 1, len(rows)):
            green = rows[green_index]
            if (green["phase"] == "green" and green["returncode"] == 0
                    and (required_green_id is None or green["evidence_id"] == required_green_id)
                    and green["command_text"] == red["command_text"]
                    and any(item["phase"] == "diff" for item in rows[red_index + 1:green_index])):
                return True
    return False


def _project_dict(row):
    return {key: row[key] for key in ("project_id", "name", "path", "purpose")}


def _status(args):
    with _connect(args.runtime_dir) as connection:
        workbench = _require_identity(connection)
        projects = connection.execute("SELECT * FROM projects ORDER BY project_id").fetchall()
        tasks = connection.execute("SELECT * FROM tasks ORDER BY task_id").fetchall()
        if args.require_project and not any(row["project_id"] == args.require_project for row in projects):
            raise WorkbenchError("required_project_missing", f"指定项目不存在：{args.require_project}")
        result = {"workbench": workbench, "projects": [_project_dict(row) for row in projects],
                  "tasks": [_task_dict(row) for row in tasks], "task_count": len(tasks),
                  "flowerp_connected": False}
        if args.require_task:
            task = connection.execute("SELECT * FROM tasks WHERE task_id=?", (args.require_task,)).fetchone()
            if not task or (args.require_project and task["project_id"] != args.require_project):
                raise WorkbenchError("required_task_missing", f"指定任务不存在：{args.require_task}")
            result.update(_task_status(connection, task))
            if args.require_red_green_evidence and not result["evidence_complete"]:
                raise WorkbenchError("same_command_red_diff_green_missing",
                                     "缺少同命令红灯—Diff—绿灯证据", result["missing_items"])
        return result


def _task_status(connection, task):
    task_id = task["task_id"]
    rows = connection.execute("SELECT * FROM evidence WHERE task_id=? ORDER BY evidence_id",
                              (task_id,)).fetchall()
    material = _latest_material(connection, task_id, "spec") or _latest_material(connection, task_id)
    missing = _material_missing(material or {}, task["relation"])
    if not _has_phase(connection, task_id, "design"):
        missing.append("design")
    if not _is_currently_approved(connection, task_id, "design_review"):
        missing.append("design_review")
    if not _has_phase(connection, task_id, "spec"):
        missing.append("spec")
    if not _is_currently_approved(connection, task_id, "spec_review"):
        missing.append("spec_review")
    inbound = connection.execute(
        "SELECT task_id,related_task_id,relation FROM tasks WHERE related_task_id=? ORDER BY task_id",
        (task_id,),
    ).fetchall()
    blockers = [row["task_id"] for row in inbound
                if row["relation"] == "child_requirement" and not _accepted(connection, row["task_id"])]
    own_state = _task_own_state(connection, task, rows)
    acceptance = own_state["acceptance"]
    if acceptance == "accepted" and blockers:
        acceptance = "pending_human_review"
    questions = [CLARIFICATION_QUESTIONS.get(item, f"还需要确认：{item}")
                 for item in dict.fromkeys(missing)]
    return {"task": _task_dict(task), "evidence": [_evidence_dict(row) for row in rows],
            "relations": [dict(row) for row in inbound],
            "missing_items": list(dict.fromkeys(missing)),
            "clarification_questions": questions,
            "ready_for_development": own_state["ready_for_development"],
            "verifiable": bool(material and _valid_acceptance(material)),
            "evidence_complete": own_state["evidence_complete"], "acceptance": acceptance,
            "acceptance_blockers": blockers, "all_requirements_proven": acceptance == "accepted"}


def _task_own_state(connection, task, rows=None):
    task_id = task["task_id"]
    if rows is None:
        rows = connection.execute("SELECT * FROM evidence WHERE task_id=? ORDER BY evidence_id",
                                  (task_id,)).fetchall()
    spec = _latest_material(connection, task_id, "spec")
    ready = (not _material_missing(spec or {}, task["relation"])
             and _is_currently_approved(connection, task_id, "design_review")
             and _is_currently_approved(connection, task_id, "spec_review"))
    evidence_complete = _red_diff_green_complete(rows)
    final_review = _current_review(connection, task_id, "final_review")
    if final_review and final_review["decision"] == "reject":
        acceptance = "rejected"
    elif final_review and final_review["decision"] == "approve" and ready and evidence_complete:
        acceptance = "accepted"
    else:
        acceptance = "pending_human_review"
    return {"ready_for_development": ready, "evidence_complete": evidence_complete,
            "acceptance": acceptance}


def _accepted(connection, task_id, visiting=None):
    visiting = set() if visiting is None else visiting
    if task_id in visiting:
        return False
    visiting.add(task_id)
    try:
        task = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        rows = connection.execute("SELECT * FROM evidence WHERE task_id=? ORDER BY evidence_id",
                                  (task_id,)).fetchall()
        if _task_own_state(connection, task, rows)["acceptance"] != "accepted":
            return False
        children = connection.execute(
            "SELECT task_id FROM tasks WHERE related_task_id=? AND relation='child_requirement'",
            (task_id,),
        ).fetchall()
        return all(_accepted(connection, child["task_id"], visiting) for child in children)
    finally:
        visiting.remove(task_id)
