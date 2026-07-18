import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("plugin foundation shell", () => {
  it("states that product workflows are deferred", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "AI TestPilot foundation" })).toBeVisible();
    expect(screen.getByText(/product workflows.*intentionally deferred/i)).toBeVisible();
  });
});
