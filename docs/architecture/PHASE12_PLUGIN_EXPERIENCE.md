# Phase 12 Plugin Experience

Status: implemented

The Phase 12 React workspace turns accepted Plugin records into nine portfolio-facing product
areas. A read-only `GET /api/v1/workspace` endpoint selects authoritative accepted records and
returns presentation-safe aggregates; it never starts runs or mutates review, execution, evidence,
Bug, report, or regression data.

The interface provides Mission Control, PRD Scanner, Requirement Constellation, Test Forge,
Execution Arena, Evidence Vault, Bug Archive, Quality Observatory, and Regression Portal routes.
All KPI cards, status charts, accessible tables, hashes, IDs, and lifecycle decisions use the same
database snapshot. Historical failed attempts remain visible where relevant, while gate status is
derived from accepted promoted outputs rather than whichever attempt happened to be newest.

The shell uses React Router deep links, an Axios API boundary, Ant Design theme tokens, a fixed
desktop navigation and mobile drawer, skip navigation, visible focus, non-color status labels,
responsive tables, and reduced-motion support. Charts include source-equivalent accessible tables.
The Vite development proxy connects `/api` to the local Plugin backend on port 5002.

Generated build files, screenshots, runtime evidence, databases, and secrets remain ignored. Phase
13 end-to-end orchestration is not implemented or started.
