from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import text

from plugin.backend.app.api_execution import _canonical, _utc_timestamp
from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.test_review import _hash

BUG_SCHEMA_VERSION = "canonical-bug@1.0.0"
BUG_BUNDLE_FORMAT_VERSION = "bug-bundle@1.0.0"
SUPPORTED_BUG_ID = "BUG-AUTH-001"
SENSITIVE_MARKERS = (
    b"test1234",
    b"authorization: bearer",
    b"session token",
    b"cookie:",
    b"sqlite:///",
    b"deepseek_api_key",
)


class BugArtifactError(Exception):
    pass


class BugArtifactService:
    def __init__(self, database: PluginDatabase, *, artifact_root: Path | None = None) -> None:
        self.database = database
        self.artifact_root = artifact_root or PROJECT_ROOT / "artifacts" / "bugs"
        schema_path = PROJECT_ROOT / "schemas" / "bugs" / "v1" / "canonical_bug.schema.json"
        self.validator = Draft202012Validator(json.loads(schema_path.read_text("utf-8")))

    def generate(self, consolidation_run_id: str, bug_id: str) -> dict[str, Any]:
        if bug_id != SUPPORTED_BUG_ID:
            raise BugArtifactError("BUG_POLICY_UNSUPPORTED")
        existing = self.database.fetch_one(
            "SELECT canonical_bug_record_id FROM canonical_bug_records "
            "WHERE evidence_consolidation_run_id=:run AND bug_id=:bug",
            {"run": consolidation_run_id, "bug": bug_id},
        )
        if existing:
            return self.get(str(existing["canonical_bug_record_id"]))
        context, sources = self._eligible_sources(consolidation_run_id, bug_id)
        created_at = _utc_timestamp()
        bug_version = 1
        stamp = created_at.replace("-", "").replace(":", "").replace(".", "").replace("Z", "Z")
        basename = f"bug-auth-001--bug--v{bug_version}--{stamp}"
        final_dir = self.artifact_root / basename
        staging_dir = self.artifact_root / f".{basename}.staging-{new_id('TMP')}"
        if final_dir.exists() or staging_dir.exists():
            raise BugArtifactError("BUG_BUNDLE_PATH_CONFLICT")
        api_export = f"{basename}--api-evidence.json"
        for source in sources:
            if source["executor"] == "api":
                source["evidence"][0]["relative_path"] = (
                    final_dir.relative_to(PROJECT_ROOT) / api_export
                ).as_posix()
        canonical = self._canonical_record(context, sources, bug_id, bug_version, created_at)
        errors = sorted(self.validator.iter_errors(canonical), key=lambda error: list(error.path))
        if errors:
            raise BugArtifactError(f"CANONICAL_BUG_SCHEMA_INVALID:{errors[0].json_path}")
        self._assert_safe(_canonical(canonical).encode())
        try:
            bundle = self._write_bundle(staging_dir, final_dir, basename, canonical, sources)
            record_id = new_id("BUGR")
            with self.database.transaction() as connection:
                connection.execute(
                    text(
                        "INSERT INTO canonical_bug_records(canonical_bug_record_id,bug_id,"
                        "bug_version,project_id,evidence_consolidation_run_id,schema_version,status,"
                        "severity,priority,defect_type,canonical_json,canonical_hash,created_at) "
                        "VALUES "
                        "(:id,:bug,:version,:project,:run,:schema,'open','high','P1',"
                        "'business_rule_validation',:payload,:hash,:created)"
                    ),
                    {
                        "id": record_id,
                        "bug": bug_id,
                        "version": bug_version,
                        "project": context["project_id"],
                        "run": consolidation_run_id,
                        "schema": BUG_SCHEMA_VERSION,
                        "payload": _canonical(canonical),
                        "hash": _hash(canonical),
                        "created": created_at,
                    },
                )
                for source in sources:
                    for evidence in source["evidence"]:
                        connection.execute(
                            text(
                                "INSERT INTO canonical_bug_sources(canonical_bug_source_id,"
                                "canonical_bug_record_id,failure_classification_id,source_executor,"
                                "source_result_id,source_evidence_id,case_id,case_version,"
                                "approved_test_case_version_id,requirement_id,evidence_kind,"
                                "evidence_hash,relative_path) VALUES "
                                "(:id,:record,:classification,:executor,:result,:evidence,:case,"
                                ":version,:approved,:requirement,:kind,:hash,:path)"
                            ),
                            {
                                "id": new_id("BUGS"),
                                "record": record_id,
                                "classification": source["classification_id"],
                                "executor": source["executor"],
                                "result": source["result_id"],
                                "evidence": evidence["evidence_id"],
                                "case": source["case_id"],
                                "version": source["case_version"],
                                "approved": source["approved_version_id"],
                                "requirement": source["requirement_id"],
                                "kind": evidence["kind"],
                                "hash": evidence["content_hash"],
                                "path": evidence["relative_path"],
                            },
                        )
                connection.execute(
                    text(
                        "INSERT INTO bug_artifact_bundles(bug_artifact_bundle_id,"
                        "canonical_bug_record_id,format_version,bundle_path,json_path,json_hash,"
                        "markdown_path,markdown_hash,manifest_path,manifest_hash,status,"
                        "created_at) "
                        "VALUES (:id,:record,:format,:bundle,:json,:json_hash,:markdown,"
                        ":markdown_hash,:manifest,:manifest_hash,'completed',:created)"
                    ),
                    {
                        "id": new_id("BGB"),
                        "record": record_id,
                        "format": BUG_BUNDLE_FORMAT_VERSION,
                        **bundle,
                        "created": created_at,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO bug_artifact_audit_events(bug_artifact_audit_event_id,"
                        "canonical_bug_record_id,event_type,details_json) VALUES "
                        "(:id,:record,'bug_bundle_generated',:details)"
                    ),
                    {
                        "id": new_id("BGA"),
                        "record": record_id,
                        "details": _canonical(
                            {"source_count": len(sources), "external_push_count": 0}
                        ),
                    },
                )
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        return self.get(record_id)

    def get(self, record_id: str) -> dict[str, Any]:
        record = self.database.fetch_one(
            "SELECT * FROM canonical_bug_records WHERE canonical_bug_record_id=:id",
            {"id": record_id},
        )
        if not record:
            raise BugArtifactError("CANONICAL_BUG_NOT_FOUND")
        bundle = self.database.fetch_one(
            "SELECT * FROM bug_artifact_bundles WHERE canonical_bug_record_id=:id",
            {"id": record_id},
        )
        sources = self.database.fetch_all(
            "SELECT * FROM canonical_bug_sources WHERE canonical_bug_record_id=:id "
            "ORDER BY source_executor,evidence_kind",
            {"id": record_id},
        )
        return {
            **{key: value for key, value in record.items() if key != "canonical_json"},
            "canonical_bug": json.loads(str(record["canonical_json"])),
            "bundle": bundle,
            "sources": sources,
        }

    def _eligible_sources(
        self, consolidation_run_id: str, bug_id: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        run = self.database.fetch_one(
            "SELECT * FROM evidence_consolidation_runs WHERE evidence_consolidation_run_id=:run",
            {"run": consolidation_run_id},
        )
        if not run or run["status"] != "completed":
            raise BugArtifactError("CONSOLIDATION_NOT_ELIGIBLE")
        classifications = self.database.fetch_all(
            "SELECT * FROM deterministic_failure_classifications "
            "WHERE evidence_consolidation_run_id=:run AND suspected_bug_id=:bug "
            "ORDER BY source_executor",
            {"run": consolidation_run_id, "bug": bug_id},
        )
        if len(classifications) != 2 or {row["source_executor"] for row in classifications} != {
            "api",
            "ui",
        }:
            raise BugArtifactError("BUG_SOURCE_SET_INVALID")
        sources = [self._source(row) for row in classifications]
        if any(row["verdict"] != "FAIL" for row in classifications):
            raise BugArtifactError("BUG_SOURCE_NOT_FAILED")
        if any(row["classification_code"] != "seeded_product_bug" for row in classifications):
            raise BugArtifactError("BUG_CLASSIFICATION_INVALID")
        requirement_ids = {source["requirement_id"] for source in sources}
        projects = {
            str(row["project_id"])
            for requirement_id in requirement_ids
            if (
                row := self.database.fetch_one(
                    "SELECT project_id FROM requirements WHERE requirement_id=:requirement",
                    {"requirement": requirement_id},
                )
            )
        }
        if len(projects) != 1 or len(requirement_ids) == 0:
            raise BugArtifactError("BUG_PROJECT_TRACE_INVALID")
        return {**run, "project_id": projects.pop()}, sources

    def _source(self, classification: dict[str, Any]) -> dict[str, Any]:
        executor = str(classification["source_executor"])
        result_table = "api_test_results" if executor == "api" else "ui_test_results"
        result_id = "api_test_result_id" if executor == "api" else "ui_test_result_id"
        result = self.database.fetch_one(
            f"SELECT * FROM {result_table} WHERE {result_id}=:id",  # noqa: S608 - fixed allowlist
            {"id": classification["source_result_id"]},
        )
        if (
            not result
            or result["status"] != "FAIL"
            or result["case_id"] != classification["case_id"]
        ):
            raise BugArtifactError("BUG_RESULT_TRACE_INVALID")
        frozen = self.database.fetch_one(
            "SELECT s.snapshot_json,s.snapshot_hash,m.approved_test_case_version_id,"
            "m.case_version,a.payload_json,a.content_hash FROM immutable_execution_snapshots s "
            "JOIN frozen_baseline_members m ON "
            "m.frozen_baseline_member_id=s.frozen_baseline_member_id "
            "JOIN approved_test_case_versions a ON a.approved_test_case_version_id="
            "m.approved_test_case_version_id WHERE s.immutable_execution_snapshot_id=:id",
            {"id": result["immutable_execution_snapshot_id"]},
        )
        if not frozen:
            raise BugArtifactError("BUG_FROZEN_CASE_TRACE_INVALID")
        snapshot = json.loads(str(frozen["snapshot_json"]))
        approved = json.loads(str(frozen["payload_json"]))
        if _hash(snapshot) != frozen["snapshot_hash"] or _hash(approved) != frozen["content_hash"]:
            raise BugArtifactError("BUG_FROZEN_CASE_HASH_INVALID")
        case = snapshot["case"]
        requirement_ids = case.get("requirement_ids", [])
        if (
            case.get("case_id") != result["case_id"]
            or int(frozen["case_version"]) != int(result["case_version"])
            or len(requirement_ids) != 1
        ):
            raise BugArtifactError("BUG_CASE_TRACE_INVALID")
        evidence_rows = self.database.fetch_all(
            "SELECT * FROM consolidated_evidence_records WHERE evidence_consolidation_run_id="
            ":run AND source_executor=:executor AND source_result_id=:result "
            "ORDER BY evidence_kind",
            {
                "run": classification["evidence_consolidation_run_id"],
                "executor": executor,
                "result": classification["source_result_id"],
            },
        )
        if not evidence_rows:
            raise BugArtifactError("BUG_EVIDENCE_MISSING")
        evidence = [self._verify_evidence(executor, row) for row in evidence_rows]
        return {
            "executor": executor,
            "case_id": result["case_id"],
            "case_version": int(result["case_version"]),
            "approved_version_id": frozen["approved_test_case_version_id"],
            "result_id": classification["source_result_id"],
            "classification_id": classification["failure_classification_id"],
            "requirement_id": requirement_ids[0],
            "evidence": evidence,
        }

    def _verify_evidence(self, executor: str, row: dict[str, Any]) -> dict[str, Any]:
        if row["integrity_status"] != "verified" or row["redaction_status"] != "verified":
            raise BugArtifactError("BUG_EVIDENCE_NOT_VERIFIED")
        if executor == "api":
            source = self.database.fetch_one(
                "SELECT evidence_json,evidence_hash FROM api_test_evidence "
                "WHERE api_test_evidence_id=:id",
                {"id": row["source_evidence_id"]},
            )
            if not source:
                raise BugArtifactError("BUG_EVIDENCE_SOURCE_MISSING")
            payload = _canonical(json.loads(str(source["evidence_json"]))).encode()
            if (
                self._sha(payload) != row["content_hash"]
                or source["evidence_hash"] != row["content_hash"]
            ):
                raise BugArtifactError("BUG_EVIDENCE_HASH_INVALID")
            self._assert_safe(payload)
            return {
                "evidence_id": row["source_evidence_id"],
                "kind": row["evidence_kind"],
                "content_hash": row["content_hash"],
                "relative_path": None,
                "_content": payload,
            }
        relative = str(row["relative_path"])
        path = (PROJECT_ROOT / relative).resolve()
        root = (PROJECT_ROOT / "artifacts" / "evidence").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise BugArtifactError("BUG_EVIDENCE_PATH_INVALID")
        content = path.read_bytes()
        if self._sha(content) != row["content_hash"]:
            raise BugArtifactError("BUG_EVIDENCE_HASH_INVALID")
        self._assert_safe(content)
        return {
            "evidence_id": row["source_evidence_id"],
            "kind": row["evidence_kind"],
            "content_hash": row["content_hash"],
            "relative_path": relative,
        }

    @staticmethod
    def _canonical_record(
        context: dict[str, Any],
        sources: list[dict[str, Any]],
        bug_id: str,
        version: int,
        created_at: str,
    ) -> dict[str, Any]:
        clean_sources = [
            {key: value for key, value in source.items() if key != "requirement_id"}
            | {
                "evidence": [
                    {key: value for key, value in evidence.items() if not key.startswith("_")}
                    for evidence in source["evidence"]
                ]
            }
            for source in sources
        ]
        return {
            "schema_version": BUG_SCHEMA_VERSION,
            "bug_id": bug_id,
            "bug_version": version,
            "title": "Registration accepts a username shorter than the required six characters",
            "status": "open",
            "severity": "high",
            "priority": "P1",
            "defect_type": "business_rule_validation",
            "project_id": context["project_id"],
            "requirement_ids": sorted({source["requirement_id"] for source in sources}),
            "environment": {
                "environment_id": "local-windows-demo",
                "frozen_baseline_id": context["frozen_baseline_id"],
                "api_run_id": context["api_test_run_id"],
                "ui_run_id": context["ui_test_run_id"],
            },
            "preconditions": [
                "Use the frozen MVP baseline in an isolated local test database.",
                "Open the registration workflow without an authenticated session.",
            ],
            "reproduction_steps": [
                "Open the registration page.",
                "Enter the approved five-character username and valid confirmation data.",
                "Submit the registration form once.",
                "Observe the registration API response and resulting browser route.",
            ],
            "expected_result": (
                "Registration is rejected with HTTP 400, the browser remains on /register, "
                "and a minimum-six-character validation error is shown."
            ),
            "actual_result": (
                "The API returned HTTP 201 and the browser navigated to /profile, creating and "
                "authenticating a user whose username contains only five characters."
            ),
            "failure_classification": "seeded_product_bug",
            "sources": clean_sources,
            "advisory_ai": [],
            "created_at": created_at,
        }

    def _write_bundle(
        self,
        staging: Path,
        final: Path,
        basename: str,
        canonical: dict[str, Any],
        sources: list[dict[str, Any]],
    ) -> dict[str, str]:
        staging.mkdir(parents=True, exist_ok=False)
        json_path = staging / f"{basename}.json"
        markdown_path = staging / f"{basename}.md"
        manifest_path = staging / "manifest.json"
        api_path = staging / f"{basename}--api-evidence.json"
        api_source = next(source for source in sources if source["executor"] == "api")
        api_path.write_bytes(api_source["evidence"][0]["_content"])
        json_path.write_text(_canonical(canonical) + "\n", encoding="utf-8", newline="\n")
        markdown_path.write_text(self._markdown(canonical, final), encoding="utf-8", newline="\n")
        evidence_manifest = [
            {
                "evidence_id": evidence["evidence_id"],
                "kind": evidence["kind"],
                "relative_path": evidence["relative_path"],
                "content_hash": evidence["content_hash"],
            }
            for source in canonical["sources"]
            for evidence in source["evidence"]
        ]
        manifest = {
            "format_version": BUG_BUNDLE_FORMAT_VERSION,
            "bug_id": canonical["bug_id"],
            "bug_version": canonical["bug_version"],
            "created_at": canonical["created_at"],
            "json": {"path": json_path.name, "sha256": self._file_hash(json_path)},
            "markdown": {"path": markdown_path.name, "sha256": self._file_hash(markdown_path)},
            "evidence": evidence_manifest,
            "result_ids": [source["result_id"] for source in canonical["sources"]],
        }
        manifest_path.write_text(_canonical(manifest) + "\n", encoding="utf-8", newline="\n")
        for path in (json_path, markdown_path, manifest_path, api_path):
            self._assert_safe(path.read_bytes())
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(final)
        final_json = final / json_path.name
        final_markdown = final / markdown_path.name
        final_manifest = final / manifest_path.name
        verified = json.loads(final_manifest.read_text("utf-8"))
        if (
            self._file_hash(final_json) != verified["json"]["sha256"]
            or self._file_hash(final_markdown) != verified["markdown"]["sha256"]
        ):
            raise BugArtifactError("BUG_MANIFEST_HASH_INVALID")
        return {
            "bundle": final.relative_to(PROJECT_ROOT).as_posix(),
            "json": final_json.relative_to(PROJECT_ROOT).as_posix(),
            "json_hash": self._file_hash(final_json),
            "markdown": final_markdown.relative_to(PROJECT_ROOT).as_posix(),
            "markdown_hash": self._file_hash(final_markdown),
            "manifest": final_manifest.relative_to(PROJECT_ROOT).as_posix(),
            "manifest_hash": self._file_hash(final_manifest),
        }

    @staticmethod
    def _markdown(canonical: dict[str, Any], final_dir: Path) -> str:
        source_lines: list[str] = []
        attachment_lines: list[str] = []
        for source in canonical["sources"]:
            source_lines.append(
                f"- `{source['executor']}`: `{source['case_id']}` v{source['case_version']} → "
                f"`{source['result_id']}`"
            )
            for evidence in source["evidence"]:
                path = evidence["relative_path"]
                link = os.path.relpath(PROJECT_ROOT / path, final_dir).replace("\\", "/")
                attachment_lines.append(
                    f"- [{evidence['kind']}]({link}) — `{evidence['content_hash']}`"
                )
        return "\n".join(
            [
                f"# {canonical['bug_id']}",
                "",
                "## 基本信息",
                f"- 标题：{canonical['title']}",
                f"- 状态：{canonical['status']}",
                f"- 严重程度 / 优先级：{canonical['severity']} / {canonical['priority']}",
                f"- 版本：v{canonical['bug_version']} ({canonical['schema_version']})",
                "",
                "## 关联需求",
                *[f"- `{item}`" for item in canonical["requirement_ids"]],
                "",
                "## 影响范围",
                "注册API和React注册页面均接受不满足最小长度要求的用户名。",
                "",
                "## 测试环境",
                f"- Environment: `{canonical['environment']['environment_id']}`",
                f"- Frozen baseline: `{canonical['environment']['frozen_baseline_id']}`",
                "",
                "## 前置条件",
                *[f"- {item}" for item in canonical["preconditions"]],
                "",
                "## 复现步骤",
                *[
                    f"{index}. {item}"
                    for index, item in enumerate(canonical["reproduction_steps"], 1)
                ],
                "",
                "## 预期结果",
                canonical["expected_result"],
                "",
                "## 实际结果",
                canonical["actual_result"],
                "",
                "## API证据 / UI证据",
                *source_lines,
                "",
                "## 失败分类",
                f"`{canonical['failure_classification']}`（确定性、权威）",
                "",
                "## 附件与Hash",
                *attachment_lines,
                "",
                "## 追踪链路",
                "PRD → Requirement → Frozen Case Version → Execution Result → Evidence → "
                "Classification → Bug",
                "",
                "## 已知边界",
                "本地Bug单，不包含外部平台推送；AI建议为空且不参与Bug真实性判定。",
                "",
            ]
        )

    @staticmethod
    def _assert_safe(content: bytes) -> None:
        lowered = content.lower()
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            raise BugArtifactError("BUG_ARTIFACT_SENSITIVE_CONTENT")
        if str(PROJECT_ROOT).encode().lower() in lowered:
            raise BugArtifactError("BUG_ARTIFACT_ABSOLUTE_PATH")

    @staticmethod
    def _sha(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
