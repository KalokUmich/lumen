import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ChevronDown, Activity } from "lucide-react";
import {
  listWorkspaces,
  getProvidersHealth,
  setActiveWorkspace,
  getActiveWorkspace,
  type Workspace,
} from "../../lib/api";

export function TopBar() {
  const [activeId, setActiveId] = useState(getActiveWorkspace());

  const workspaces = useQuery({ queryKey: ["workspaces"], queryFn: listWorkspaces });
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: getProvidersHealth,
    refetchInterval: 30_000,
  });

  useEffect(() => {
    const ws = workspaces.data?.find((w) => w.id === activeId);
    if (ws) setActiveWorkspace(ws.id, ws.llm_preset);
  }, [workspaces.data, activeId]);

  return (
    <header className="flex h-12 items-center justify-between border-b border-border bg-bg-elevated px-5">
      <div className="flex items-center gap-3">
        <div className="flex h-6 w-6 items-center justify-center rounded bg-accent text-xs font-bold text-white">
          L
        </div>
        <span className="font-semibold">Lumen</span>
        <span className="text-fg-subtle">/</span>
        <WorkspaceSelector
          workspaces={workspaces.data ?? []}
          activeId={activeId}
          onSelect={setActiveId}
        />
      </div>

      <div className="flex items-center gap-3">
        <ProviderBadge data={providers.data} />
        <button className="flex items-center gap-2 rounded-md border border-border bg-bg px-3 py-1 text-xs text-fg-muted hover:text-fg">
          <Search className="h-3.5 w-3.5" />
          Search
          <span className="ml-3 font-mono text-fg-subtle">⌘K</span>
        </button>
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-bg text-xs">U</div>
      </div>
    </header>
  );
}

function WorkspaceSelector({
  workspaces,
  activeId,
  onSelect,
}: {
  workspaces: Workspace[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const active = workspaces.find((w) => w.id === activeId);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-sm text-fg-muted hover:text-fg"
      >
        {active ? `${active.name}` : "Select workspace…"}
        <span className="text-fg-subtle">·</span>
        <span className="text-xs uppercase text-fg-subtle">{active?.vertical ?? "—"}</span>
        <ChevronDown className="h-3 w-3" />
      </button>
      {open && (
        <div className="absolute left-0 top-7 z-10 min-w-[14rem] rounded-md border border-border bg-bg-elevated p-1 shadow-lg">
          {workspaces.length === 0 && (
            <div className="px-2 py-1 text-xs text-fg-muted">No workspaces yet.</div>
          )}
          {workspaces.map((ws) => (
            <button
              key={ws.id}
              onClick={() => {
                onSelect(ws.id);
                setOpen(false);
              }}
              className={`flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs ${
                ws.id === activeId ? "bg-accent/15 text-accent" : "text-fg hover:bg-bg-subtle"
              }`}
            >
              <span>{ws.name}</span>
              <span className="text-fg-subtle">{ws.vertical}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ProviderBadge({ data }: { data: unknown }) {
  if (!data) return null;
  const d = data as {
    default: string | null;
    providers: Record<string, { healthy: boolean; latency_ms: number | null }>;
  };
  const healthy = Object.entries(d.providers ?? {}).filter(([_, v]) => v.healthy);
  const total = Object.keys(d.providers ?? {}).length;
  const color = healthy.length === 0 ? "text-danger" : healthy.length < total ? "text-warning" : "text-success";
  return (
    <div title={JSON.stringify(d, null, 2)} className="flex items-center gap-1 text-xs text-fg-muted">
      <Activity className={`h-3.5 w-3.5 ${color}`} />
      {healthy.length}/{total} providers
    </div>
  );
}
