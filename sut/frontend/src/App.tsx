import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { FullPageStatus } from "./components/FullPageStatus";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RegisterPage } from "./pages/RegisterPage";

function HomeRoute() {
  const auth = useAuth();
  if (auth.status === "initializing") {
    return <FullPageStatus title="Preparing your workspace" detail="Restoring your session..." />;
  }
  if (auth.status === "error") {
    return (
      <FullPageStatus
        title="Authentication service unavailable"
        detail="We could not determine your sign-in state."
        actionLabel="Try again"
        onAction={auth.retry}
      />
    );
  }
  return <Navigate replace to={auth.status === "authenticated" ? "/profile" : "/login"} />;
}

export function App() {
  return (
    <Routes>
      <Route index element={<HomeRoute />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
