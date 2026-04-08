import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

import type { ExpeditionSummary } from "../../pages/dashboardTypes";
import type { AdvisorySurface, DerivedExpeditionProgress, MirrorExpressionSpec, MirrorNote } from "../../pages/useVisibleExpressionConsoleData";

type VisibleExpressionStageProps = {
  expeditions: ExpeditionSummary[];
  selectedMissionId: string;
  onMissionChange: (missionId: string) => void;
  mission: {
    mission_id: string;
    objective: string;
    current_state: string;
    status_badge?: string;
    operator_posture?: string;
    mission_summary?: {
      summary?: string;
    };
  } | null;
  mirrorNotes: MirrorNote[];
  state: {
    item: {
      operator_posture?: string;
      autonomy_state?: string;
    } | null;
  };
  timeline: {
    item: {
      recent_agent_runs: Array<{
        run_id: string;
        role: string;
        status: string;
        summary: string;
        created_at: string;
      }>;
      recent_triggers: Array<{
        trigger_id: string;
        trigger_kind: string;
        status: string;
        reason: string;
        created_at: string;
      }>;
    } | null;
  };
  interpretation: {
    item: {
      summary: string;
      patterns: string[];
      contradictions: string[];
    } | null;
    available: boolean;
    reason?: string;
  };
  signals: {
    item: {
      activity?: {
        role?: string;
        kind?: string;
        summary?: string;
        created_at?: string;
      } | null;
      contradiction?: {
        count?: number;
        summary?: string;
      } | null;
      blocked?: {
        reason?: string;
      } | null;
      stall?: {
        summary?: string;
      } | null;
      handoff?: {
        target_role?: string;
        status?: string;
        reason?: string;
      } | null;
    } | null;
  };
  progress: DerivedExpeditionProgress;
  expressionSpec: MirrorExpressionSpec;
  advisories: AdvisorySurface[];
};

const compactTime = (value?: string) => {
  if (!value) return "Awaiting";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
};

const percent = (value: number) => `${Math.round(value * 100)}%`;

const lensTitle: Record<MirrorExpressionSpec["lens"], string> = {
  contradictions: "Contradictions",
  activity: "Activity",
  memory_tension: "Tension",
  handoff: "Handoff",
};

const mirrorKindLabel = (value?: string) => {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "echo";
  if (normalized === "operator_save") return "saved";
  return normalized.replace(/_/g, " ");
};

const overlayHintLabel = (value: string) => {
  if (value === "ghost_pressure") return "handoff pressure";
  if (value === "replay_seam_ready") return "history seam ready";
  return value.replace(/_/g, " ");
};

export default function VisibleExpressionStage(props: VisibleExpressionStageProps) {
  const contradictions = props.interpretation.item?.contradictions || [];
  const patterns = props.interpretation.item?.patterns || [];
  const visibleMirrorNotes = useMemo(() => props.mirrorNotes.slice(0, 5), [props.mirrorNotes]);
  const hasGhostPressure = props.expressionSpec.overlay_hints.includes("ghost_pressure");
  const hasActivityEmphasis = props.expressionSpec.emphasis.includes("activity");
  const hasContradictionEmphasis = props.expressionSpec.emphasis.includes("contradiction");
  const hasMemoryTension = props.expressionSpec.emphasis.includes("memory_tension");
  const visualStyle = {
    "--expression-intensity": `${props.expressionSpec.intensity}`,
    "--activity-prominence": hasActivityEmphasis ? "1" : "0.45",
    "--contradiction-prominence": hasContradictionEmphasis ? "1" : "0.35",
    "--tension-prominence": hasMemoryTension ? "1" : "0.4",
  } as CSSProperties;
  const [selectedMirrorNoteId, setSelectedMirrorNoteId] = useState<string>("");
  useEffect(() => {
    if (!visibleMirrorNotes.length) {
      setSelectedMirrorNoteId("");
      return;
    }
    setSelectedMirrorNoteId((current) => (
      current && visibleMirrorNotes.some((item) => item.artifact_id === current) ? current : visibleMirrorNotes[0].artifact_id
    ));
  }, [visibleMirrorNotes]);
  const activeMirrorNote = visibleMirrorNotes.find((item) => item.artifact_id === selectedMirrorNoteId) || visibleMirrorNotes[0] || null;
  const focusItems = useMemo(
    () => ({
      mirror: {
        title: "Mirror summary",
        summary: props.expressionSpec.summary,
        related: [
          ...patterns.slice(0, 2),
          ...contradictions.slice(0, 2),
          activeMirrorNote?.text || "",
          props.signals.item?.activity?.summary || "",
        ].filter(Boolean),
      },
      echoes: {
        title: "Written echo",
        summary: activeMirrorNote?.text || "Saved mission-local mirror notes will settle here when present.",
        related: [
          activeMirrorNote ? `${mirrorKindLabel(activeMirrorNote.artifact_kind)} · ${compactTime(activeMirrorNote.created_at)}` : "",
          ...visibleMirrorNotes
            .filter((item) => item.artifact_id !== activeMirrorNote?.artifact_id)
            .slice(0, 3)
            .map((item) => item.text),
        ].filter(Boolean),
      },
      progress: {
        title: "Expedition progress",
        summary: `Phase ${props.progress.phase}, status ${props.progress.status}, confidence ${percent(props.progress.confidence)}.`,
        related: [
          props.timeline.item?.recent_agent_runs[0]?.summary || "",
          props.timeline.item?.recent_triggers[0]?.reason || "",
          props.signals.item?.activity?.summary || "",
        ].filter(Boolean),
      },
      activity: {
        title: "Activity channel",
        summary: props.signals.item?.activity?.summary || "No live activity artifact is visible right now.",
        related: [
          props.signals.item?.activity?.kind || "",
          props.timeline.item?.recent_agent_runs[0]?.summary || "",
          props.signals.item?.handoff?.reason || "",
        ].filter(Boolean),
      },
      contradictions: {
        title: "Contradiction field",
        summary: props.signals.item?.contradiction?.summary || "Contradiction indicators will surface here when present.",
        related: [...contradictions.slice(0, 3), props.signals.item?.blocked?.reason || ""].filter(Boolean),
      },
      ghost: {
        title: "Advisory seam",
        summary: hasGhostPressure
          ? "The advisory pressure indicator is visible as a read-only handoff cue."
          : "The advisory seam is reserved without active pressure right now.",
        related: [
          props.signals.item?.handoff?.target_role || "",
          props.signals.item?.handoff?.reason || "",
          ...props.expressionSpec.overlay_hints
            .filter((item) => item.includes("ghost") || item.includes("mirror"))
            .map(overlayHintLabel),
        ].filter(Boolean),
      },
    }),
    [activeMirrorNote, contradictions, hasGhostPressure, patterns, props.expressionSpec.overlay_hints, props.expressionSpec.summary, props.progress.confidence, props.progress.phase, props.progress.status, props.signals.item?.activity?.kind, props.signals.item?.activity?.summary, props.signals.item?.blocked?.reason, props.signals.item?.contradiction?.summary, props.signals.item?.handoff?.reason, props.signals.item?.handoff?.target_role, props.timeline.item?.recent_agent_runs, props.timeline.item?.recent_triggers, visibleMirrorNotes],
  );
  const [focusKey, setFocusKey] = useState<keyof typeof focusItems>("mirror");
  const focus = focusItems[focusKey];
  const focusClass = (key: keyof typeof focusItems) => `stage-clickable${focusKey === key ? " stage-clickable--focused" : ""}`;

  return (
    <section className={`visible-expression-stage visible-expression-stage--${props.expressionSpec.mood}`} style={visualStyle}>
      <header className="visible-expression-stage__header">
        <div className="visible-expression-stage__heading">
          <span className="console-kicker">Live field</span>
          <h1>{props.mission?.objective || "Select a mission"}</h1>
        </div>

        <div className="visible-expression-stage__controls">
          <label className="console-select">
            <span>Mission</span>
            <select value={props.selectedMissionId} onChange={(event) => props.onMissionChange(event.target.value)}>
              {props.expeditions.length ? null : <option value="">No expeditions available</option>}
              {props.expeditions.map((item) => (
                <option key={item.mission_id} value={item.mission_id}>
                  {item.objective || item.mission_id}
                </option>
              ))}
            </select>
          </label>
          <div className="visible-expression-stage__badges">
            <span className="console-badge console-badge--soft">{props.mission?.mission_id || "none"}</span>
            <span className="console-badge">{props.mission?.current_state || "idle"}</span>
            <span className="console-badge console-badge--accent">{props.state.item?.operator_posture || props.mission?.operator_posture || "observe"}</span>
            <span className="console-badge console-badge--ghost">{props.expressionSpec.lens}</span>
            <span className="console-badge console-badge--soft">mirror</span>
            <span className="console-badge console-badge--soft">observer</span>
            <span className="console-badge console-badge--soft">concierge</span>
          </div>
        </div>
      </header>

      <div className={`stage-visual${focusKey ? " stage-visual--zoomed" : ""}`}>
        <div className="stage-visual__field" />
        <div className="stage-visual__mesh" />
        <div className="stage-visual__pulse stage-visual__pulse--one" />
        <div className="stage-visual__pulse stage-visual__pulse--two" />
        <div className={`stage-visual__channel${hasActivityEmphasis ? " stage-visual__channel--active" : ""}`} />
        <div className={`stage-visual__contradictions${hasContradictionEmphasis ? " stage-visual__contradictions--active" : ""}`} />
        <div className={`stage-visual__tension${hasMemoryTension ? " stage-visual__tension--active" : ""}`} />
        {hasGhostPressure ? <div className="stage-visual__ghost-pressure" aria-hidden="true" /> : null}

        <div className="stage-visual__header">
          <div className="stage-visual__identity">
            <div className="stage-visual__title-row">
              <strong>{props.mission?.mission_id || "mission-pending"}</strong>
              <span className="console-badge">{props.mission?.status_badge || props.progress.status}</span>
            </div>
            <p>{props.mission?.mission_summary?.summary || "Awaiting clearer signal."}</p>
          </div>

          <div className="stage-visual__header-meta">
            <div>
              <span>lens</span>
              <strong>{lensTitle[props.expressionSpec.lens]}</strong>
            </div>
            <div>
              <span>posture</span>
              <strong>{props.state.item?.operator_posture || props.mission?.operator_posture || "observe"}</strong>
            </div>
            <div>
              <span>runtime</span>
              <strong>{props.state.item?.autonomy_state || "guarded"}</strong>
            </div>
            <div>
              <span>handoff</span>
              <strong>{hasGhostPressure ? "pressure" : "idle"}</strong>
            </div>
          </div>
        </div>

        <div className="stage-visual__body">
          <div className="stage-visual__summary-column">
            <button type="button" className={`stage-visual__summary ${focusClass("mirror")}`} onClick={() => setFocusKey("mirror")}>
              <h2>{props.expressionSpec.summary}</h2>
              <div className="stage-visual__chips">
                {props.expressionSpec.emphasis.map((item) => (
                  <span key={item} className="expression-chip">
                    {item}
                  </span>
                ))}
                {props.expressionSpec.overlay_hints.map((item) => (
                  <span key={item} className="expression-chip expression-chip--ghost">
                    {overlayHintLabel(item)}
                  </span>
                ))}
              </div>
            </button>

            {visibleMirrorNotes.length ? (
              <section className="stage-echoes" aria-label="Mirror notes">
                <div className="stage-echoes__header">
                  <span>written echoes</span>
                  <span>{visibleMirrorNotes.length}</span>
                </div>
                <div className="stage-echoes__list">
                  {visibleMirrorNotes.map((item, index) => {
                    const isSelected = item.artifact_id === activeMirrorNote?.artifact_id;
                    return (
                      <button
                        key={item.artifact_id || `${item.created_at}-${index}`}
                        type="button"
                        className={`stage-echo ${focusClass("echoes")}${isSelected ? " stage-echo--selected" : ""}${index === 0 ? " stage-echo--latest" : ""}`}
                        style={{ opacity: Math.max(0.54, 1 - index * 0.12) }}
                        onClick={() => {
                          setSelectedMirrorNoteId(item.artifact_id);
                          setFocusKey("echoes");
                        }}
                      >
                        <div className="stage-echo__meta">
                          <span>{compactTime(item.created_at)}</span>
                          <span className="stage-echo__kind">{mirrorKindLabel(item.artifact_kind)}</span>
                        </div>
                        <p className="stage-echo__text">{item.text}</p>
                      </button>
                    );
                  })}
                </div>
              </section>
            ) : null}
          </div>

          <div className="stage-visual__right-stack">
            <article className="stage-spec-card">
              <div className="stage-spec-card__header">
                <h3>Mirror</h3>
                <span className="console-badge console-badge--soft">spec</span>
              </div>
              <dl className="stage-spec-card__grid">
                <div>
                  <dt>mode</dt>
                  <dd>{props.expressionSpec.expression_mode}</dd>
                </div>
                <div>
                  <dt>mood</dt>
                  <dd>{props.expressionSpec.mood}</dd>
                </div>
                <div>
                  <dt>motion</dt>
                  <dd>{props.expressionSpec.motion_style}</dd>
                </div>
                <div>
                  <dt>intensity</dt>
                  <dd>{percent(props.expressionSpec.intensity)}</dd>
                </div>
              </dl>
            </article>

            <button type="button" className={`stage-progress-card ${focusClass("progress")}`} onClick={() => setFocusKey("progress")}>
              <div className="stage-progress-card__header">
                <h3>Expedition</h3>
                <span className="console-badge console-badge--accent">{props.progress.phase}</span>
              </div>
              <div className="stage-progress-card__bar" aria-label="Expedition progress">
                <div
                  className="stage-progress-card__bar-fill"
                  style={{ width: `${(props.progress.steps_completed / props.progress.steps_total) * 100}%` }}
                />
              </div>
              <div className="stage-progress-card__stats">
                <div>
                  <span>status</span>
                  <strong>{props.progress.status}</strong>
                </div>
                <div>
                  <span>confidence</span>
                  <strong>{percent(props.progress.confidence)}</strong>
                </div>
                <div>
                  <span>steps</span>
                  <strong>
                    {props.progress.steps_completed}/{props.progress.steps_total}
                  </strong>
                </div>
                <div>
                  <span>update</span>
                  <strong>{compactTime(props.progress.last_update)}</strong>
                  </div>
                </div>
            </button>
          </div>
        </div>

        <div className={`stage-visual__lower-rail stage-visual__lower-rail--${props.expressionSpec.lens}`}>
          <section className="stage-rail-section stage-rail-section--dock">
            <div className="stage-note-list">
              <button type="button" className={`stage-note ${focusClass("activity")}`} onClick={() => setFocusKey("activity")}>
                {props.signals.item?.activity?.summary || "No live activity artifact is visible right now."}
              </button>
              <button
                type="button"
                className={`stage-note ${focusClass("contradictions")}${hasContradictionEmphasis ? " stage-note--warning" : ""}`}
                onClick={() => setFocusKey("contradictions")}
              >
                {props.signals.item?.contradiction?.summary || "Contradiction indicators will surface here when present."}
              </button>
              <button
                type="button"
                className={`stage-note ${focusClass("contradictions")}${hasMemoryTension ? " stage-note--warning" : ""}`}
                onClick={() => setFocusKey("contradictions")}
              >
                {props.signals.item?.blocked?.reason || props.signals.item?.stall?.summary || "Memory tension remains low."}
              </button>
            </div>
          </section>

          <section className="stage-rail-section stage-rail-section--dock">
            <div className="stage-note-list">
              {patterns.slice(0, 3).map((item) => (
                <button key={item} type="button" className={`stage-note ${focusClass("mirror")}`} onClick={() => setFocusKey("mirror")}>
                  {item}
                </button>
              ))}
              {contradictions.slice(0, 2).map((item) => (
                <button key={item} type="button" className={`stage-note ${focusClass("contradictions")} stage-note--warning`} onClick={() => setFocusKey("contradictions")}>
                  {item}
                </button>
              ))}
              {!patterns.length && !contradictions.length ? (
                <div className="stage-note stage-note--muted">
                  {props.interpretation.reason || "Mirror snippets appear only when a real interpretation artifact is present."}
                </div>
              ) : null}
            </div>
          </section>

          <section className="stage-rail-section stage-rail-section--dock">
            <div className="stage-note-list">
              {props.timeline.item?.recent_agent_runs.slice(0, 2).map((item) => (
                <button key={item.run_id} type="button" className={`stage-note ${focusClass("progress")}`} onClick={() => setFocusKey("progress")}>
                  {compactTime(item.created_at)}: {item.role} {item.summary || item.status}
                </button>
              ))}
              {props.timeline.item?.recent_triggers.slice(0, 1).map((item) => (
                <button key={item.trigger_id} type="button" className={`stage-note ${focusClass("progress")}`} onClick={() => setFocusKey("progress")}>
                  {compactTime(item.created_at)}: {item.trigger_kind} {item.reason || item.status}
                </button>
              ))}
            </div>
          </section>

          <section className="stage-rail-section stage-rail-section--dock">
            <div className="stage-note-list">
              <button
                type="button"
                className={`stage-note ${focusClass("ghost")}${hasGhostPressure ? " stage-note--ghost" : " stage-note--muted"}`}
                onClick={() => setFocusKey("ghost")}
              >
                {hasGhostPressure ? "Advisory pressure seam is visible." : "Advisory seam is quiet."}
              </button>
              {props.advisories.slice(0, 2).map((item, index) => (
                <button
                  key={`${item.kind}-${index}`}
                  type="button"
                  className={`stage-note ${focusClass("ghost")}${item.kind === "expedition_intervention" ? " stage-note--warning" : ""}`}
                  onClick={() => setFocusKey("ghost")}
                >
                  {item.kind === "expedition_intervention" ? item.instruction : item.suggestion}
                </button>
              ))}
            </div>
          </section>
        </div>

        <section className="stage-focus-panel">
          <div className="stage-focus-panel__header">
            <h3>Focus</h3>
            <span className="console-badge console-badge--soft">{focus.title}</span>
          </div>
          <p className="stage-focus-panel__summary">{focus.summary}</p>
          <div className="stage-focus-panel__related">
            {focus.related.length ? (
              focus.related.map((item) => (
                <div key={item} className="stage-focus-panel__related-item">
                  {item}
                </div>
              ))
            ) : (
              <div className="stage-focus-panel__related-item">Related evidence will appear here as stage artifacts accumulate.</div>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
