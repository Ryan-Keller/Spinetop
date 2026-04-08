import { useEffect, useState } from "react";

import type { MissionChatMessage } from "../../pages/dashboardTypes";
import type { AdvisorySurface } from "../../pages/useVisibleExpressionConsoleData";

type ComposerMode = "Observer" | "Concierge" | "Mirror" | "System" | "Expedition";

type VisibleChatRailProps = {
  missionId: string;
  messages: MissionChatMessage[];
  advisories: AdvisorySurface[];
  sending: boolean;
  onSend: (content: string) => Promise<boolean>;
  onReturnToBase: () => void;
};

const modes: ComposerMode[] = ["Observer", "Concierge", "Mirror", "System", "Expedition"];

const actionPresets: Record<string, { mode: ComposerMode; text?: string; callback?: "return" }> = {
  Reflect: {
    mode: "Mirror",
    text: "Reflect on the strongest contradiction, drift, or tension signal using only visible mission artifacts.",
  },
  "Ask better question": {
    mode: "Concierge",
    text: "Synthesize the mission context, explain the strategic picture clearly, and sharpen the next question without assuming hidden control.",
  },
  "Send to Mirror": {
    mode: "Mirror",
    text: "Mirror, direct the expression stage with a bounded summary of what the live signals mean right now.",
  },
  "Start Expedition": {
    mode: "Expedition",
    text: "Visible expedition request: if the mission is sufficient, propose the next bounded first-pass move without auto-executing it.",
  },
  "Advise Expedition": {
    mode: "Concierge",
    text: '{\n  "kind": "expedition_advisory",\n  "suggestion": "",\n  "reason": "Visible concierge strategy guidance",\n  "strength": "low"\n}',
  },
  "Interject Now": {
    mode: "System",
    text: '{\n  "kind": "expedition_intervention",\n  "instruction": "",\n  "reason": "Visible interjection request",\n  "strength": "high"\n}',
  },
  "Return to Base": {
    mode: "System",
    callback: "return",
  },
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
  const [composerMode, setComposerMode] = useState<ComposerMode>("Observer");
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setDraft("");
  }, [props.missionId]);

  const triggerAction = (label: string) => {
    const preset = actionPresets[label];
    if (!preset) return;
    if (preset.callback === "return") {
      props.onReturnToBase();
      return;
    }
    setComposerMode(preset.mode);
    setDraft(preset.text || "");
  };

  const handleSubmit = async () => {
    const content = draft.trim();
    if (!content) return;
    const visibleEnvelope = `[${composerMode}] ${content}`;
    const sent = await props.onSend(visibleEnvelope);
    if (sent) setDraft("");
  };

  return (
    <aside className="visible-chat-rail">
      <header className="visible-chat-rail__header">
        <div className="visible-chat-rail__heading">
          <span className="console-kicker">Command</span>
          <h2>{composerMode}</h2>
        </div>
        <div className="visible-chat-rail__mode-row">
          {modes.map((mode) => (
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
      </header>

      <section className="visible-chat-rail__advisories">
        <div className="visible-chat-rail__section-header">
          <h3>Active objects</h3>
          <span className="console-badge console-badge--soft">visible</span>
        </div>
        <div className="visible-chat-rail__advisory-list">
          {props.advisories.length ? (
            props.advisories.map((item, index) => (
              <article
                key={`${item.kind}-${index}`}
                className={`advisory-card${item.kind === "expedition_intervention" ? " advisory-card--intervention" : ""}`}
              >
                <strong>{item.kind === "expedition_intervention" ? "Intervention" : "Advisory"}</strong>
                <p>{item.kind === "expedition_intervention" ? item.instruction : item.suggestion}</p>
                <small>
                  {item.reason} | {item.source}
                </small>
              </article>
            ))
          ) : (
            <article className="advisory-card advisory-card--empty">
              <strong>Quiet</strong>
              <p>No advisory surface is active.</p>
            </article>
          )}
        </div>
      </section>

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
            <strong>No thread yet</strong>
            <p>The rail wakes when the mission speaks.</p>
          </div>
        )}
      </div>

      <div className="visible-chat-rail__actions">
        {Object.keys(actionPresets).map((label) => (
          <button key={label} type="button" className="quick-action" onClick={() => triggerAction(label)}>
            {label}
          </button>
        ))}
      </div>

      <div className="visible-chat-rail__composer">
        <label className="chat-rail__input-wrap">
          <span>{composerMode}</span>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={`Visible ${composerMode.toLowerCase()} message`}
            rows={5}
          />
        </label>
        <div className="chat-rail__composer-row">
          <small>Explicit only</small>
          <button type="button" className="chat-send" onClick={() => void handleSubmit()} disabled={props.sending || !draft.trim()}>
            {props.sending ? "Sending..." : "Send"}
          </button>
        </div>
      </div>
    </aside>
  );
}
