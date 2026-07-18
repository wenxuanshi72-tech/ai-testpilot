import { StrictMode } from "react";
import { App as AntApp, ConfigProvider } from "antd";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import "./styles.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("SUT frontend root element is missing.");
}

createRoot(root).render(
  <StrictMode>
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#176b87",
          colorSuccess: "#23856d",
          colorError: "#c2414b",
          borderRadius: 12,
          controlHeight: 44,
          fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
);
