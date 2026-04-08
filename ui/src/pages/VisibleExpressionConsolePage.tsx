import "./VisibleExpressionConsolePage.css";

import VisibleChatRail from "../components/visibleConsole/VisibleChatRail";
import VisibleExpressionStage from "../components/visibleConsole/VisibleExpressionStage";
import { useVisibleExpressionConsoleData } from "./useVisibleExpressionConsoleData";

const relativeTime = (timestamp: number) =>
  new Date(timestamp).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });

export default function VisibleExpressionConsolePage() {
  const consoleData = useVisibleExpressionConsoleData();

  return (
    <main className="visible-expression-console-page">
      <div className="visible-expression-console-shell">
        <header className="visible-expression-console-topbar">
          <div className="visible-expression-console-topbar__brand">
            <span className="console-kicker">Expression Console</span>
            <h1>Visible intelligence</h1>
          </div>
          <div className="visible-expression-console-topbar__status">
            <span className="console-badge console-badge--soft">live surfaces</span>
            <span className="console-badge">{relativeTime(consoleData.refreshTick)}</span>
            <span className="console-badge console-badge--ghost">replay</span>
            {consoleData.error ? <span className="console-badge console-badge--warning">{consoleData.error}</span> : null}
          </div>
        </header>

        <div className="visible-expression-console-layout">
          <VisibleExpressionStage
            expeditions={consoleData.expeditions}
            selectedMissionId={consoleData.selectedMissionId}
            onMissionChange={consoleData.setSelectedMissionId}
            mission={consoleData.mission}
            mirrorNotes={consoleData.mirrorNotes}
            state={consoleData.state}
            timeline={consoleData.timeline}
            interpretation={consoleData.interpretation}
            signals={consoleData.signals}
            progress={consoleData.progress}
            expressionSpec={consoleData.expressionSpec}
            advisories={consoleData.advisories}
          />

          <VisibleChatRail
            missionId={consoleData.selectedMissionId}
            messages={consoleData.messages}
            advisories={consoleData.advisories}
            sending={consoleData.sending}
            onSend={consoleData.sendMessage}
            onReturnToBase={() => {
              window.location.hash = "#/dashboard";
            }}
          />
        </div>

        {!consoleData.loading && !consoleData.expeditions.length ? (
          <section className="visible-console-empty-state">
            <h2>No expeditions available</h2>
            <p>The stage stays honest here. When a mission exists, the page binds to existing expedition APIs and derived-only UI overlays automatically.</p>
          </section>
        ) : null}
      </div>
    </main>
  );
}
