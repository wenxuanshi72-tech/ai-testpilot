import { Link } from "react-router-dom";

interface AuthShellProps {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}

export function AuthShell({ eyebrow, title, description, children }: AuthShellProps) {
  return (
    <main className="auth-shell">
      <section className="brand-panel" aria-labelledby="brand-heading">
        <Link className="brand-mark" to="/" aria-label="AI TestPilot SUT home">
          AT
        </Link>
        <div>
          <p className="eyebrow">System under test</p>
          <h1 id="brand-heading">Authentication, made observable.</h1>
          <p>
            A focused local application for exercising registration, session, and access-control
            behavior with clear, deterministic feedback.
          </p>
        </div>
        <p className="trust-note">Local-first Cookie sessions No browser token storage</p>
      </section>
      <section className="form-panel" aria-labelledby="page-heading">
        <div className="form-card">
          <p className="eyebrow">{eyebrow}</p>
          <h2 id="page-heading">{title}</h2>
          <p className="form-intro">{description}</p>
          {children}
        </div>
      </section>
    </main>
  );
}
