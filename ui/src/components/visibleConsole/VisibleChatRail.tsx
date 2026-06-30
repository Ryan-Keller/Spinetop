import { useEffect, useState } from "react";

import type { MissionChatMessage } from "../../pages/dashboardTypes";

type VisibleChatRailProps = {
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
  if (role.includes("concierge")) return "concierge";
  if (role.includes("observer")) return "observer";
  if (role.includes("expedition")) return "expedition";
  if (role.includes("system") || role.includes("intervention")) return "system";
  return "assistant";
};

export default function VisibleChatRail(props: VisibleChatRailProps) {
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setDraft("");
  }, [props.missionId]);

  const handleSubmit = async () => {
    const content = draft.trim();
    if (!content) return;
    const sent = await props.onSend(content);
    if (sent) setDraft("");
  };

  return (
    <aside className="visible-chat-rail">
      <header className="visible-chat-rail__header">
        <div className="visible-chat-rail__heading">
          <span className="console-kicker">Console</span>
          <h2>Mirror notes</h2>
        </div>
        <div className="visible-chat-rail__mode-row">
          <button type="button" className="role-chip" onClick={props.onReturnToBase}>
            Dashboard
          </button>
        </div>
      </header>

      <div className="visible-chat-rail__messages">
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
            <strong>Quiet</strong>
            <p>
              Use <code>save:</code>, retrieval, or a direct note when you need to write to the mirror.
            </p>
          </div>
        )}
      </div>

      <div className="visible-chat-rail__composer">
        <label className="chat-rail__input-wrap">
          <span>Input</span>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Type save:, retrieval, or a direct mirror note"
            rows={5}
          />
        </label>
        <div className="chat-rail__composer-row">
          <small>Messages send exactly as typed.</small>
          <button type="button" className="chat-send" onClick={() => void handleSubmit()} disabled={props.sending || !draft.trim()}>
            {props.sending ? "Sending..." : "Send"}
          </button>
        </div>
      </div>
    </aside>
  );
}
