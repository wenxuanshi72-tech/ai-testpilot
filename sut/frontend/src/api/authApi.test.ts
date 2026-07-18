import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient, AuthApiError, getCurrentUser, register, toAuthApiError } from "./authApi";

describe("auth API client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses bounded credentialed HTTP defaults", () => {
    expect(apiClient.defaults.baseURL).toBe("http://127.0.0.1:5001");
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.timeout).toBe(8_000);
  });

  it("maps server details and request IDs without exposing internal messages", () => {
    const error = {
      isAxiosError: true,
      response: {
        status: 400,
        data: {
          error: {
            code: "VALIDATION_ERROR",
            message: "Internal detail that must not be shown.",
            details: [{ field: "username", code: "invalid_format" }],
          },
          meta: { request_id: "REQ-map" },
        },
        headers: {},
      },
    };
    const normalized = toAuthApiError(error);
    expect(normalized.message).toBe("Check the highlighted fields and try again.");
    expect(normalized.fieldErrors.username).toBe("Use letters, numbers, or underscores only.");
    expect(normalized.requestId).toBe("REQ-map");
  });

  it("distinguishes network failures", () => {
    const normalized = toAuthApiError({ isAxiosError: true });
    expect(normalized).toBeInstanceOf(AuthApiError);
    expect(normalized.code).toBe("NETWORK_ERROR");
  });

  it("treats an unauthorized me response as an unauthenticated state", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 401,
        data: { error: { code: "AUTHENTICATION_REQUIRED", details: [] } },
        headers: {},
      },
    });
    await expect(getCurrentUser()).resolves.toBeNull();
  });

  it("sends registration fields to the real contract path", async () => {
    const postSpy = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: {
        data: { user_id: "USR-api", username: "z1234", created_at: "2026-07-18T00:00:00Z" },
        meta: { request_id: "REQ-api" },
      },
    });
    await register({
      username: "z1234",
      password: "Test1234",
      password_confirmation: "Test1234",
    });
    expect(postSpy).toHaveBeenCalledWith("/api/auth/register", {
      username: "z1234",
      password: "Test1234",
      password_confirmation: "Test1234",
    });
  });
});
