import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Descriptions,
  Drawer,
  Empty,
  Layout,
  Menu,
  Progress,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { loadWorkspace, type Row, type WorkspaceSnapshot } from "./api";

const { Header, Sider, Content } = Layout;
const { Title, Text, Paragraph } = Typography;

const areas = [
  ["/mission-control", "Mission Control", "MC"],
  ["/prd-scanner", "PRD Scanner", "PS"],
  ["/requirements", "Requirement Constellation", "RC"],
  ["/test-forge", "Test Forge", "TF"],
  ["/execution", "Execution Arena", "EA"],
  ["/evidence", "Evidence Vault", "EV"],
  ["/bugs", "Bug Archive", "BA"],
  ["/quality", "Quality Observatory", "QO"],
  ["/regression", "Regression Portal", "RP"],
] as const;

function display(item: unknown, fallback = "Not available") {
  return typeof item === "string" || typeof item === "number" || typeof item === "boolean"
    ? String(item)
    : fallback;
}

function value(row: Row | null | undefined, key: string, fallback = "Not available") {
  return display(row?.[key], fallback);
}

function StatusTag({ status }: { status: unknown }) {
  const text = display(status, "unknown");
  const color =
    text === "PASS" || text === "completed" || text === "closed"
      ? "green"
      : text === "FAIL" || text === "failed"
        ? "red"
        : text === "open"
          ? "gold"
          : "blue";
  return <Tag color={color}>{text.toUpperCase()}</Tag>;
}

function DataTable({ rows, label }: { rows: Row[]; label: string }) {
  if (!rows.length)
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`No ${label}`} />;
  const keys = Object.keys(rows[0]!)
    .filter((key) => !["payload", "candidate", "requirement"].includes(key))
    .slice(0, 6);
  return (
    <Table<Row>
      rowKey={(row) => display(row.case_id ?? row.requirement_id, JSON.stringify(row))}
      size="small"
      scroll={{ x: true }}
      pagination={{ pageSize: 8, hideOnSinglePage: true }}
      columns={keys.map((key) => ({
        title: key.replaceAll("_", " "),
        dataIndex: key,
        render: (item: unknown) =>
          key === "status" || key === "decision" ? <StatusTag status={item} /> : display(item, "—"),
      }))}
      dataSource={rows}
      aria-label={label}
    />
  );
}

function Panel({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <section className="page-panel" aria-labelledby={`title-${eyebrow}`}>
      <Text className="eyebrow">{eyebrow}</Text>
      <Title id={`title-${eyebrow}`} level={1}>
        {title}
      </Title>
      {children}
    </section>
  );
}

function Mission({ data }: { data: WorkspaceSnapshot }) {
  const statuses = data.metrics.result_statuses;
  const total = Object.values(statuses).reduce((sum, count) => sum + count, 0);
  const pass = statuses.PASS ?? 0;
  return (
    <Panel eyebrow="Live project health" title="Mission Control">
      <div className="metric-grid">
        <Card>
          <Statistic title="Formal requirements" value={data.metrics.requirements} />
        </Card>
        <Card>
          <Statistic title="Test designs" value={data.metrics.candidates} />
        </Card>
        <Card>
          <Statistic title="Frozen snapshots" value={data.metrics.snapshots} />
        </Card>
        <Card>
          <Statistic
            title="Latest pass rate"
            value={total ? Math.round((pass / total) * 100) : 0}
            suffix="%"
          />
        </Card>
      </div>
      <div className="two-column">
        <Card title="Phase and gate status">
          <Descriptions
            column={1}
            size="small"
            items={[
              {
                key: "analysis",
                label: "PRD analysis",
                children: (
                  <StatusTag status={data.metrics.requirements > 0 ? "completed" : "unavailable"} />
                ),
              },
              {
                key: "baseline",
                label: "MVP baseline",
                children: <StatusTag status={data.baseline?.status} />,
              },
              {
                key: "regression",
                label: "Regression",
                children: <StatusTag status={data.regression?.status} />,
              },
            ]}
          />
        </Card>
        <Card title="Next action">
          <Title level={3}>Explore verified quality evidence</Title>
          <Paragraph>
            Review the closed defect trace, compare pre-fix and regression runs, then prepare the
            Phase 13 local-loop rehearsal.
          </Paragraph>
          <Link to="/regression">Open Regression Portal</Link>
        </Card>
      </div>
    </Panel>
  );
}

function PrdScanner({ data }: { data: WorkspaceSnapshot }) {
  const complete = data.analysis.batches.filter((row) => row.status === "completed").length;
  return (
    <Panel eyebrow="Source intelligence" title="PRD Scanner">
      <div className="two-column">
        <Card title="Current PRD">
          <Descriptions
            column={1}
            size="small"
            items={[
              { key: "title", label: "Title", children: value(data.prd, "title") },
              { key: "version", label: "Version", children: value(data.prd, "version_number") },
              {
                key: "hash",
                label: "Content hash",
                children: <Text code>{value(data.prd, "content_hash")}</Text>,
              },
              {
                key: "provider",
                label: "Provider identity",
                children: `${value(data.analysis.run, "provider")} · ${data.meta.provider_mode ?? "unknown"}`,
              },
            ]}
          />
        </Card>
        <Card title="Batch validation">
          <Progress
            percent={
              data.analysis.batches.length
                ? Math.round((complete / data.analysis.batches.length) * 100)
                : 0
            }
          />
          <Paragraph>
            {complete}/{data.analysis.batches.length} batches complete. Retry and isolation states
            remain visible below.
          </Paragraph>
        </Card>
      </div>
      <Card title="Source preview">
        <Paragraph className="source-preview">{value(data.prd, "content_preview")}</Paragraph>
      </Card>
      <Card title="Analysis batches">
        <DataTable rows={data.analysis.batches} label="analysis batches" />
      </Card>
    </Panel>
  );
}

function Requirements({ data }: { data: WorkspaceSnapshot }) {
  return (
    <Panel eyebrow="Traceable specification" title="Requirement Constellation">
      <Alert
        showIcon
        type="info"
        message="Graph and accessible table share the same formal requirement source."
      />
      <div className="constellation" aria-hidden="true">
        {data.requirements.slice(0, 12).map((row) => (
          <span key={String(row.requirement_id)}>{String(row.requirement_id)}</span>
        ))}
      </div>
      <Card title="Accessible requirement table">
        <DataTable rows={data.requirements} label="formal requirements" />
      </Card>
    </Panel>
  );
}

function TestForge({ data }: { data: WorkspaceSnapshot }) {
  const counts = Counter(data.test_forge.candidates.map((row) => String(row.case_type)));
  return (
    <Panel eyebrow="Reviewed test design" title="Test Forge">
      <Space wrap>
        {Object.entries(counts).map(([key, count]) => (
          <Tag key={key}>
            {key}: {count}
          </Tag>
        ))}
      </Space>
      <Card title="Candidates, review and automation disposition">
        <DataTable rows={data.test_forge.candidates} label="test case candidates" />
      </Card>
      <Card title="Human revision history">
        <DataTable rows={data.test_forge.revisions} label="human revisions" />
      </Card>
    </Panel>
  );
}

function Counter(items: string[]) {
  return items.reduce<Record<string, number>>(
    (result, item) => ({ ...result, [item]: (result[item] ?? 0) + 1 }),
    {},
  );
}

function Execution({ data }: { data: WorkspaceSnapshot }) {
  return (
    <Panel eyebrow="Deterministic runtime" title="Execution Arena">
      <div className="two-column">
        <Card title="Frozen baseline">
          <Descriptions
            column={1}
            size="small"
            items={[
              {
                key: "id",
                label: "Baseline",
                children: value(data.baseline, "frozen_baseline_id"),
              },
              {
                key: "hash",
                label: "Hash",
                children: <Text code>{value(data.baseline, "baseline_hash")}</Text>,
              },
              {
                key: "status",
                label: "Lifecycle",
                children: <StatusTag status={data.baseline?.status} />,
              },
            ]}
          />
        </Card>
        <Card title="Latest execution">
          <Space wrap>
            {Object.entries(data.metrics.result_statuses).map(([status, count]) => (
              <Tag key={status}>
                {status}: {count}
              </Tag>
            ))}
          </Space>
        </Card>
      </div>
      <Card title="API results">
        <DataTable rows={data.execution.api_results} label="API results" />
      </Card>
      <Card title="UI results">
        <DataTable rows={data.execution.ui_results} label="UI results" />
      </Card>
    </Panel>
  );
}

function Evidence({ data }: { data: WorkspaceSnapshot }) {
  return (
    <Panel eyebrow="Integrity first" title="Evidence Vault">
      <Alert
        type="success"
        showIcon
        message={`${data.metrics.evidence} redacted evidence records loaded from the accepted consolidation.`}
      />
      <Card title="Evidence metadata and hash verification">
        <DataTable rows={data.evidence.records} label="evidence records" />
      </Card>
      <Card title="Result and Bug classification">
        <DataTable rows={data.evidence.classifications} label="failure classifications" />
      </Card>
    </Panel>
  );
}

function Bugs({ data }: { data: WorkspaceSnapshot }) {
  const bug = data.bug.record;
  return (
    <Panel eyebrow="Local defect history" title="Bug Archive">
      <Card title={value(bug, "bug_id")}>
        <Descriptions
          column={{ xs: 1, md: 2 }}
          items={[
            { key: "version", label: "Version", children: value(bug, "bug_version") },
            { key: "severity", label: "Severity", children: value(bug, "severity") },
            { key: "priority", label: "Priority", children: value(bug, "priority") },
            {
              key: "status",
              label: "Effective status",
              children: (
                <StatusTag status={data.bug.latest_status_event?.to_status ?? bug?.status} />
              ),
            },
            {
              key: "hash",
              label: "Canonical hash",
              children: <Text code>{value(bug, "canonical_hash")}</Text>,
            },
          ]}
        />
        <Paragraph>
          API and UI source failures remain immutable. JSON and Markdown exports are generated from
          one canonical record.
        </Paragraph>
        <Descriptions
          column={1}
          size="small"
          items={[
            { key: "json", label: "Local JSON", children: value(data.bug.bundle, "json_path") },
            {
              key: "markdown",
              label: "Local Markdown",
              children: value(data.bug.bundle, "markdown_path"),
            },
          ]}
        />
      </Card>
    </Panel>
  );
}

function Quality({ data }: { data: WorkspaceSnapshot }) {
  const rows = Object.entries(data.metrics.result_statuses).map(([status, count]) => ({
    status,
    count,
  }));
  return (
    <Panel eyebrow="Source-backed metrics" title="Quality Observatory">
      <div className="metric-grid">
        <Card>
          <Statistic title="Requirements traced" value={data.metrics.requirements} />
        </Card>
        <Card>
          <Statistic title="Evidence records" value={data.metrics.evidence} />
        </Card>
        <Card>
          <Statistic title="Report version" value={value(data.report, "report_version", "—")} />
        </Card>
      </div>
      <Card title="Latest deterministic verdict mix">
        <div className="bar-chart" role="img" aria-label="Bar chart of latest result status counts">
          {rows.map((row) => (
            <div key={row.status}>
              <span>{row.status}</span>
              <i style={{ width: `${Math.max(8, row.count * 12)}px` }} />
            </div>
          ))}
        </div>
        <DataTable rows={rows} label="verdict count table" />
      </Card>
    </Panel>
  );
}

function Regression({ data }: { data: WorkspaceSnapshot }) {
  const regression = data.regression;
  return (
    <Panel eyebrow="Verified change" title="Regression Portal">
      <Alert
        type="success"
        showIcon
        message="BUG-AUTH-001 closed through deterministic FAIL → PASS evidence."
      />
      <div className="transition">
        <Card>
          <Text>Before</Text>
          <Title level={2}>FAIL</Title>
          <Paragraph>
            {value(regression, "baseline_api_test_run_id")}
            <br />
            {value(regression, "baseline_ui_test_run_id")}
          </Paragraph>
        </Card>
        <strong aria-label="changed to">→</strong>
        <Card>
          <Text>After</Text>
          <Title level={2}>PASS</Title>
          <Paragraph>
            {value(regression, "regression_api_test_run_id")}
            <br />
            {value(regression, "regression_ui_test_run_id")}
          </Paragraph>
        </Card>
      </div>
      <Card title="Closure decision">
        <Descriptions
          column={1}
          items={[
            {
              key: "guards",
              label: "Adjacent guards",
              children: `${value(regression, "guard_pass_count")}/${value(regression, "guard_case_count")}`,
            },
            {
              key: "trace",
              label: "Trace hash",
              children: <Text code>{value(regression, "trace_hash")}</Text>,
            },
            {
              key: "event",
              label: "Bug lifecycle",
              children: <StatusTag status={data.bug.latest_status_event?.to_status} />,
            },
          ]}
        />
      </Card>
    </Panel>
  );
}

function Workspace() {
  const location = useLocation();
  const [data, setData] = useState<WorkspaceSnapshot | null>(null);
  const [error, setError] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const refresh = () => {
    setError("");
    loadWorkspace()
      .then(setData)
      .catch(() =>
        setError("The Plugin workspace could not be loaded. Check the local backend and retry."),
      );
  };
  useEffect(refresh, []);
  useEffect(() => {
    const area = areas.find(([path]) => path === location.pathname)?.[1] ?? "Workspace";
    document.title = `${area} | AI TestPilot`;
  }, [location.pathname]);
  const menu = (
    <Menu
      selectedKeys={[location.pathname]}
      items={areas.map(([key, label, mark]) => ({
        key,
        label: (
          <Link to={key} onClick={() => setMobileOpen(false)}>
            <span className="nav-mark" aria-hidden="true">
              {mark}
            </span>
            {label}
          </Link>
        ),
      }))}
    />
  );
  const content = useMemo(
    () =>
      data && {
        Mission,
        PrdScanner,
        Requirements,
        TestForge,
        Execution,
        Evidence,
        Bugs,
        Quality,
        Regression,
      },
    [data],
  );
  if (error)
    return (
      <main className="state-page">
        <Alert
          type="error"
          showIcon
          message="Workspace unavailable"
          description={error}
          action={<Button onClick={refresh}>Retry</Button>}
        />
      </main>
    );
  if (!data || !content)
    return (
      <main className="state-page" aria-label="Loading workspace">
        <Skeleton active paragraph={{ rows: 8 }} />
      </main>
    );
  if (!data.project)
    return (
      <main className="state-page">
        <Empty description="No Plugin project data is available yet." />
      </main>
    );
  return (
    <Layout className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Sider className="desktop-nav" width={264}>
        <div className="brand">
          <b>AI TestPilot</b>
          <span>Quality Exploration Lab</span>
        </div>
        {menu}
      </Sider>
      <Drawer
        className="mobile-drawer"
        placement="left"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
      >
        {menu}
      </Drawer>
      <Layout>
        <Header>
          <Button
            className="mobile-trigger"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            Menu
          </Button>
          <div>
            <Text strong>{value(data.project, "name")}</Text>
            <Text type="secondary"> / {data.meta.environment_id ?? "local"}</Text>
          </div>
          <Space>
            <Tag>{data.meta.provider_mode ?? "offline"} provider</Tag>
            <StatusTag status={data.regression?.status ?? "ready"} />
          </Space>
        </Header>
        <Content id="main-content">
          <nav className="breadcrumb" aria-label="Breadcrumb">
            <Link to="/mission-control">Workspace</Link>
            <span>/</span>
            <span>{areas.find(([path]) => path === location.pathname)?.[1]}</span>
          </nav>
          <Routes>
            <Route path="/mission-control" element={<Mission data={data} />} />
            <Route path="/prd-scanner" element={<PrdScanner data={data} />} />
            <Route path="/requirements" element={<Requirements data={data} />} />
            <Route path="/test-forge" element={<TestForge data={data} />} />
            <Route path="/execution" element={<Execution data={data} />} />
            <Route path="/evidence" element={<Evidence data={data} />} />
            <Route path="/bugs" element={<Bugs data={data} />} />
            <Route path="/quality" element={<Quality data={data} />} />
            <Route path="/regression" element={<Regression data={data} />} />
            <Route path="*" element={<Navigate to="/mission-control" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export function App() {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#5eead4",
          colorBgBase: "#07111f",
          colorTextBase: "#e7f0ff",
          borderRadius: 10,
          fontFamily: "Inter, system-ui, sans-serif",
        },
      }}
    >
      <BrowserRouter>
        <Workspace />
      </BrowserRouter>
    </ConfigProvider>
  );
}
