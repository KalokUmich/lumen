import { useState } from "react";
import { ChatPanel } from "./components/chat/ChatPanel";
import { Workbench } from "./components/workbench/Workbench";
import { Dashboard } from "./components/dashboard/Dashboard";
import { TopBar } from "./components/layout/TopBar";
import { LeftRail } from "./components/layout/LeftRail";

type Surface = "workbook" | "dashboard" | "model" | "chat";

export default function App() {
  const [surface, setSurface] = useState<Surface>("chat");

  return (
    <div className="grid h-screen grid-rows-[3rem_1fr] grid-cols-[3.5rem_1fr]">
      <div className="col-span-2">
        <TopBar />
      </div>
      <LeftRail surface={surface} onChange={setSurface} />
      <main className="overflow-hidden">
        {surface === "chat" && <ChatPanel />}
        {surface === "workbook" && <Workbench />}
        {surface === "dashboard" && <Dashboard />}
        {surface === "model" && (
          <Placeholder title="Model Editor" hint="Phase 1 sprint M6" />
        )}
      </main>
    </div>
  );
}

function Placeholder({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center text-fg-muted">
      <h2 className="text-xl font-semibold text-fg">{title}</h2>
      <p className="mt-1 text-sm">{hint}</p>
    </div>
  );
}
