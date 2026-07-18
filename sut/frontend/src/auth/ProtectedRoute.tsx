import { Navigate, Outlet, useLocation } from "react-router-dom";

import { FullPageStatus } from "../components/FullPageStatus";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.status === "initializing") {
    return (
      <FullPageStatus title="Restoring your session" detail="Checking your secure session..." />
    );
  }
  if (auth.status === "error") {
    return (
      <FullPageStatus
        title="Authentication service unavailable"
        detail="We could not restore your session."
        actionLabel="Try again"
        onAction={auth.retry}
      />
    );
  }
  if (auth.status === "unauthenticated") {
    return <Navigate replace to="/login" state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
