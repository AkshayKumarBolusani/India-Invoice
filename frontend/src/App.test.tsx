import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api", () => ({
  health: vi.fn(() => Promise.reject(new Error("offline"))),
  evaluation: vi.fn(() => Promise.reject(new Error("offline"))),
  processInvoice: vi.fn(),
  processBatch: vi.fn(),
  compareInvoice: vi.fn(),
}));

describe("India Invoice AI product shell", () => {
  it("shows a clearly labelled demo workspace with verified navigation", async () => {
    render(<App />);

    expect(screen.getByText("A quieter way to trust invoice data")).toBeInTheDocument();
    expect(screen.getByText("Demo snapshot")).toBeInTheDocument();
    expect(screen.getByText("Documents audited")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Extractor comparison/i }));
    expect(screen.getByText("Agreement is not evidence")).toBeInTheDocument();
    expect(screen.getByText(/Both outputs can agree and still be wrong/)).toBeInTheDocument();
  });
});
