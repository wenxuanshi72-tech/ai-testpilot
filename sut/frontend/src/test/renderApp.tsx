import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthContext";

export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
