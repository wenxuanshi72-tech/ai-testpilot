import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  type LoginInput,
  type PublicUser,
  type RegistrationInput,
} from "../api/authApi";

export type AuthStatus = "initializing" | "authenticated" | "unauthenticated" | "error";

interface AuthContextValue {
  status: AuthStatus;
  user: PublicUser | null;
  login: (input: LoginInput) => Promise<PublicUser>;
  register: (input: RegistrationInput) => Promise<PublicUser>;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [user, setUser] = useState<PublicUser | null>(null);
  const [revision, setRevision] = useState(0);
  const initializationRequest = useRef<Promise<PublicUser | null> | null>(null);

  useEffect(() => {
    let active = true;
    setStatus("initializing");
    initializationRequest.current ??= getCurrentUser().finally(() => {
      initializationRequest.current = null;
    });
    void initializationRequest.current
      .then((currentUser) => {
        if (!active) return;
        setUser(currentUser);
        setStatus(currentUser ? "authenticated" : "unauthenticated");
      })
      .catch(() => {
        if (!active) return;
        setUser(null);
        setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [revision]);

  const login = useCallback(async (input: LoginInput) => {
    const currentUser = await loginRequest(input);
    setUser(currentUser);
    setStatus("authenticated");
    return currentUser;
  }, []);

  const register = useCallback(async (input: RegistrationInput) => {
    const currentUser = await registerRequest(input);
    setUser(currentUser);
    setStatus("authenticated");
    return currentUser;
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      setUser(null);
      setStatus("unauthenticated");
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login,
      register,
      logout,
      retry: () => setRevision((current) => current + 1),
    }),
    [login, logout, register, status, user],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// AuthProvider and its hook intentionally share one public module.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
