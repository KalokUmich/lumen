import { useEffect, useState } from "react";
import { ChatPanel } from "./components/chat/ChatPanel";
import { Workbench } from "./components/workbench/Workbench";
import { Dashboard } from "./components/dashboard/Dashboard";
import { ModelEditor } from "./components/model/ModelEditor";
import { TopBar } from "./components/layout/TopBar";
import { LeftRail } from "./components/layout/LeftRail";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useApp } from "./lib/store";

type Surface = "workbook" | "dashboard" | "model" | "chat";

export default function App() {
  const [surface, setSurface] = useState<Surface>("chat");
  const pendingDrill = useApp((s) => s.pendingDrill);
  const pendingModelJump = useApp((s) => s.pendingModelJump);
  const setPendingModelJump = useApp((s) => s.setPendingModelJump);

  // Drill-down → workbook
  useEffect(() => {
    if (pendingDrill && surface !== "workbook") {
      setSurface("workbook");
    }
  }, [pendingDrill, surface]);

  // Citation click → model editor
  useEffect(() => {
    if (pendingModelJump && surface !== "model") {
      setSurface("model");
    }
  }, [pendingModelJump, surface]);

  // Capture the jump payload locally then clear the global one — that way the
  // ModelEditor unmount-remount stays clean (key={surface} resets state).
  const [modelJump, setModelJump] = useState<{ path: string; line: number } | null>(null);
  useEffect(() => {
    if (pendingModelJump) {
      setModelJump(pendingModelJump);
      setPendingModelJump(null);
    }
  }, [pendingModelJump, setPendingModelJump]);

  return (
    <div className="grid h-screen grid-rows-[3rem_1fr] grid-cols-[4rem_1fr]">
      <div className="col-span-2">
        <TopBar />
      </div>
      <LeftRail surface={surface} onChange={setSurface} />
      <main className="overflow-hidden">
        <ErrorBoundary key={surface} surface={surface}>
          {surface === "chat" && <ChatPanel />}
          {surface === "workbook" && <Workbench />}
          {surface === "dashboard" && <Dashboard />}
          {surface === "model" && (
            <ModelEditor initialPath={modelJump?.path} initialLine={modelJump?.line} />
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}
