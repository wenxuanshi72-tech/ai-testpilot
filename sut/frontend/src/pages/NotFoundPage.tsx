import { Button, Result } from "antd";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { usePageTitle } from "../hooks/usePageTitle";

export function NotFoundPage() {
  usePageTitle("Page not found | AI TestPilot SUT");
  const auth = useAuth();
  const destination = auth.status === "authenticated" ? "/profile" : "/login";
  return (
    <main className="not-found-page">
      <Result
        status="404"
        title="404"
        subTitle="The page you requested does not exist in this authentication workspace."
        extra={
          <Button type="primary">
            <Link to={destination}>
              {auth.status === "authenticated" ? "Return to profile" : "Sign in"}
            </Link>
          </Button>
        }
      />
    </main>
  );
}
