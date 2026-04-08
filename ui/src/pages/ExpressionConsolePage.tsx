import "./ExpressionConsolePage.css";

import ChatRail from "../components/console/ChatRail";
import ExpressionStage from "../components/console/ExpressionStage";
import { useExpressionConsoleData } from "./useExpressionConsoleData";

const relativeTime = (timestamp: number) =>
  new Date(timestamp).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });

export default function ExpressionConsolePage() {
  const consoleData = useExpressionConsoleData();

  return (
    <main className="expression-console-page">
      <div className="expression-console-shell">
        <header className="console-topbar">
          <div>
            <span className="console-kicker">Reference Surface</span>
            <h1>Live expression console</h1>
            <p>
              Inspect visual mission expression, chat-driven exploration, and read-only stage overlays from the current mission APIs.
            </p>
          </div>
          <div className="console-topbar__status">
            <span className="console-badge console-badge--soft">poll every 8s when visible</span>
            <span className="console-badge">refreshed {relativeTime(consoleData.refreshTick)}</span>
            {consoleData.error ? <span className="console-badge console-badge--warning">{consoleData.error}</span> : null}
          </div>
        </header>

        <div className="expression-console-layout">
          <ExpressionStage
            expeditions={consoleData.expeditions}
            selectedMissionId={consoleData.selectedMissionId}
            onMissionChange={consoleData.setSelectedMissionId}
            mission={consoleData.mission}
            state={consoleData.state}
            timeline={consoleData.timeline}
            interpretation={consoleData.interpretation}
            signals={consoleData.signals}
            refreshTick={consoleData.refreshTick}
          />

          <ChatRail
            missionId={consoleData.selectedMissionId}
            messages={consoleData.messages}
            sending={consoleData.sending}
            onSend={consoleData.sendMessage}
            onReturnToBase={() => {
              window.location.hash = "#/dashboard";
            }}
          />
        </div>

        {!consoleData.loading && !consoleData.expeditions.length ? (
          <section className="console-empty-state">
            <h2>No expeditions available</h2>
            <p>
              The console stays read-only and honest here. When expeditions exist again, the stage and chat rail will bind to the current mission APIs automatically.
            </p>
          </section>
        ) : null}
      </div>
    </main>
  );
}
