import { Alert, Button, Descriptions } from "antd";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { AuthApiError } from "../api/authApi";
import { useAuth } from "../auth/AuthContext";
import { usePageTitle } from "../hooks/usePageTitle";

export function ProfilePage() {
  usePageTitle("Profile | AI TestPilot SUT");
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<AuthApiError | null>(null);
  const notice = (location.state as { notice?: string } | null)?.notice;

  const signOut = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await auth.logout();
      void navigate("/login", { replace: true });
    } catch (reason) {
      setError(
        reason instanceof AuthApiError
          ? reason
          : new AuthApiError("UNEXPECTED_ERROR", "Sign out could not be completed."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="profile-shell">
      <header className="profile-header">
        <div>
          <p className="eyebrow">Authenticated workspace</p>
          <h1>Account profile</h1>
          <p>Your identity is restored from a server-managed cookie session.</p>
        </div>
        <Button danger loading={submitting} onClick={() => void signOut()}>
          Sign out
        </Button>
      </header>
      {notice ? <Alert showIcon type="success" message={notice} /> : null}
      {error ? (
        <Alert
          showIcon
          type="error"
          message={error.message}
          description={error.requestId ? `Support ID: ${error.requestId}` : undefined}
        />
      ) : null}
      <section className="profile-card" aria-labelledby="identity-heading">
        <div className="session-badge">
          <span aria-hidden="true" />
          Session active
        </div>
        <h2 id="identity-heading">{auth.user?.username}</h2>
        <Descriptions column={1} bordered size="middle">
          <Descriptions.Item label="Public user ID">{auth.user?.user_id}</Descriptions.Item>
          <Descriptions.Item label="Username">{auth.user?.username}</Descriptions.Item>
          <Descriptions.Item label="Account created">
            {auth.user ? new Date(auth.user.created_at).toLocaleString() : ""}
          </Descriptions.Item>
          <Descriptions.Item label="Authentication">
            Server-managed cookie session
          </Descriptions.Item>
        </Descriptions>
      </section>
      <p className="privacy-note">
        Passwords, cookies, session tokens, and internal hashes are never displayed here.
      </p>
    </main>
  );
}
