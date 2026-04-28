/**
 * Model Editor — view/edit Cube schema YAML files (per IMPLEMENTATION_PLAN §5.4.3).
 *
 * Phase-0 implementation:
 *   - File tree (left): YAML files under backend/cube/schema/
 *   - Code area (centre): textarea with line-number gutter; jump-to-line via URL state
 *   - Validation panel (bottom): YAML parse + Cube-shape validation
 *   - "Validate" + "Save" buttons. Save runs server-side YAML validation first.
 *
 * Phase-1 will swap the textarea for Monaco and add git-backed deploy / diff.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, FolderTree, Save, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import {
  listModelFiles,
  getModelFile,
  saveModelFile,
  validateModelContent,
  type ModelValidationResult,
} from "../../lib/api";

type Props = {
  /** Optional initial selection (file path) and line — used when chat citation lands here. */
  initialPath?: string;
  initialLine?: number;
};

export function ModelEditor({ initialPath, initialLine }: Props) {
  const filesQuery = useQuery({
    queryKey: ["model-files"],
    queryFn: listModelFiles,
  });

  const [selectedPath, setSelectedPath] = useState<string | null>(initialPath ?? null);
  const [content, setContent] = useState<string>("");
  const [originalContent, setOriginalContent] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ModelValidationResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-select the first file when one isn't pre-supplied.
  useEffect(() => {
    if (selectedPath || !filesQuery.data || filesQuery.data.length === 0) return;
    setSelectedPath(filesQuery.data[0].path);
  }, [filesQuery.data, selectedPath]);

  // Load file when selection changes.
  useEffect(() => {
    if (!selectedPath) return;
    let cancelled = false;
    setLoadError(null);
    setValidation(null);
    setSaveError(null);
    setSavedAt(null);
    getModelFile(selectedPath)
      .then((f) => {
        if (cancelled) return;
        setContent(f.content);
        setOriginalContent(f.content);
      })
      .catch((e) => {
        if (cancelled) return;
        setLoadError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPath]);

  // Scroll-to-line when initialLine is set (chat citation).
  useEffect(() => {
    if (!initialLine || !content || !textareaRef.current) return;
    const lines = content.split("\n").slice(0, initialLine);
    const offset = lines.join("\n").length;
    textareaRef.current.focus();
    textareaRef.current.setSelectionRange(offset, offset);
    // Approximate scroll: line height ~16px at text-xs.
    textareaRef.current.scrollTop = Math.max(0, (initialLine - 5) * 16);
  }, [initialLine, content]);

  const dirty = content !== originalContent;
  const lineCount = useMemo(() => content.split("\n").length, [content]);

  async function runValidate() {
    try {
      const res = await validateModelContent(content);
      setValidation(res);
    } catch (e) {
      setValidation({
        valid: false,
        errors: [{ line: null, column: null, message: e instanceof Error ? e.message : String(e) }],
        warnings: [],
      });
    }
  }

  async function runSave() {
    if (!selectedPath) return;
    setSaving(true);
    setSaveError(null);
    try {
      // Validate first; refuse to save if invalid.
      const res = await validateModelContent(content);
      setValidation(res);
      if (!res.valid) {
        setSaveError("Fix validation errors before saving.");
        return;
      }
      await saveModelFile(selectedPath, content);
      setOriginalContent(content);
      setSavedAt(Date.now());
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid h-full grid-cols-[18rem_1fr]">
      <aside className="flex h-full flex-col overflow-y-auto border-r border-border bg-bg-elevated">
        <div className="flex items-center gap-1.5 border-b border-border px-3 py-2 text-xs uppercase tracking-wider text-fg-subtle">
          <FolderTree className="h-3.5 w-3.5" />
          Schema files
        </div>
        {filesQuery.isLoading && <div className="px-3 py-2 text-xs text-fg-muted">Loading…</div>}
        {filesQuery.isError && (
          <div className="px-3 py-2 text-xs text-danger">
            {String((filesQuery.error as Error)?.message ?? "")}
          </div>
        )}
        <FileTree
          entries={filesQuery.data ?? []}
          selected={selectedPath}
          onSelect={setSelectedPath}
        />
      </aside>

      <section className="flex h-full flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-border bg-bg-elevated px-4 py-2">
          <div className="flex items-center gap-2 text-sm">
            <FileText className="h-4 w-4 text-fg-subtle" />
            <span className="font-mono text-xs text-fg">{selectedPath ?? "(no file)"}</span>
            {dirty && <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[10px] text-warning">Unsaved</span>}
            {savedAt && !dirty && (
              <span className="rounded bg-success/15 px-1.5 py-0.5 text-[10px] text-success">Saved</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="validate-button"
              onClick={runValidate}
              className="btn"
              disabled={!selectedPath}
            >
              <CheckCircle2 className="h-3.5 w-3.5" />
              Validate
            </button>
            <button
              data-testid="save-button"
              onClick={runSave}
              className="btn-primary"
              disabled={!selectedPath || !dirty || saving}
            >
              <Save className="h-3.5 w-3.5" />
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </header>

        {loadError && (
          <div className="border-b border-border bg-danger/10 px-4 py-2 text-xs text-danger">{loadError}</div>
        )}
        {saveError && (
          <div className="border-b border-border bg-danger/10 px-4 py-2 text-xs text-danger">{saveError}</div>
        )}

        <div className="flex flex-1 overflow-hidden">
          <pre
            aria-hidden
            className="select-none border-r border-border bg-bg-subtle px-2 py-2 text-right font-mono text-[11px] leading-[1.5] text-fg-subtle"
          >
            {Array.from({ length: lineCount }, (_, i) => i + 1).join("\n")}
          </pre>
          <textarea
            ref={textareaRef}
            data-testid="model-editor-textarea"
            spellCheck={false}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="flex-1 resize-none bg-bg p-2 font-mono text-[11px] leading-[1.5] text-fg outline-none"
          />
        </div>

        <ValidationPanel result={validation} />
      </section>
    </div>
  );
}

function FileTree({
  entries,
  selected,
  onSelect,
}: {
  entries: { path: string; vertical: string | null }[];
  selected: string | null;
  onSelect: (p: string) => void;
}) {
  // Group by top-level directory: examples / verticals/<vertical> / shared / ...
  const groups = useMemo(() => {
    const out: Record<string, { path: string }[]> = {};
    for (const e of entries) {
      const parts = e.path.split("/");
      const head = parts.length > 1 ? (parts[0] === "verticals" ? `verticals/${parts[1]}` : parts[0]) : ".";
      (out[head] ??= []).push({ path: e.path });
    }
    return out;
  }, [entries]);

  return (
    <ul className="px-1 py-1">
      {Object.entries(groups).map(([group, files]) => (
        <li key={group}>
          <div className="mt-1 px-2 py-0.5 text-[10px] uppercase tracking-wider text-fg-subtle">{group}</div>
          {files.map((f) => {
            const name = f.path.split("/").pop()!;
            const active = f.path === selected;
            return (
              <button
                key={f.path}
                data-testid={`file-row-${f.path}`}
                onClick={() => onSelect(f.path)}
                className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-xs ${
                  active ? "bg-bg-subtle text-fg" : "text-fg-muted hover:bg-bg-subtle hover:text-fg"
                }`}
              >
                <FileText className="h-3 w-3 text-fg-subtle" />
                <span className="truncate">{name}</span>
              </button>
            );
          })}
        </li>
      ))}
    </ul>
  );
}

function ValidationPanel({ result }: { result: ModelValidationResult | null }) {
  if (!result) {
    return (
      <div className="border-t border-border bg-bg-elevated px-4 py-2 text-xs text-fg-subtle">
        Click <strong>Validate</strong> to check this file before saving.
      </div>
    );
  }
  return (
    <div data-testid="validation-panel" className="max-h-40 overflow-y-auto border-t border-border bg-bg-elevated">
      <div className="flex items-center gap-1.5 px-4 py-2 text-xs">
        {result.valid ? (
          <>
            <CheckCircle2 className="h-3.5 w-3.5 text-success" />
            <span className="text-success">Valid</span>
          </>
        ) : (
          <>
            <XCircle className="h-3.5 w-3.5 text-danger" />
            <span className="text-danger">{result.errors.length} error{result.errors.length === 1 ? "" : "s"}</span>
          </>
        )}
        {result.warnings.length > 0 && (
          <span className="ml-2 inline-flex items-center gap-1 text-warning">
            <AlertTriangle className="h-3 w-3" />
            {result.warnings.length} warning{result.warnings.length === 1 ? "" : "s"}
          </span>
        )}
      </div>
      <ul className="space-y-1 px-4 pb-3">
        {result.errors.map((e, i) => (
          <li key={`e-${i}`} className="flex gap-2 text-xs text-danger">
            {e.line && <span className="font-mono text-fg-subtle">L{e.line}</span>}
            <span>{e.message}</span>
          </li>
        ))}
        {result.warnings.map((w, i) => (
          <li key={`w-${i}`} className="flex gap-2 text-xs text-warning">
            {w.line && <span className="font-mono text-fg-subtle">L{w.line}</span>}
            <span>{w.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
