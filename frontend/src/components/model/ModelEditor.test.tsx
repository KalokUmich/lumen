import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ModelEditor } from "./ModelEditor";

const apiMocks = {
  listModelFiles: vi.fn(),
  getModelFile: vi.fn(),
  saveModelFile: vi.fn(),
  validateModelContent: vi.fn(),
};

vi.mock("../../lib/api", () => ({
  listModelFiles: () => apiMocks.listModelFiles(),
  getModelFile: (p: string) => apiMocks.getModelFile(p),
  saveModelFile: (p: string, c: string) => apiMocks.saveModelFile(p, c),
  validateModelContent: (c: string) => apiMocks.validateModelContent(c),
}));

function mountEditor(initialPath?: string, initialLine?: number) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ModelEditor initialPath={initialPath} initialLine={initialLine} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
  apiMocks.listModelFiles.mockResolvedValue([
    { path: "examples/orders.yml", size: 1234, vertical: null },
    { path: "verticals/lending/loan.yml", size: 5678, vertical: "lending" },
  ]);
  apiMocks.getModelFile.mockResolvedValue({
    path: "examples/orders.yml",
    content: "cubes:\n  - name: Orders\n    sql_table: orders\n",
  });
});

describe("ModelEditor", () => {
  it("loads the file list and renders entries grouped by directory", async () => {
    mountEditor();
    await waitFor(() =>
      expect(screen.getByTestId("file-row-examples/orders.yml")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("file-row-verticals/lending/loan.yml")).toBeInTheDocument();
  });

  it("auto-selects the first file and shows its content", async () => {
    mountEditor();
    await waitFor(() => expect(apiMocks.getModelFile).toHaveBeenCalled());
    const ta = (await screen.findByTestId("model-editor-textarea")) as HTMLTextAreaElement;
    await waitFor(() => expect(ta.value).toContain("name: Orders"));
  });

  it("respects initialPath when provided (citation jump)", async () => {
    apiMocks.getModelFile.mockResolvedValue({
      path: "verticals/lending/loan.yml",
      content: "cubes:\n  - name: Orders\n",
    });
    mountEditor("verticals/lending/loan.yml");
    await waitFor(() =>
      expect(apiMocks.getModelFile).toHaveBeenCalledWith("verticals/lending/loan.yml"),
    );
  });

  it("Validate button calls the API and shows the success state", async () => {
    apiMocks.validateModelContent.mockResolvedValue({
      valid: true,
      errors: [],
      warnings: [],
    });
    mountEditor();
    await waitFor(() => expect(apiMocks.getModelFile).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("validate-button"));
    const panel = await screen.findByTestId("validation-panel");
    // The panel renders the literal "Valid" word (success state); the button
    // also contains "Validate" so we have to scope the text query to the panel.
    expect(panel.textContent).toMatch(/\bValid\b/);
  });

  it("Validate shows errors when the file is invalid", async () => {
    apiMocks.validateModelContent.mockResolvedValue({
      valid: false,
      errors: [{ line: 3, column: 1, message: "missing `type`" }],
      warnings: [],
    });
    mountEditor();
    await waitFor(() => expect(apiMocks.getModelFile).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("validate-button"));
    await waitFor(() => expect(screen.getByText(/missing `type`/)).toBeInTheDocument());
    expect(screen.getByText(/1 error/)).toBeInTheDocument();
  });

  it("Save validates first and bails on errors", async () => {
    apiMocks.validateModelContent.mockResolvedValue({
      valid: false,
      errors: [{ line: null, column: null, message: "broken" }],
      warnings: [],
    });
    mountEditor();
    await waitFor(() => expect(apiMocks.getModelFile).toHaveBeenCalled());
    // Make the editor dirty to enable Save.
    const ta = screen.getByTestId("model-editor-textarea") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: ta.value + "\n# edit" } });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => expect(apiMocks.validateModelContent).toHaveBeenCalled());
    expect(apiMocks.saveModelFile).not.toHaveBeenCalled();
  });

  it("Save persists when validation passes", async () => {
    apiMocks.validateModelContent.mockResolvedValue({
      valid: true,
      errors: [],
      warnings: [],
    });
    apiMocks.saveModelFile.mockResolvedValue({ path: "examples/orders.yml", size: 1300 });
    mountEditor();
    await waitFor(() => expect(apiMocks.getModelFile).toHaveBeenCalled());
    const ta = screen.getByTestId("model-editor-textarea") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: ta.value + "\n# edit" } });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => expect(apiMocks.saveModelFile).toHaveBeenCalled());
  });

  it("switching files re-fetches content", async () => {
    apiMocks.getModelFile
      .mockResolvedValueOnce({ path: "examples/orders.yml", content: "first" })
      .mockResolvedValueOnce({ path: "verticals/lending/loan.yml", content: "second" });
    mountEditor();
    await waitFor(() =>
      expect(apiMocks.getModelFile).toHaveBeenCalledWith("examples/orders.yml"),
    );
    fireEvent.click(screen.getByTestId("file-row-verticals/lending/loan.yml"));
    await waitFor(() =>
      expect(apiMocks.getModelFile).toHaveBeenCalledWith("verticals/lending/loan.yml"),
    );
  });
});
