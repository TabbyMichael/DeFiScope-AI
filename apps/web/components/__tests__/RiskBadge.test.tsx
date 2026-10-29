import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RiskBadge from "@/components/RiskBadge";

describe("RiskBadge", () => {
  it("shows the band label and rounded score", () => {
    render(<RiskBadge score={42.6} band="moderate" />);
    expect(screen.getByText("moderate")).toBeInTheDocument();
    expect(screen.getByText("43")).toBeInTheDocument();
  });

  it("omits the score when it is unavailable", () => {
    render(<RiskBadge score={null} band="unknown" />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
    expect(screen.queryByText("null")).not.toBeInTheDocument();
  });
});
