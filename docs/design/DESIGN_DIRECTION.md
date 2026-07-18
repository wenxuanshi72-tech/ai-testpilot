# Product Design Direction

Status: Phase 0 design direction only. No React component, page, visual asset, or design dependency is created in this phase.

## Concept, goals, and users

AI TestPilot is a **Quality Mission Control / Test Exploration Lab**: a professional testing workspace whose restrained mission metaphor clarifies progress, risk, evidence, and traceability. It must feel distinctive enough for a portfolio while remaining fast, credible, accessible, and data-dense enough for QA engineers, SDETs, full-stack engineers, test leads, and technical reviewers.

Design goals are to make the lifecycle visible, separate AI proposals from deterministic facts, keep blockers actionable, expose provenance/evidence, support keyboard-first work, and guide a repeatable demonstration without hiding ordinary navigation.

Visual keywords: precise, exploratory, calm, technical, luminous, layered, trustworthy, auditable, and purposeful. Avoid childish science fiction and visual noise.

## Information architecture and navigation

A persistent left navigation provides the nine product areas; a top context bar selects project/environment and exposes provider mode, global task state, help, and user controls. Breadcrumbs and stable page titles preserve location. A command/search surface accelerates navigation but never replaces visible menus. A right-side inspector may show selected-object detail/provenance without forcing route changes.

1. **Mission Control** — project health, phase/gate state, active tasks, latest runs, risk summary, and next action.
2. **PRD Scanner** — upload/version selection, source preview, outline, provider attribution, batch progress, validation/quarantine, and retry controls.
3. **Requirement Constellation** — requirements, source anchors, relationships, risks, testability, review state, and accessible table alternative.
4. **Test Forge** — API/UI/manual drafts, schema issues, diffs, human review, approval, and version freeze.
5. **Execution Arena** — run configuration, approved snapshot, API/UI progress, deterministic results, and cancellation/retry boundaries.
6. **Evidence Vault** — evidence metadata, redacted previews, hashes, retention, and result/bug links.
7. **Bug Archive** — canonical local bug records, severity/priority, linked evidence, status, and export files.
8. **Quality Observatory** — trend/coverage/state charts, trace completeness, report versions, and accessible data tables.
9. **Regression Portal** — baseline/fix comparison, case-version parity, changed evidence, and closure decision.

## Key user flow

The primary demonstration follows visible checkpoints:

`Create/select project -> Import PRD -> Observe real-provider batches -> Review requirements -> Generate/review/freeze tests -> Run API then UI checks -> Inspect deterministic failure/evidence -> Generate local bug/report -> Apply authorized fix -> Rerun approved cases -> Compare regression`.

At every step, the interface states whether data is draft, AI-generated, mock/real, validated, approved, running, or authoritative. Deep links return reviewers to the source requirement and evidence.

## Design system direction

Use reusable semantic tokens and accessible components rather than page-specific styling. Ant Design supplies robust interaction primitives; a project theme shapes density, hierarchy, surfaces, focus, and charts without fighting component semantics.

### Color

Base surfaces use deep neutral navy/slate or an equally legible light counterpart, with restrained cool blue/cyan for navigation and interactive focus. A subtle violet accent may identify AI candidate content. Gradients are limited to orientation/progress surfaces, never body text or status meaning.

Status color is redundant with icon, label, and pattern:

- `PASS`: green/teal, positive check; never the general brand color.
- `FAIL`: red, assertion/product mismatch.
- `BLOCKED`: amber, unmet environment/precondition.
- `ERROR`: magenta/deep orange-red, system/executor malfunction and visually distinct from FAIL.
- `SKIPPED`: neutral gray.
- Risk: low blue/green, medium amber, high red, critical deep red; exact palettes must meet contrast targets.

Do not rely on color alone. Provider mode uses explicit text badges (`REAL`/`MOCK`) and provenance, not only hue.

### Typography

Use a highly legible system/UI sans stack for all product text and a carefully limited monospaced stack for IDs, JSON, hashes, and timings. Avoid decorative/art fonts. Recommended hierarchy uses a small number of sizes/weights, tabular numerals for metrics, readable line length, and at least 16px-equivalent body text where practical.

### Spacing, grid, and depth

Adopt a 4px base scale with primary increments of 8px. Desktop uses a responsive 12-column grid, consistent content maximums, and dense-but-breathable tables; tablet reflows to 8 columns and mobile to 4. Critical actions and filters remain near the relevant content.

Use three elevation levels: base canvas, working surface, and temporary overlay/inspector. Borders and tonal separation provide most hierarchy; shadows and glass effects are restrained. Never stack translucent panels until text/controls lose contrast.

### Cards and panels

Cards summarize one actionable concept and link to detail; they do not repeat all table content. Panels have a clear title, state/provenance, primary action, and optional help. Large datasets use tables or lists with filters, pagination/virtualization, column controls, and export—not endless dashboard cards.

## Data visualization

Charts answer an explicit question, show denominator/time range/source, and have a table alternative. Use bars for comparisons, lines for time, heatmaps for risk/coverage, and node-link views only when relationships are genuinely important. Avoid 3D, decorative gauges, misleading area, excessive pie charts, and animation that changes perceived values.

Requirement Constellation can use a spatial graph, but search, filters, selection details, and a sortable table must expose the same information. “Quality energy” is a labelled composite summary with visible components, never a replacement for pass rate, coverage, or blockers.

## Motion and feedback

Motion explains state change: batch enters validation, evidence is secured, a panel expands, or a run advances. Use short 120–240ms transitions, no continuous ambient movement, and no celebratory effect for sensitive/failing test work. Respect `prefers-reduced-motion`; essential progress remains understandable without animation.

- Loading: skeletons for stable layouts, determinate progress when counts exist, current batch/stage and elapsed time for long tasks, cancel/retry when safe.
- Empty: explain why no data exists, prerequisites, and one appropriate next action; never fabricate sample metrics in a real project view.
- Error: name the failed stage, impact, request/correlation ID, retryability, and safe recovery; preserve completed batches.
- Success: concise confirmation plus created version/artifact and next action; success never implies test PASS unless deterministic results say so.

## Responsive behavior

Desktop supports split views and dense comparisons. Tablet collapses inspectors into drawers. Mobile prioritizes status, review, evidence metadata, and essential controls; complex graphs become lists/tables and large matrices use focused drill-down. No required action depends on hover. Touch targets remain comfortably sized.

## Accessibility

- Meet WCAG 2.2 AA contrast, focus visibility, semantic headings, landmarks, labels, error association, and screen-reader status announcements.
- All navigation, dialogs, tables, graph selections, review actions, and execution controls are keyboard operable with logical focus order and escape behavior.
- Offer reduced motion, chart/table alternatives, non-color status cues, zoom/reflow support, accessible names for icons, and captions/descriptions for evidence.
- Preserve native semantics through Ant Design customization and test with keyboard plus representative assistive technology.

## Portfolio capture scenarios

Curated screenshots must use safe example or genuinely executed redacted data and visibly label provider/result provenance:

1. Mission Control showing the end-to-end mission path and honest gate status.
2. PRD Scanner showing bounded real-provider batches and validation states.
3. Requirement Constellation plus its accessible table and risk filters.
4. Test Forge diff/review of API and UI cases.
5. Execution Arena exposing the seeded defect with deterministic status.
6. Evidence Vault linking screenshot/trace/request evidence.
7. Bug Archive and Quality Observatory with reconciled local artifacts.
8. Regression Portal comparing immutable before/after runs.

Capture desktop and one responsive view, plus loading/error/empty states where they demonstrate engineering maturity. Never create a screenshot that implies an unperformed model call or test.

## Demonstration flow

A 5–8 minute guided demo should introduce the problem, import the PRD, point out real-provider identity and resumable batches, approve traceable requirements/cases, execute API and UI checks, inspect the protected failure and evidence, open local bug/report artifacts, then show an authorized regression comparison. The presenter can drill into IDs and request/correlation links without leaving the main flow.

## Prohibited patterns

- Generic rigid admin-template appearance with interchangeable KPI cards.
- Childish cartoons, excessive neon, low contrast, unreadable display fonts, or meaningless ambient animation.
- Visual metaphors that conceal raw status, IDs, evidence, filters, or navigation.
- Beauty at the expense of task speed, keyboard access, responsive behavior, or data density.
- A static portfolio mockup without working product behavior.
- AI glow or celebratory motion used to imply correctness before deterministic validation.

Gamification remains a navigational and progress language serving professional testing information; it is never the product's authority or purpose.
