import { MessageSquare, BarChart3, Table2, Layers } from "lucide-react";
import clsx from "clsx";

type Surface = "workbook" | "dashboard" | "model" | "chat";

const items: Array<{ id: Surface; icon: typeof MessageSquare; label: string }> = [
  { id: "chat", icon: MessageSquare, label: "AI Chat" },
  { id: "workbook", icon: Table2, label: "Workbook" },
  { id: "dashboard", icon: BarChart3, label: "Dashboards" },
  { id: "model", icon: Layers, label: "Model" },
];

export function LeftRail({
  surface,
  onChange,
}: {
  surface: Surface;
  onChange: (s: Surface) => void;
}) {
  return (
    <nav className="flex flex-col items-center gap-1.5 border-r border-border bg-bg-elevated py-3">
      {items.map((it) => {
        const Icon = it.icon;
        const active = surface === it.id;
        return (
          <button
            key={it.id}
            title={it.label}
            onClick={() => onChange(it.id)}
            className={clsx(
              "flex h-10 w-10 items-center justify-center rounded-md transition-all duration-150",
              active
                ? "bg-accent/15 text-accent"
                : "text-fg-subtle hover:bg-bg-subtle hover:text-fg"
            )}
          >
            <Icon className="h-[18px] w-[18px]" />
          </button>
        );
      })}
    </nav>
  );
}
