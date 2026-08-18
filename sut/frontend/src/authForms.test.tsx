import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "./api/authApi";
import { renderApp } from "./test/renderApp";

vi.mock("./api/authApi", async () => {
  const actual = await vi.importActual<typeof import("./api/authApi")>("./api/authApi");
  return {
    ...actual,
    getCurrentUser: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
  };
});

const user = {
  user_id: "USR-form",
  username: "z1234",
  created_at: "2026-07-18T00:00:00Z",
};

function enterRegistration(username: string, password = "Test1234", confirmation = password) {
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Confirm password"), {
    target: { value: confirmation },
  });
}

describe("authentication forms", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(authApi.getCurrentUser).mockResolvedValue(null);
  });

  it("shows the API minimum-length error for a five-character username", async () => {
    vi.mocked(authApi.register).mockRejectedValue(
      new authApi.AuthApiError(
        "VALIDATION_ERROR",
        "Check the highlighted fields and try again.",
        400,
        "REQ-minimum",
        { username: "Use at least 6 characters." },
      ),
    );
    renderApp("/register");
    await screen.findByRole("heading", { name: "Start a secure session" });
    enterRegistration(" z1234 ");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() =>
      expect(authApi.register).toHaveBeenCalledWith({
        username: "z1234",
        password: "Test1234",
        password_confirmation: "Test1234",
      }),
    );
    expect(await screen.findByText("Use at least 6 characters.")).toBeVisible();
    expect(screen.queryByText("Account created successfully.")).not.toBeInTheDocument();
  });

  it("maps a duplicate username and request ID to safe feedback", async () => {
    vi.mocked(authApi.register).mockRejectedValue(
      new authApi.AuthApiError(
        "USERNAME_EXISTS",
        "That username is already in use.",
        409,
        "REQ-duplicate",
      ),
    );
    renderApp("/register");
    await screen.findByRole("heading", { name: "Start a secure session" });
    enterRegistration("existing_user");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("That username is already in use.")).toBeVisible();
    expect(screen.getByText("Support ID: REQ-duplicate")).toBeVisible();
  });

  it("requires all registration fields", async () => {
    renderApp("/register");
    await screen.findByRole("heading", { name: "Start a secure session" });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Choose a username.")).toBeVisible();
    expect(screen.getByText("Create a password.")).toBeVisible();
    expect(screen.getByText("Confirm your password.")).toBeVisible();
    expect(authApi.register).not.toHaveBeenCalled();
  });

  it("enforces the approved password policy", async () => {
    renderApp("/register");
    await screen.findByRole("heading", { name: "Start a secure session" });
    enterRegistration("valid_user", "weak", "weak");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Use at least 8 characters.")).toBeVisible();
    expect(screen.getByText("Add an uppercase letter.")).toBeVisible();
    expect(screen.getByText("Add a number.")).toBeVisible();
  });

  it("rejects a mismatched password confirmation", async () => {
    renderApp("/register");
    await screen.findByRole("heading", { name: "Start a secure session" });
    enterRegistration("valid_user", "Test1234", "Test1235");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("The passwords do not match.")).toBeVisible();
    expect(authApi.register).not.toHaveBeenCalled();
  });

  it("submits valid login credentials and returns to the protected target", async () => {
    vi.mocked(authApi.login).mockResolvedValue({ ...user, username: "valid_user" });
    renderApp("/profile");
    await screen.findByRole("heading", { name: "Sign in to your account" });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "valid_user" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Test1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Account profile" })).toBeVisible();
    expect(authApi.login).toHaveBeenCalledWith({
      username: "valid_user",
      password: "Test1234",
    });
  });

  it("shows generic login failure feedback", async () => {
    vi.mocked(authApi.login).mockRejectedValue(
      new authApi.AuthApiError(
        "INVALID_CREDENTIALS",
        "The username or password is incorrect.",
        401,
        "REQ-login",
      ),
    );
    renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in to your account" });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "unknown_user" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Wrong1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("The username or password is incorrect.")).toBeVisible();
    expect(screen.getByText("Support ID: REQ-login")).toBeVisible();
  });

  it("prevents duplicate registration submission while pending", async () => {
    let resolveRegistration: ((value: authApi.PublicUser) => void) | undefined;
    vi.mocked(authApi.register).mockReturnValue(
      new Promise((resolve) => {
        resolveRegistration = resolve;
      }),
    );
    renderApp("/register");
    await screen.findByRole("heading", { name: "Start a secure session" });
    enterRegistration("valid_user");
    const button = screen.getByRole("button", { name: "Create account" });
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(authApi.register).toHaveBeenCalledOnce());
    resolveRegistration?.({ ...user, username: "valid_user" });
  });

  it("exposes semantic labels and explicit actions", async () => {
    renderApp("/register");
    await screen.findByRole("heading", { name: "Start a secure session" });
    expect(screen.getByLabelText("Username")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByRole("button", { name: "Create account" })).toHaveAttribute(
      "type",
      "submit",
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("requires login fields before calling the API", async () => {
    renderApp("/login");
    await screen.findByRole("heading", { name: "Sign in to your account" });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your username.")).toBeVisible();
    expect(screen.getByText("Enter your password.")).toBeVisible();
    expect(authApi.login).not.toHaveBeenCalled();
  });
});
