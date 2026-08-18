from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import text

from plugin.backend.app.api_execution import _canonical, _utc_timestamp
from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.test_review import _hash

REPORT_SCHEMA_VERSION = "canonical-test-report@1.0.0"
REPORT_BUNDLE_VERSION = "test-report-bundle@1.0.0"
SENSITIVE_MARKERS = (
    b"test1234",
    b"authorization: bearer",
    b"session token",
    b"cookie:",
    b"sqlite:///",
    b"deepseek_api_key",
)


class TestReportError(Exception):
    pass


class TestReportService:
    def __init__(self, database: PluginDatabase, *, artifact_root: Path | None = None) -> None:
        self.database = database
        self.artifact_root = artifact_root or PROJECT_ROOT / "artifacts" / "reports"
        schema_path = (
            PROJECT_ROOT / "schemas" / "reports" / "v1" / "canonical_test_report.schema.json"
        )
        self.validator = Draft202012Validator(json.loads(schema_path.read_text("utf-8")))

    def generate(self, consolidation_run_id: str, bug_record_id: str) -> dict[str, Any]:
        existing = self.database.fetch_one(
            "SELECT canonical_test_report_id FROM canonical_test_reports "
            "WHERE evidence_consolidation_run_id=:run AND canonical_bug_record_id=:bug",
            {"run": consolidation_run_id, "bug": bug_record_id},
        )
        if existing:
            return self.get(str(existing["canonical_test_report_id"]))
        context = self._context(consolidation_run_id, bug_record_id)
        created_at = _utc_timestamp()
        stamp = created_at.replace("-", "").replace(":", "").replace(".", "")
        basename = f"test-report--v1--{stamp}"
        final_dir = self.artifact_root / basename
        staging_dir = self.artifact_root / f".{basename}.staging-{new_id('TMP')}"
        results = self._results(context, final_dir)
        canonical = self._canonical_report(context, results, created_at)
        errors = sorted(self.validator.iter_errors(canonical), key=lambda error: list(error.path))
        if errors:
            raise TestReportError(f"CANONICAL_REPORT_SCHEMA_INVALID:{errors[0].json_path}")
        self._assert_safe(_canonical(canonical).encode())
        try:
            bundle = self._write_bundle(staging_dir, final_dir, basename, canonical, results)
            report_id = new_id("RPT")
            with self.database.transaction() as connection:
                connection.execute(
                    text(
                        "INSERT INTO canonical_test_reports(canonical_test_report_id,"
                        "report_version,project_id,frozen_baseline_id,api_test_run_id,ui_test_run_id,"
                        "evidence_consolidation_run_id,canonical_bug_record_id,schema_version,status,"
                        "canonical_json,canonical_hash,created_at) VALUES "
                        "(:id,1,:project,:baseline,:api,:ui,:evidence,:bug,:schema,'completed',"
                        ":payload,:hash,:created)"
                    ),
                    {
                        "id": report_id,
                        "project": context["project_id"],
                        "baseline": context["frozen_baseline_id"],
                        "api": context["api_test_run_id"],
                        "ui": context["ui_test_run_id"],
                        "evidence": consolidation_run_id,
                        "bug": bug_record_id,
                        "schema": REPORT_SCHEMA_VERSION,
                        "payload": _canonical(canonical),
                        "hash": _hash(canonical),
                        "created": created_at,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO test_report_artifact_bundles(test_report_artifact_bundle_id,"
                        "canonical_test_report_id,format_version,bundle_path,json_path,json_hash,"
                        "markdown_path,markdown_hash,html_path,html_hash,pdf_path,pdf_hash,"
                        "manifest_path,manifest_hash,status,created_at) VALUES "
                        "(:id,:report,:format,:bundle,:json,:json_hash,:markdown,:markdown_hash,"
                        ":html,:html_hash,:pdf,:pdf_hash,:manifest,:manifest_hash,'completed',:created)"
                    ),
                    {
                        "id": new_id("RPB"),
                        "report": report_id,
                        "format": REPORT_BUNDLE_VERSION,
                        **bundle,
                        "created": created_at,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO test_report_audit_events(test_report_audit_event_id,"
                        "canonical_test_report_id,event_type,details_json) VALUES "
                        "(:id,:report,'test_report_generated',:details)"
                    ),
                    {
                        "id": new_id("RPA"),
                        "report": report_id,
                        "details": _canonical(
                            {
                                "result_count": canonical["summary"]["total"],
                                "evidence_count": canonical["evidence_count"],
                                "bug_count": len(canonical["bugs"]),
                                "verdict_recalculation_count": 0,
                            }
                        ),
                    },
                )
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        return self.get(report_id)

    def get(self, report_id: str) -> dict[str, Any]:
        record = self.database.fetch_one(
            "SELECT * FROM canonical_test_reports WHERE canonical_test_report_id=:id",
            {"id": report_id},
        )
        if not record:
            raise TestReportError("TEST_REPORT_NOT_FOUND")
        bundle = self.database.fetch_one(
            "SELECT * FROM test_report_artifact_bundles WHERE canonical_test_report_id=:id",
            {"id": report_id},
        )
        return {
            **{key: value for key, value in record.items() if key != "canonical_json"},
            "canonical_report": json.loads(str(record["canonical_json"])),
            "bundle": bundle,
        }

    def _context(self, consolidation_run_id: str, bug_record_id: str) -> dict[str, Any]:
        context = self.database.fetch_one(
            "SELECT e.*,a.environment_id AS api_environment,u.environment_id AS ui_environment,"
            "a.status AS api_status,u.status AS ui_status,b.project_id,b.bug_id,b.bug_version,"
            "b.canonical_bug_record_id,b.status AS bug_status,b.canonical_json AS bug_json,"
            "b.canonical_hash AS bug_hash "
            "FROM evidence_consolidation_runs e JOIN api_test_runs a ON "
            "a.api_test_run_id=e.api_test_run_id JOIN ui_test_runs u ON "
            "u.ui_test_run_id=e.ui_test_run_id JOIN canonical_bug_records b ON "
            "b.evidence_consolidation_run_id=e.evidence_consolidation_run_id "
            "WHERE e.evidence_consolidation_run_id=:run AND b.canonical_bug_record_id=:bug",
            {"run": consolidation_run_id, "bug": bug_record_id},
        )
        if not context:
            raise TestReportError("REPORT_SOURCE_TRACE_INVALID")
        if (
            context["status"] != "completed"
            or context["api_status"] != "completed"
            or context["ui_status"] != "completed"
            or context["api_environment"] != context["ui_environment"]
        ):
            raise TestReportError("REPORT_SOURCE_NOT_COMPLETED")
        bug = json.loads(str(context["bug_json"]))
        if _hash(bug) != context["bug_hash"] or context["bug_id"] != "BUG-AUTH-001":
            raise TestReportError("REPORT_BUG_HASH_INVALID")
        return {**context, "bug": bug}

    def _results(self, context: dict[str, Any], final_dir: Path) -> list[dict[str, Any]]:
        classifications = self.database.fetch_all(
            "SELECT * FROM deterministic_failure_classifications "
            "WHERE evidence_consolidation_run_id=:run ORDER BY source_executor,case_id",
            {"run": context["evidence_consolidation_run_id"]},
        )
        if len(classifications) != int(context["result_count"]):
            raise TestReportError("REPORT_RESULT_SET_INCOMPLETE")
        results: list[dict[str, Any]] = []
        for classification in classifications:
            executor = str(classification["source_executor"])
            table = "api_test_results" if executor == "api" else "ui_test_results"
            id_column = "api_test_result_id" if executor == "api" else "ui_test_result_id"
            source = self.database.fetch_one(
                f"SELECT * FROM {table} WHERE {id_column}=:id",  # noqa: S608 - fixed allowlist
                {"id": classification["source_result_id"]},
            )
            if not source or source["status"] != classification["verdict"]:
                raise TestReportError("REPORT_VERDICT_TRACE_INVALID")
            evidence_rows = self.database.fetch_all(
                "SELECT * FROM consolidated_evidence_records WHERE "
                "evidence_consolidation_run_id=:run AND source_executor=:executor "
                "AND source_result_id=:result ORDER BY evidence_kind",
                {
                    "run": context["evidence_consolidation_run_id"],
                    "executor": executor,
                    "result": classification["source_result_id"],
                },
            )
            if not evidence_rows:
                raise TestReportError("REPORT_EVIDENCE_MISSING")
            evidence = [self._evidence(row, final_dir) for row in evidence_rows]
            expected = source["expected_status"] if executor == "api" else source["expected_route"]
            actual = source["actual_status"] if executor == "api" else source["actual_route"]
            results.append(
                {
                    "executor": executor,
                    "case_id": source["case_id"],
                    "case_version": int(source["case_version"]),
                    "result_id": classification["source_result_id"],
                    "verdict": classification["verdict"],
                    "classification": classification["classification_code"],
                    "expected": expected,
                    "actual": actual,
                    "bug_id": classification["suspected_bug_id"],
                    "evidence": evidence,
                }
            )
        return results

    def _evidence(self, row: dict[str, Any], final_dir: Path) -> dict[str, Any]:
        if row["integrity_status"] != "verified" or row["redaction_status"] != "verified":
            raise TestReportError("REPORT_EVIDENCE_NOT_VERIFIED")
        if row["evidence_kind"] == "api_exchange":
            source = self.database.fetch_one(
                "SELECT evidence_json,evidence_hash FROM api_test_evidence "
                "WHERE api_test_evidence_id=:id",
                {"id": row["source_evidence_id"]},
            )
            if not source:
                raise TestReportError("REPORT_EVIDENCE_SOURCE_MISSING")
            content = _canonical(json.loads(str(source["evidence_json"]))).encode()
            if (
                self._sha(content) != row["content_hash"]
                or source["evidence_hash"] != row["content_hash"]
            ):
                raise TestReportError("REPORT_EVIDENCE_HASH_INVALID")
            relative = (
                final_dir.relative_to(PROJECT_ROOT)
                / "evidence"
                / f"{row['case_id']}--api-exchange.json"
            ).as_posix()
            return {
                "evidence_id": row["source_evidence_id"],
                "kind": row["evidence_kind"],
                "relative_path": relative,
                "content_hash": row["content_hash"],
                "_content": content,
            }
        relative = str(row["relative_path"])
        path = (PROJECT_ROOT / relative).resolve()
        root = (PROJECT_ROOT / "artifacts" / "evidence").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise TestReportError("REPORT_EVIDENCE_PATH_INVALID")
        content = path.read_bytes()
        if self._sha(content) != row["content_hash"]:
            raise TestReportError("REPORT_EVIDENCE_HASH_INVALID")
        self._assert_safe(content)
        return {
            "evidence_id": row["source_evidence_id"],
            "kind": row["evidence_kind"],
            "relative_path": relative,
            "content_hash": row["content_hash"],
        }

    @staticmethod
    def _canonical_report(
        context: dict[str, Any], results: list[dict[str, Any]], created_at: str
    ) -> dict[str, Any]:
        verdicts = Counter(result["verdict"] for result in results)
        classifications = Counter(result["classification"] for result in results)
        clean_results = [
            {
                **{key: value for key, value in result.items() if key != "evidence"},
                "evidence": [
                    {key: value for key, value in item.items() if not key.startswith("_")}
                    for item in result["evidence"]
                ],
            }
            for result in results
        ]
        bug = context["bug"]
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "report_version": 1,
            "title": "AI TestPilot Authentication MVP - Test Execution Report",
            "status": "completed",
            "project_id": context["project_id"],
            "sources": {
                "frozen_baseline_id": context["frozen_baseline_id"],
                "api_run_id": context["api_test_run_id"],
                "ui_run_id": context["ui_test_run_id"],
                "evidence_consolidation_run_id": context["evidence_consolidation_run_id"],
                "canonical_bug_record_id": context["canonical_bug_record_id"],
            },
            "summary": {
                "total": len(results),
                "pass": verdicts["PASS"],
                "fail": verdicts["FAIL"],
                "blocked": verdicts["BLOCKED"],
                "error": verdicts["ERROR"],
                "skipped": verdicts["SKIPPED"],
                "api_total": sum(item["executor"] == "api" for item in results),
                "ui_total": sum(item["executor"] == "ui" for item in results),
            },
            "classifications": dict(sorted(classifications.items())),
            "results": clean_results,
            "bugs": [
                {
                    "bug_id": bug["bug_id"],
                    "bug_version": bug["bug_version"],
                    "status": bug["status"],
                    "record_id": context["canonical_bug_record_id"],
                    "title": bug["title"],
                }
            ],
            "evidence_count": sum(len(result["evidence"]) for result in results),
            "created_at": created_at,
        }

    def _write_bundle(
        self,
        staging: Path,
        final: Path,
        basename: str,
        canonical: dict[str, Any],
        raw_results: list[dict[str, Any]],
    ) -> dict[str, str]:
        staging.mkdir(parents=True, exist_ok=False)
        evidence_dir = staging / "evidence"
        evidence_dir.mkdir()
        for result in raw_results:
            for evidence in result["evidence"]:
                if evidence["kind"] == "api_exchange":
                    path = evidence_dir / f"{result['case_id']}--api-exchange.json"
                    path.write_bytes(evidence["_content"])
        paths = {
            "json": staging / f"{basename}.json",
            "markdown": staging / f"{basename}.md",
            "html": staging / f"{basename}.html",
            "pdf": staging / f"{basename}.pdf",
            "manifest": staging / "manifest.json",
        }
        paths["json"].write_text(_canonical(canonical) + "\n", encoding="utf-8", newline="\n")
        paths["markdown"].write_text(
            self._markdown(canonical, final), encoding="utf-8", newline="\n"
        )
        paths["html"].write_text(self._html(canonical, final), encoding="utf-8", newline="\n")
        self._pdf(canonical, final, paths["pdf"])
        manifest = {
            "format_version": REPORT_BUNDLE_VERSION,
            "report_version": canonical["report_version"],
            "created_at": canonical["created_at"],
            "summary": canonical["summary"],
            "classifications": canonical["classifications"],
            "bug_ids": [bug["bug_id"] for bug in canonical["bugs"]],
            "evidence_count": canonical["evidence_count"],
            "files": {
                name: {"path": path.name, "sha256": self._file_hash(path)}
                for name, path in paths.items()
                if name != "manifest"
            },
            "evidence": [
                evidence for result in canonical["results"] for evidence in result["evidence"]
            ],
        }
        paths["manifest"].write_text(_canonical(manifest) + "\n", encoding="utf-8", newline="\n")
        for path in [*paths.values(), *evidence_dir.iterdir()]:
            self._assert_safe(path.read_bytes())
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(final)
        output: dict[str, str] = {"bundle": final.relative_to(PROJECT_ROOT).as_posix()}
        for name, original in paths.items():
            path = final / original.name
            output[name] = path.relative_to(PROJECT_ROOT).as_posix()
            output[f"{name}_hash"] = self._file_hash(path)
        verified = json.loads((final / "manifest.json").read_text("utf-8"))
        for name in ("json", "markdown", "html", "pdf"):
            if output[f"{name}_hash"] != verified["files"][name]["sha256"]:
                raise TestReportError("REPORT_MANIFEST_HASH_INVALID")
        return output

    @classmethod
    def _markdown(cls, report: dict[str, Any], final_dir: Path) -> str:
        summary = report["summary"]
        lines = [
            f"# {report['title']}",
            "",
            "## Executive Summary",
            f"- Total: {summary['total']}",
            f"- PASS: {summary['pass']}",
            f"- FAIL: {summary['fail']}",
            "- BLOCKED / ERROR / SKIPPED: "
            f"{summary['blocked']} / {summary['error']} / {summary['skipped']}",
            f"- API / UI: {summary['api_total']} / {summary['ui_total']}",
            f"- Evidence: {report['evidence_count']}",
            "",
            "## Failure Classification",
            *[f"- `{key}`: {value}" for key, value in report["classifications"].items()],
            "",
            "## Formal Bugs",
            *[
                f"- `{bug['bug_id']}` v{bug['bug_version']} - {bug['status']} - {bug['title']}"
                for bug in report["bugs"]
            ],
            "",
            "## Results",
            "| Executor | Case | Version | Verdict | Classification | Expected | Actual | Bug |",
            "|---|---|---:|---|---|---|---|---|",
        ]
        for result in report["results"]:
            lines.append(
                f"| {result['executor']} | `{result['case_id']}` | {result['case_version']} | "
                f"{result['verdict']} | {result['classification']} | {result['expected']} | "
                f"{result['actual']} | {result['bug_id'] or '-'} |"
            )
        lines.extend(["", "## Evidence Index"])
        for result in report["results"]:
            lines.append(f"### {result['case_id']}")
            for evidence in result["evidence"]:
                link = cls._relative_link(final_dir, evidence["relative_path"])
                lines.append(f"- [{evidence['kind']}]({link}) - `{evidence['content_hash']}`")
        lines.extend(
            [
                "",
                "## Traceability",
                "Frozen baseline -> API/UI runs -> deterministic results -> evidence -> "
                "classification -> BUG-AUTH-001 -> this report.",
                "",
                "## Boundaries",
                "Verdicts and classifications are reproduced from persisted authoritative records. "
                "No regression run, defect repair, model verdict, or external publication "
                "occurred.",
                "",
            ]
        )
        return "\n".join(lines)

    @classmethod
    def _html(cls, report: dict[str, Any], final_dir: Path) -> str:
        def esc(value: Any) -> str:
            return html.escape(str(value), quote=True)

        rows = "".join(
            "<tr>"
            + "".join(
                f"<td>{esc(value)}</td>"
                for value in (
                    item["executor"],
                    item["case_id"],
                    item["case_version"],
                    item["verdict"],
                    item["classification"],
                    item["expected"],
                    item["actual"],
                    item["bug_id"] or "-",
                )
            )
            + "</tr>"
            for item in report["results"]
        )
        evidence_sections = []
        for result in report["results"]:
            links = "".join(
                f'<li><a href="{esc(cls._relative_link(final_dir, evidence["relative_path"]))}">'
                f"{esc(evidence['kind'])}</a> - <code>{esc(evidence['content_hash'])}</code></li>"
                for evidence in result["evidence"]
            )
            evidence_sections.append(f"<h3>{esc(result['case_id'])}</h3><ul>{links}</ul>")
        summary = report["summary"]
        bug = report["bugs"][0]
        css = "".join(
            [
                "body{font:16px/1.5 system-ui,sans-serif;color:#172033;background:#fff;margin:0}",
                "main{max-width:1100px;margin:auto;padding:2rem}a{color:#0645ad}",
                "a:focus{outline:3px solid #f59e0b}.skip{position:absolute;left:-9999px}",
                ".skip:focus{left:1rem;top:1rem;background:#fff;padding:.5rem}",
                ".cards{display:flex;gap:1rem;flex-wrap:wrap}",
                ".card{border:1px solid #b8c2d1;border-radius:.5rem;padding:1rem;min-width:8rem}",
                "table{border-collapse:collapse;width:100%}",
                "th,td{border:1px solid #9aa7b8;padding:.5rem;text-align:left}",
                "th{background:#e8eef7}code{overflow-wrap:anywhere}",
                "@media print{.skip{display:none}main{padding:0}}",
            ]
        )
        cards = "".join(
            f'<div class="card"><strong>{label}</strong><br>{value}</div>'
            for label, value in (
                ("Total", summary["total"]),
                ("PASS", summary["pass"]),
                ("FAIL", summary["fail"]),
                ("Evidence", report["evidence_count"]),
            )
        )
        headers = "".join(
            f'<th scope="col">{label}</th>'
            for label in (
                "Executor",
                "Case",
                "Version",
                "Verdict",
                "Classification",
                "Expected",
                "Actual",
                "Bug",
            )
        )
        return "\n".join(
            [
                "<!doctype html>",
                '<html lang="en"><head><meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width,initial-scale=1">',
                f"<title>{esc(report['title'])}</title><style>{css}</style></head><body>",
                '<a class="skip" href="#main">Skip to report</a><main id="main">',
                f"<h1>{esc(report['title'])}</h1>",
                '<section aria-labelledby="summary"><h2 id="summary">Executive Summary</h2>',
                f'<div class="cards">{cards}</div></section>',
                '<section aria-labelledby="bugs"><h2 id="bugs">Formal Bugs</h2><ul>',
                f"<li><strong>{esc(bug['bug_id'])}</strong> v{bug['bug_version']} - "
                f"{esc(bug['title'])}</li></ul></section>",
                '<section aria-labelledby="results"><h2 id="results">Results</h2>',
                '<div role="region" aria-label="Execution results" tabindex="0"><table>',
                "<caption>Persisted deterministic API and UI results</caption>"
                f"<thead><tr>{headers}",
                f"</tr></thead><tbody>{rows}</tbody></table></div></section>",
                '<section aria-labelledby="evidence"><h2 id="evidence">Evidence Index</h2>',
                f"{''.join(evidence_sections)}</section>",
                '<section aria-labelledby="boundary"><h2 id="boundary">Boundaries</h2>',
                "<p>Verdicts and classifications are reproduced from persisted authoritative "
                "records. No regression run, defect repair, model verdict, or external "
                "publication occurred.</p></section>",
                "</main></body></html>",
            ]
        )

    @classmethod
    def _pdf(cls, report: dict[str, Any], final_dir: Path, path: Path) -> None:
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="ReportTitle",
                parent=styles["Title"],
                textColor=colors.HexColor("#17365D"),
                alignment=TA_CENTER,
                spaceAfter=12,
            )
        )
        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            rightMargin=16 * mm,
            leftMargin=16 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=report["title"],
            author="AI TestPilot",
        )
        story: list[Any] = [Paragraph(html.escape(report["title"]), styles["ReportTitle"])]
        summary = report["summary"]
        summary_table = Table(
            [
                ["Total", "PASS", "FAIL", "Blocked", "Error", "Skipped", "Evidence"],
                [
                    summary["total"],
                    summary["pass"],
                    summary["fail"],
                    summary["blocked"],
                    summary["error"],
                    summary["skipped"],
                    report["evidence_count"],
                ],
            ],
            repeatRows=1,
        )
        summary_table.setStyle(cls._table_style())
        story.extend(
            [Paragraph("Executive Summary", styles["Heading2"]), summary_table, Spacer(1, 8)]
        )
        bug = report["bugs"][0]
        story.extend(
            [
                Paragraph("Formal Bug", styles["Heading2"]),
                Paragraph(
                    f"<b>{html.escape(bug['bug_id'])}</b> v{bug['bug_version']} - "
                    f"{html.escape(bug['title'])}",
                    styles["BodyText"],
                ),
                Spacer(1, 8),
                Paragraph("Execution Results", styles["Heading2"]),
            ]
        )
        data: list[list[Any]] = [
            ["Type", "Case", "Verdict", "Classification", "Expected", "Actual", "Bug"]
        ]
        for result in report["results"]:
            data.append(
                [
                    result["executor"].upper(),
                    Paragraph(result["case_id"], styles["BodyText"]),
                    result["verdict"],
                    Paragraph(result["classification"], styles["BodyText"]),
                    str(result["expected"]),
                    str(result["actual"]),
                    result["bug_id"] or "-",
                ]
            )
        results_table = Table(
            data,
            colWidths=[12 * mm, 43 * mm, 15 * mm, 30 * mm, 19 * mm, 19 * mm, 25 * mm],
            repeatRows=1,
        )
        results_table.setStyle(cls._table_style())
        story.extend([results_table, PageBreak(), Paragraph("Evidence Index", styles["Heading2"])])
        for result in report["results"]:
            story.append(Paragraph(html.escape(result["case_id"]), styles["Heading3"]))
            for evidence in result["evidence"]:
                link = cls._relative_link(final_dir, evidence["relative_path"])
                story.append(
                    Paragraph(
                        f'{html.escape(evidence["kind"])}: <link href="{html.escape(link)}">'
                        f'{html.escape(link)}</link><br/><font size="7">SHA-256: '
                        f"{evidence['content_hash']}</font>",
                        styles["BodyText"],
                    )
                )
                story.append(Spacer(1, 4))
        story.extend(
            [
                Paragraph("Traceability and Boundaries", styles["Heading2"]),
                Paragraph(
                    "Frozen baseline -> API/UI runs -> deterministic results -> evidence -> "
                    "classification -> BUG-AUTH-001 -> this report.",
                    styles["BodyText"],
                ),
                Paragraph(
                    "No verdict was recalculated. No regression run, defect repair, model verdict, "
                    "or external publication occurred.",
                    styles["BodyText"],
                ),
            ]
        )

        def footer(canvas: Any, document: Any) -> None:
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#52606D"))
            canvas.drawString(16 * mm, 9 * mm, "AI TestPilot - Canonical Test Report")
            canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {document.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=footer, onLaterPages=footer)

    @staticmethod
    def _table_style() -> TableStyle:
        return TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#172033")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#8A98A8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )

    @staticmethod
    def _relative_link(final_dir: Path, relative: str) -> str:
        return os.path.relpath(PROJECT_ROOT / relative, final_dir).replace("\\", "/")

    @staticmethod
    def _assert_safe(content: bytes) -> None:
        lowered = content.lower()
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            raise TestReportError("REPORT_SENSITIVE_CONTENT")
        if str(PROJECT_ROOT).encode().lower() in lowered:
            raise TestReportError("REPORT_ABSOLUTE_PATH")

    @staticmethod
    def _sha(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
