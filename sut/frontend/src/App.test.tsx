import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("SUT foundation shell", () => {
  it("states that authentication is not implemented", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "AI TestPilot SUT foundation" })).toBeVisible();
    expect(screen.getByText(/authentication behavior is not implemented/i)).toBeVisible();
  });
});
