import { Alert, Button, Form, Input } from "antd";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AuthApiError } from "../api/authApi";
import { useAuth } from "../auth/AuthContext";
import { AuthShell } from "../components/AuthShell";
import { usePageTitle } from "../hooks/usePageTitle";

interface RegisterValues {
  username: string;
  password: string;
  passwordConfirmation: string;
}

export function RegisterPage() {
  usePageTitle("Create account | AI TestPilot SUT");
  const auth = useAuth();
  const navigate = useNavigate();
  const [form] = Form.useForm<RegisterValues>();
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState<AuthApiError | null>(null);

  const submit = async (values: RegisterValues) => {
    if (submitting) return;
    setSubmitting(true);
    setApiError(null);
    try {
      await auth.register({
        username: values.username.trim(),
        password: values.password,
        password_confirmation: values.passwordConfirmation,
      });
      void navigate("/profile", {
        replace: true,
        state: { notice: "Account created successfully." },
      });
    } catch (error) {
      const normalized =
        error instanceof AuthApiError
          ? error
          : new AuthApiError("UNEXPECTED_ERROR", "Registration could not be completed.");
      setApiError(normalized);
      const fieldMap: Record<string, keyof RegisterValues> = {
        username: "username",
        password: "password",
        password_confirmation: "passwordConfirmation",
      };
      form.setFields(
        Object.entries(normalized.fieldErrors).flatMap(([name, message]) => {
          const fieldName = fieldMap[name];
          return fieldName ? [{ name: fieldName, errors: [message] }] : [];
        }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Create account"
      title="Start a secure session"
      description="Choose local credentials for this authentication system under test."
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
          extra="6-32 characters using letters, numbers, or underscores."
          rules={[
            { required: true, whitespace: true, message: "Choose a username." },
            { max: 32, message: "Use no more than 32 characters." },
            {
              transform: (value: string) => value.trim(),
              pattern: /^[A-Za-z0-9_]+$/,
              message: "Use letters, numbers, or underscores only.",
            },
          ]}
        >
          <Input autoComplete="username" maxLength={32} />
        </Form.Item>
        <Form.Item
          name="password"
          label="Password"
          extra="8-128 characters with uppercase, lowercase, and a number."
          rules={[
            { required: true, message: "Create a password." },
            { min: 8, message: "Use at least 8 characters." },
            { max: 128, message: "Use no more than 128 characters." },
            { pattern: /[a-z]/, message: "Add a lowercase letter." },
            { pattern: /[A-Z]/, message: "Add an uppercase letter." },
            { pattern: /[0-9]/, message: "Add a number." },
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="passwordConfirmation"
          label="Confirm password"
          dependencies={["password"]}
          rules={[
            { required: true, message: "Confirm your password." },
            ({ getFieldValue }) => ({
              validator(_, value) {
                return !value || getFieldValue("password") === value
                  ? Promise.resolve()
                  : Promise.reject(new Error("The passwords do not match."));
              },
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Button block htmlType="submit" loading={submitting} type="primary">
          Create account
        </Button>
      </Form>
      <p className="form-switch">
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </AuthShell>
  );
}
