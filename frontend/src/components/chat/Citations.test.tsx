import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Citations } from "./Citations";
import type { CubeQuery } from "../../lib/api";

const locateMock = vi.fn();
vi.mock("../../lib/api", async (orig) => {
  const real = await orig<typeof import("../../lib/api")>();
  return { ...real, locateMember: (m: string) => locateMock(m) };
});

const setPendingModelJump = vi.fn();
vi.mock("../../lib/store", () => ({
  useApp: (sel: (s: { setPendingModelJump: typeof setPendingModelJump }) => unknown) =>
    sel({ setPendingModelJump }),
}));

beforeEach(() => {
  locateMock.mockReset();
  setPendingModelJump.mockReset();
});

describe("Citations", () => {
  it("renders nothing when there are no fields", () => {
    const { container } = render(<Citations cubeQuery={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders one chip per measure / dimension / time dim", () => {
    const q: CubeQuery = {
      measures: ["Loan.total_originated"],
      dimensions: ["Branch.name"],
      timeDimensions: [{ dimension: "Loan.originated_at" }],
    };
    render(<Citations cubeQuery={q} />);
    expect(screen.getByTestId("citation-Loan.total_originated")).toBeInTheDocument();
    expect(screen.getByTestId("citation-Branch.name")).toBeInTheDocument();
    expect(screen.getByTestId("citation-Loan.originated_at")).toBeInTheDocument();
  });

  it("calls locateMember + setPendingModelJump on click", async () => {
    locateMock.mockResolvedValueOnce({
      path: "verticals/lending/loan.yml",
      line: 14,
      cube: "Loan",
      field: "originated_at",
    });
    render(<Citations cubeQuery={{ measures: ["Loan.count"] }} />);
    fireEvent.click(screen.getByTestId("citation-Loan.count"));
    await waitFor(() => expect(locateMock).toHaveBeenCalledWith("Loan.count"));
    await waitFor(() =>
      expect(setPendingModelJump).toHaveBeenCalledWith({
        path: "verticals/lending/loan.yml",
        line: 14,
      }),
    );
  });

  it("does not throw when locate returns null (member not found)", async () => {
    locateMock.mockResolvedValueOnce(null);
    render(<Citations cubeQuery={{ measures: ["Loan.unknown"] }} />);
    fireEvent.click(screen.getByTestId("citation-Loan.unknown"));
    await waitFor(() => expect(locateMock).toHaveBeenCalled());
    // setPendingModelJump must NOT have been called for null.
    expect(setPendingModelJump).not.toHaveBeenCalled();
  });
});
