import axios from "axios";

export interface PublicUser {
  user_id: string;
  username: string;
  created_at: string;
}

export interface RegistrationInput {
  username: string;
  password: string;
  password_confirmation: string;
}

export interface LoginInput {
  username: string;
  password: string;
}

interface SuccessEnvelope<T> {
  data: T;
  meta: { request_id: string };
}

interface ErrorEnvelope {
  error: { code: string; details: { field: string; code: string }[] };
  meta?: { request_id: string };
}

export class AuthApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status?: number,
    public readonly requestId?: string,
    public readonly fieldErrors: Readonly<Record<string, string>> = {},
  ) {
    super(message);
    this.name = "AuthApiError";
  }
}

const configuredBaseUrl: unknown = import.meta.env["VITE_SUT_API_BASE_URL"];
const baseURL =
  typeof configuredBaseUrl === "string" && configuredBaseUrl.trim()
    ? configuredBaseUrl.trim()
    : "http://127.0.0.1:5001";

export const apiClient = axios.create({
  baseURL,
  timeout: 8_000,
  withCredentials: true,
  headers: { Accept: "application/json" },
});

const fieldMessages: Record<string, string> = {
  required_string: "This field is required.",
  invalid_format: "Use letters, numbers, or underscores only.",
  too_short: "Use at least 6 characters.",
  too_long: "Use no more than 32 characters.",
  password_policy: "Use 8-128 characters with uppercase, lowercase, and a number.",
  mismatch: "The passwords do not match.",
};

const safeMessages: Record<string, string> = {
  USERNAME_EXISTS: "That username is already in use.",
  INVALID_CREDENTIALS: "The username or password is incorrect.",
  AUTHENTICATION_REQUIRED: "Please sign in to continue.",
  ORIGIN_NOT_ALLOWED: "This request was not accepted from the current origin.",
  VALIDATION_ERROR: "Check the highlighted fields and try again.",
};

export function toAuthApiError(error: unknown): AuthApiError {
  if (error instanceof AuthApiError) return error;
  if (!axios.isAxiosError<ErrorEnvelope>(error)) {
    return new AuthApiError("UNEXPECTED_ERROR", "Something unexpected happened. Please try again.");
  }
  if (!error.response) {
    return new AuthApiError(
      "NETWORK_ERROR",
      "The authentication service could not be reached. Check that it is running and try again.",
    );
  }
  const payload = error.response.data;
  const code = payload?.error?.code ?? "REQUEST_FAILED";
  const responseRequestId: unknown = error.response.headers["x-request-id"];
  const fieldErrors = Object.fromEntries(
    (payload?.error?.details ?? []).map((detail) => [
      detail.field,
      fieldMessages[detail.code] ?? "Check this value and try again.",
    ]),
  );
  return new AuthApiError(
    code,
    safeMessages[code] ?? "We could not complete the request. Please try again.",
    error.response.status,
    payload?.meta?.request_id ??
      (typeof responseRequestId === "string" ? responseRequestId : undefined),
    fieldErrors,
  );
}

async function postUser(path: string, input: RegistrationInput | LoginInput): Promise<PublicUser> {
  try {
    const response = await apiClient.post<SuccessEnvelope<PublicUser>>(path, input);
    return response.data.data;
  } catch (error) {
    throw toAuthApiError(error);
  }
}

export const register = (input: RegistrationInput) => postUser("/api/auth/register", input);
export const login = (input: LoginInput) => postUser("/api/auth/login", input);

export async function getCurrentUser(): Promise<PublicUser | null> {
  try {
    const response = await apiClient.get<SuccessEnvelope<PublicUser>>("/api/auth/me");
    return response.data.data;
  } catch (error) {
    const normalized = toAuthApiError(error);
    if (normalized.status === 401) return null;
    throw normalized;
  }
}

export async function logout(): Promise<void> {
  try {
    await apiClient.post("/api/auth/logout");
  } catch (error) {
    throw toAuthApiError(error);
  }
}
