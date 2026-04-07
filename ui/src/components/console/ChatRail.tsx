import { useEffect, useState } from "react";

import type { MissionChatMessage } from "../../pages/dashboardTypes";

type ComposerMode = "Observer" | "Concierge" | "Mirror" | "System";

type ChatRailProps = {
  missionId: string;
  messages: MissionChatMessage[];
  sending: boolean;
  onSend: (content: string) => Promise<boolean>;
  onReturnToBase: () => void;
};

const messageVariant = (message: MissionChatMessage) => {
  const role = `${message.role} ${message.kind}`.toLowerCase();
  if (message.sender === "user") return "user";
  if (role.includes("mirror")) return "mirror";
  if (role.includes("system")) return "system";
  if (role.includes("concierge")) return "concierge";
  if (role.includes("observer")) return "observer";
  return "assistant";
};

export default function ChatRail(props: ChatRailProps) {
  const [composerMode, setComposerMode] = useState<ComposerMode>("Observer");
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setDraft("");
  }, [props.missionId]);

  const quickAction = (mode: ComposerMode, text: string) => {
    setComposerMode(mode);
    setDraft(text);
  };

  const handleSubmit = async () => {
    const content = draft.trim();
    if (!content) return;
    const sent = await props.onSend(content);
    if (sent) setDraft("");
  };

  return (
    <aside className="chat-rail">
      <header className="chat-rail__header">
        <div>
          <span className="console-kicker">Chat Rail</span>
          <h2>{composerMode}</h2>
        </div>
        <div className="chat-rail__mode-row">
          {(["Observer", "Concierge", "Mirror", "System"] as ComposerMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              className={`role-chip${composerMode === mode ? " role-chip--active" : ""}`}
              onClick={() => setComposerMode(mode)}
            >
              {mode}
            </button>
          ))}
        </div>
        <p>
          V1 uses the existing mission chat API only. Role routing stays visible in the composer and does not launch hidden runs.
        </p>
      </header>

      <div className="chat-rail__messages">
        {props.messages.length ? (
          props.messages.map((message) => (
            <article key={message.message_id} className={`chat-message chat-message--${messageVariant(message)}`}>
              <div className="chat-message__meta">
                <strong>{message.sender === "user" ? "Operator" : message.role || "Mission"}</strong>
                <span>{new Date(message.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
              </div>
              <p>{message.message}</p>
            </article>
          ))
        ) : (
          <div className="chat-message chat-message--empty">
            <strong>Conversation staging area</strong>
            <p>Mission chat history will appear here once this expedition has exchanged messages.</p>
          </div>
        )}
      </div>

      <div className="chat-rail__actions">
        <button type="button" className="quick-action" onClick={() => quickAction("Mirror", "Reflect on the strongest tension, contradiction, or drift signal in this mission.")}>
          Reflect
        </button>
        <button type="button" className="quick-action" onClick={() => quickAction("Concierge", "Help me ask a better question about what matters next in this expedition.")}>
          Ask better question
        </button>
        <button type="button" className="quick-action" onClick={() => quickAction("Mirror", "Mirror, summarize the pattern shift without proposing hidden action.")}>
          Send to Mirror
        </button>
        <button type="button" className="quick-action" onClick={props.onReturnToBase}>
          Start Expedition
        </button>
        <button type="button" className="quick-action" onClick={props.onReturnToBase}>
          Return to Base
        </button>
      </div>

      <div className="chat-rail__composer">
        <label className="chat-rail__input-wrap">
          <span>{composerMode} prompt</span>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={`Message ${composerMode.toLowerCase()} through the existing mission chat surface`}
            rows={4}
          />
        </label>
        <div className="chat-rail__composer-row">
          <small>Inspectable only: sending writes one visible mission chat message through `/api/expeditions/:id/chat`.</small>
          <button type="button" className="chat-send" onClick={() => void handleSubmit()} disabled={props.sending || !draft.trim()}>
            {props.sending ? "Sending..." : "Send"}
          </button>
        </div>
      </div>
    </aside>
  );
}
