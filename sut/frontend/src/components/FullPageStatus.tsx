import { Button, Spin } from "antd";

interface FullPageStatusProps {
  title: string;
  detail: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function FullPageStatus({ title, detail, actionLabel, onAction }: FullPageStatusProps) {
  return (
    <main className="status-page" aria-live="polite">
      <Spin size="large" spinning={!actionLabel} />
      <h1>{title}</h1>
      <p>{detail}</p>
      {actionLabel && onAction ? (
        <Button type="primary" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </main>
  );
}
