import { Alert, Button, Form, Input } from "antd";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { AuthApiError } from "../api/authApi";
import { useAuth } from "../auth/AuthContext";
import { AuthShell } from "../components/AuthShell";
import { usePageTitle } from "../hooks/usePageTitle";

interface LoginValues {
  username: string;
  password: string;
}

export function LoginPage() {
  usePageTitle("Sign in | AI TestPilot SUT");
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form] = Form.useForm<LoginValues>();
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState<AuthApiError | null>(null);
  const target = (location.state as { from?: string } | null)?.from ?? "/profile";

  const submit = async (values: LoginValues) => {
    if (submitting) return;
    setSubmitting(true);
    setApiError(null);
    try {
      await auth.login({ username: values.username.trim(), password: values.password });
      void navigate(target, { replace: true });
    } catch (error) {
      setApiError(
        error instanceof AuthApiError
          ? error
          : new AuthApiError("UNEXPECTED_ERROR", "Sign in could not be completed."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in to your account"
      description="Continue with your server-managed session."
    >
      {apiError ? (
        <Alert
          showIcon
          type="error"
          message={apiError.message}
          description={apiError.requestId ? `Support ID: ${apiError.requestId}` : undefined}
        />
      ) : null}
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => void submit(values)}
      >
        <Form.Item
          name="username"
          label="Username"
          rules={[{ required: true, whitespace: true, message: "Enter your username." }]}
        >
          <Input autoComplete="username" maxLength={32} />
        </Form.Item>
        <Form.Item
          name="password"
          label="Password"
          rules={[{ required: true, message: "Enter your password." }]}
        >
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Button block htmlType="submit" loading={submitting} type="primary">
          Sign in
        </Button>
      </Form>
      <p className="form-switch">
        New here? <Link to="/register">Create an account</Link>
      </p>
    </AuthShell>
  );
}
