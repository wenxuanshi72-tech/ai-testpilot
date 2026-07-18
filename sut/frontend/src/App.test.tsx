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
  user_id: "USR-test",
  username: "aurora_user",
  created_at: "2026-07-18T00:00:00Z",
};

describe("SUT authentication routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(authApi.getCurrentUser).mockResolvedValue(null);
    vi.mocked(authApi.logout).mockResolvedValue();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("renders the registration route", async () => {
    renderApp("/register");
    expect(await screen.findByRole("heading", { name: "Start a secure session" })).toBeVisible();
    expect(screen.getByLabelText("Username")).toBeVisible();
  });

  it("renders the login route", async () => {
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "Sign in to your account" })).toBeVisible();
  });

  it("renders a professional 404 route", async () => {
    renderApp("/not-exist");
    expect(await screen.findByText("404")).toBeVisible();
    expect(screen.getByText(/does not exist/i)).toBeVisible();
  });

  it("redirects an unauthenticated profile request to login", async () => {
    renderApp("/profile");
    expect(await screen.findByRole("heading", { name: "Sign in to your account" })).toBeVisible();
  });

  it("restores an authenticated profile from the me request", async () => {
    vi.mocked(authApi.getCurrentUser).mockResolvedValue(user);
    renderApp("/profile");
    expect(await screen.findByRole("heading", { name: "Account profile" })).toBeVisible();
    expect(screen.getAllByText("aurora_user").length).toBeGreaterThan(0);
    expect(screen.getByText("Session active")).toBeVisible();
  });

  it("routes the authenticated home page to profile", async () => {
    vi.mocked(authApi.getCurrentUser).mockResolvedValue(user);
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Account profile" })).toBeVisible();
  });

  it("routes the unauthenticated home page to login", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Sign in to your account" })).toBeVisible();
  });

  it("distinguishes an initialization network error from a 401", async () => {
    vi.mocked(authApi.getCurrentUser).mockRejectedValue(
      new authApi.AuthApiError("NETWORK_ERROR", "Service unavailable"),
    );
    renderApp("/");
    expect(
      await screen.findByRole("heading", { name: "Authentication service unavailable" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });

  it("clears authenticated state after logout", async () => {
    vi.mocked(authApi.getCurrentUser).mockResolvedValue(user);
    renderApp("/profile");
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in to your account" })).toBeVisible();
    expect(authApi.logout).toHaveBeenCalledOnce();
  });

  it("does not persist a session token in browser storage", async () => {
    vi.mocked(authApi.getCurrentUser).mockResolvedValue(user);
    renderApp("/profile");
    await screen.findByRole("heading", { name: "Account profile" });
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("shows a perceptible loading state while me is pending", () => {
    vi.mocked(authApi.getCurrentUser).mockReturnValue(new Promise(() => undefined));
    renderApp("/");
    expect(screen.getByRole("heading", { name: "Preparing your workspace" })).toBeVisible();
  });

  it("retries session restoration after an initialization error", async () => {
    vi.mocked(authApi.getCurrentUser)
      .mockRejectedValueOnce(new authApi.AuthApiError("NETWORK_ERROR", "Service unavailable"))
      .mockResolvedValueOnce(user);
    renderApp("/");
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Account profile" })).toBeVisible();
    await waitFor(() => expect(authApi.getCurrentUser).toHaveBeenCalledTimes(2));
  });
});
