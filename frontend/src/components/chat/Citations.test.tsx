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
      measures: ["LineItem.revenue"],
      dimensions: ["Region.name"],
      timeDimensions: [{ dimension: "Orders.order_date" }],
    };
    render(<Citations cubeQuery={q} />);
    expect(screen.getByTestId("citation-LineItem.revenue")).toBeInTheDocument();
    expect(screen.getByTestId("citation-Region.name")).toBeInTheDocument();
    expect(screen.getByTestId("citation-Orders.order_date")).toBeInTheDocument();
  });

  it("calls locateMember + setPendingModelJump on click", async () => {
    locateMock.mockResolvedValueOnce({
      path: "verticals/tpch/orders.yml",
      line: 14,
      cube: "Orders",
      field: "order_date",
    });
    render(<Citations cubeQuery={{ measures: ["Orders.count"] }} />);
    fireEvent.click(screen.getByTestId("citation-Orders.count"));
    await waitFor(() => expect(locateMock).toHaveBeenCalledWith("Orders.count"));
    await waitFor(() =>
      expect(setPendingModelJump).toHaveBeenCalledWith({
        path: "verticals/tpch/orders.yml",
        line: 14,
      }),
    );
  });

  it("does not throw when locate returns null (member not found)", async () => {
    locateMock.mockResolvedValueOnce(null);
    render(<Citations cubeQuery={{ measures: ["Orders.unknown"] }} />);
    fireEvent.click(screen.getByTestId("citation-Orders.unknown"));
    await waitFor(() => expect(locateMock).toHaveBeenCalled());
    // setPendingModelJump must NOT have been called for null.
    expect(setPendingModelJump).not.toHaveBeenCalled();
  });
});
