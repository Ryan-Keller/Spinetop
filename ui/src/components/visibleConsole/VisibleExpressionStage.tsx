import { useMemo, useState } from "react";
import type { CSSProperties } from "react";

import type { ExpeditionSummary } from "../../pages/dashboardTypes";
import type { AdvisorySurface, DerivedExpeditionProgress, MirrorExpressionSpec } from "../../pages/useVisibleExpressionConsoleData";

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
  contradictions: "Contradictions foregrounded",
  activity: "Activity channels foregrounded",
  memory_tension: "Memory tension foregrounded",
  handoff: "Handoff edges foregrounded",
};

export default function VisibleExpressionStage(props: VisibleExpressionStageProps) {
  const contradictions = props.interpretation.item?.contradictions || [];
  const patterns = props.interpretation.item?.patterns || [];
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
  const focusItems = useMemo(
    () => ({
      mirror: {
        title: "Mirror summary",
        summary: props.expressionSpec.summary,
        related: [
          ...patterns.slice(0, 2),
          ...contradictions.slice(0, 2),
          props.signals.item?.activity?.summary || "",
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
        title: "Ghost seam",
        summary: hasGhostPressure
          ? "Ghost pressure indicator is visible as a placeholder seam for future wake and expectation surfaces."
          : "Ghost seam is reserved without active pressure right now.",
        related: [
          props.signals.item?.handoff?.target_role || "",
          props.signals.item?.handoff?.reason || "",
          ...props.expressionSpec.overlay_hints.filter((item) => item.includes("ghost") || item.includes("mirror")),
        ].filter(Boolean),
      },
    }),
    [contradictions, hasGhostPressure, patterns, props.expressionSpec.overlay_hints, props.expressionSpec.summary, props.progress.confidence, props.progress.phase, props.progress.status, props.signals.item?.activity?.kind, props.signals.item?.activity?.summary, props.signals.item?.blocked?.reason, props.signals.item?.contradiction?.summary, props.signals.item?.handoff?.reason, props.signals.item?.handoff?.target_role, props.timeline.item?.recent_agent_runs, props.timeline.item?.recent_triggers],
  );
  const [focusKey, setFocusKey] = useState<keyof typeof focusItems>("mirror");
  const focus = focusItems[focusKey];
  const focusClass = (key: keyof typeof focusItems) => `stage-clickable${focusKey === key ? " stage-clickable--focused" : ""}`;

  return (
    <section className={`visible-expression-stage visible-expression-stage--${props.expressionSpec.mood}`} style={visualStyle}>
      <header className="visible-expression-stage__header">
        <div className="visible-expression-stage__heading">
          <span className="console-kicker">Visible Intelligence System</span>
          <h1>{props.mission?.objective || "Select a mission to open the expression stage"}</h1>
          <p>
            Mirror directs the stage from inspectable state, timeline, interpretation, and signals. The UI shifts by lens, mood, intensity, and emphasis rather than showing Mirror as text alone.
          </p>
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
            <span className="console-badge console-badge--soft">mission {props.mission?.mission_id || "none"}</span>
            <span className="console-badge">{props.mission?.current_state || "idle"}</span>
            <span className="console-badge console-badge--accent">{props.state.item?.operator_posture || props.mission?.operator_posture || "observe"}</span>
            <span className="console-badge console-badge--ghost">lens {props.expressionSpec.lens}</span>
            <span className="console-badge console-badge--soft">Mirror director</span>
            <span className="console-badge console-badge--soft">Observerbot seam</span>
            <span className="console-badge console-badge--soft">Concierge seam</span>
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
          <div>
            <span className="console-kicker">Expression Header</span>
            <div className="stage-visual__title-row">
              <strong>{props.mission?.mission_id || "mission-pending"}</strong>
              <span className="console-badge">{props.mission?.status_badge || props.progress.status}</span>
            </div>
            <p>{props.mission?.mission_summary?.summary || "The stage sharpens only when mission-local evidence exists."}</p>
          </div>

          <div className="stage-visual__header-meta">
            <div>
              <span>active lens</span>
              <strong>{lensTitle[props.expressionSpec.lens]}</strong>
            </div>
            <div>
              <span>posture</span>
              <strong>{props.state.item?.operator_posture || props.mission?.operator_posture || "observe"}</strong>
            </div>
            <div>
              <span>autonomy</span>
              <strong>{props.state.item?.autonomy_state || "guarded"}</strong>
            </div>
            <div>
              <span>ghost seam</span>
              <strong>{hasGhostPressure ? "pressure visible" : "placeholder only"}</strong>
            </div>
          </div>
        </div>

        <div className="stage-visual__body">
          <button type="button" className={`stage-visual__summary ${focusClass("mirror")}`} onClick={() => setFocusKey("mirror")}>
            <span className="console-kicker">Mirror Summary</span>
            <h2>{props.expressionSpec.summary}</h2>
            <div className="stage-visual__chips">
              {props.expressionSpec.emphasis.map((item) => (
                <span key={item} className="expression-chip">
                  {item}
                </span>
              ))}
              {props.expressionSpec.overlay_hints.map((item) => (
                <span key={item} className="expression-chip expression-chip--ghost">
                  {item}
                </span>
              ))}
            </div>
          </button>

          <div className="stage-visual__right-stack">
            <article className="stage-spec-card">
              <div className="stage-spec-card__header">
                <h3>Derived Mirror expression spec</h3>
                <span className="console-badge console-badge--soft">inspectable</span>
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
                <h3>Real expedition progress</h3>
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
                  <span>evidence steps</span>
                  <strong>
                    {props.progress.steps_completed}/{props.progress.steps_total}
                  </strong>
                </div>
                <div>
                  <span>last update</span>
                  <strong>{compactTime(props.progress.last_update)}</strong>
                  </div>
                </div>
            </button>
          </div>
        </div>

        <div className={`stage-visual__lower-rail stage-visual__lower-rail--${props.expressionSpec.lens}`}>
          <section className="stage-rail-section">
            <div className="stage-rail-section__header">
              <h3>Recent signals</h3>
              <span className="console-badge console-badge--soft">state + signals</span>
            </div>
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

          <section className="stage-rail-section">
            <div className="stage-rail-section__header">
              <h3>Interpretation snippets</h3>
              <span className="console-badge console-badge--ghost">Mirror</span>
            </div>
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

          <section className="stage-rail-section">
            <div className="stage-rail-section__header">
              <h3>Timeline hints</h3>
              <span className="console-badge">timeline</span>
            </div>
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

          <section className="stage-rail-section">
            <div className="stage-rail-section__header">
              <h3>Ghost / advisory seams</h3>
              <span className="console-badge console-badge--soft">visible only</span>
            </div>
            <div className="stage-note-list">
              <button
                type="button"
                className={`stage-note ${focusClass("ghost")}${hasGhostPressure ? " stage-note--ghost" : " stage-note--muted"}`}
                onClick={() => setFocusKey("ghost")}
              >
                {hasGhostPressure
                  ? "Ghost pressure indicator is visible as a placeholder seam for future wake and expectation surfaces."
                  : "Ghost seam is reserved without active pressure right now."}
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
            <h3>Focus mode</h3>
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
