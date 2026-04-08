import type { ExpeditionSummary } from "../../pages/dashboardTypes";

type ExtendedMission = {
  mission_id: string;
  objective: string;
  current_state: string;
  operator_posture?: string;
  status_badge?: string;
  queue_hygiene?: {
    signals?: string[];
  };
  mission_summary?: {
    summary?: string;
    recommended_next_step?: string;
    confidence?: number;
  };
  mirror_notes?: Array<{
    summary?: string;
  }>;
};

type StageProps = {
  expeditions: ExpeditionSummary[];
  selectedMissionId: string;
  onMissionChange: (missionId: string) => void;
  mission: ExtendedMission | null;
  state: {
    item: {
      operator_posture?: string;
      autonomy_state?: string;
      recommended_next_step?: string;
      latest_meaningful_activity?: {
        kind?: string;
        role?: string;
        summary?: string;
        created_at?: string;
      } | null;
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
      recent_interventions: Array<{
        intervention_id: string;
        action: string;
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
      suggested_focus: string[];
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
        last_activity_age_days?: number | null;
      } | null;
      handoff?: {
        target_role?: string;
        status?: string;
        allowed_action?: string;
      } | null;
    } | null;
  };
  refreshTick: number;
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

const confidenceLabel = (value?: number) => {
  if (typeof value !== "number") return "forming";
  if (value >= 0.7) return "stable";
  if (value >= 0.4) return "active";
  return "volatile";
};

export default function ExpressionStage(props: StageProps) {
  const recentRuns = props.timeline.item?.recent_agent_runs || [];
  const recentTriggers = props.timeline.item?.recent_triggers || [];
  const recentInterventions = props.timeline.item?.recent_interventions || [];
  const signalItems = [
    props.signals.item?.activity
      ? {
          label: "Activity pulse",
          value: props.signals.item.activity.summary || `${props.signals.item.activity.role || "role"} active`,
          meta: props.signals.item.activity.kind || "activity",
        }
      : null,
    props.signals.item?.contradiction
      ? {
          label: "Contradiction",
          value: props.signals.item.contradiction.summary || "Contradiction detected",
          meta: `${props.signals.item.contradiction.count || 1} markers`,
        }
      : null,
    props.signals.item?.blocked
      ? {
          label: "Block",
          value: props.signals.item.blocked.reason || "Blocked",
          meta: "operator attention",
        }
      : null,
    props.signals.item?.stall
      ? {
          label: "Stall drift",
          value: props.signals.item.stall.summary || "Mission drifted quiet",
          meta:
            typeof props.signals.item.stall.last_activity_age_days === "number"
              ? `${props.signals.item.stall.last_activity_age_days.toFixed(1)} days since motion`
              : "age unknown",
        }
      : null,
  ].filter(Boolean) as Array<{ label: string; value: string; meta: string }>;

  const mirrorSummary =
    props.interpretation.item?.summary ||
    props.mission?.mirror_notes?.[0]?.summary ||
    "Mirror expression will appear here when a mission-local reflection artifact exists.";

  return (
    <section className="expression-stage">
      <div className="expression-stage__header">
        <div className="expression-stage__heading">
          <span className="console-kicker">Expression Console</span>
          <h1>{props.mission?.objective || "Select an expedition to open the stage"}</h1>
          <p>
            Watch the mission state, signal pressure, and interpretive surfaces together without leaving the same screen.
          </p>
        </div>

        <div className="expression-stage__controls">
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

          <div className="expression-stage__badges">
            <span className="console-badge console-badge--soft">mission {props.mission?.mission_id || "none"}</span>
            <span className="console-badge">{props.mission?.current_state || "idle"}</span>
            <span className="console-badge console-badge--accent">{props.state.item?.operator_posture || "observe"}</span>
            <span className="console-badge console-badge--ghost">lens inspectable</span>
          </div>
        </div>
      </div>

      <div className="expression-stage__hero">
        <div className="hero-core">
          <div className="hero-core__glow" />
          <div className="hero-core__content">
            <div className="hero-core__meta">
              <span>posture {props.state.item?.operator_posture || props.mission?.operator_posture || "observing"}</span>
              <span>autonomy {props.state.item?.autonomy_state || "guarded"}</span>
              <span>refresh {compactTime(new Date(props.refreshTick).toISOString())}</span>
            </div>

            <div className="hero-core__summary">
              {props.mission?.mission_summary?.summary || "The mission summary will stabilize here once the expedition read model is available."}
            </div>

            <div className="hero-core__stats">
              <div>
                <span>confidence</span>
                <strong>{confidenceLabel(props.mission?.mission_summary?.confidence)}</strong>
              </div>
              <div>
                <span>next step</span>
                <strong>{props.state.item?.recommended_next_step || props.mission?.mission_summary?.recommended_next_step || "observe"}</strong>
              </div>
              <div>
                <span>latest motion</span>
                <strong>{compactTime(props.state.item?.latest_meaningful_activity?.created_at)}</strong>
              </div>
            </div>
          </div>
        </div>

        <div className="hero-sidecards">
          <article className="signal-card signal-card--activity">
            <span className="signal-card__label">Live Activity</span>
            <strong>{props.signals.item?.activity?.role || "Observer seam"}</strong>
            <p>{props.signals.item?.activity?.summary || "No active mission-local activity is recorded right now."}</p>
            <small>{props.signals.item?.activity?.kind || "read-only signal"}</small>
          </article>

          <article className="signal-card signal-card--mirror">
            <span className="signal-card__label">Mirror Expression</span>
            <strong>{props.interpretation.available ? "present" : "placeholder"}</strong>
            <p>{mirrorSummary}</p>
            <small>
              {props.interpretation.available
                ? `${props.interpretation.item?.patterns.length || 0} patterns available`
                : props.interpretation.reason || "Waiting for mission-local Mirror note"}
            </small>
          </article>

          <article className="signal-card signal-card--warning">
            <span className="signal-card__label">Contradiction / Stall</span>
            <strong>
              {props.signals.item?.contradiction?.count
                ? `${props.signals.item.contradiction.count} contradictions`
                : props.signals.item?.stall
                  ? "stall detected"
                  : "clear"}
            </strong>
            <p>
              {props.signals.item?.contradiction?.summary ||
                props.signals.item?.stall?.summary ||
                "Signal pressure is currently low enough to keep the stage open and readable."}
            </p>
            <small>{props.signals.item?.blocked?.reason || "No major block recorded"}</small>
          </article>

          <article className="signal-card signal-card--handoff">
            <span className="signal-card__label">Role Surface</span>
            <strong>{props.signals.item?.handoff?.target_role || "Observer / concierge seam"}</strong>
            <p>
              {props.signals.item?.handoff?.allowed_action ||
                "Visible placeholders keep advisory and activation cues inspectable without adding hidden behavior."}
            </p>
            <small>{props.signals.item?.handoff?.status || "no active handoff"}</small>
          </article>
        </div>
      </div>

      <div className="expression-stage__signal-strip">
        {signalItems.length ? (
          signalItems.map((item) => (
            <div key={`${item.label}-${item.value}`} className="signal-pill">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.meta}</small>
            </div>
          ))
        ) : (
          <div className="signal-pill signal-pill--empty">
            <span>Signals</span>
            <strong>Waiting for expedition read-model activity</strong>
            <small>The stage keeps the space reserved instead of inventing fake state.</small>
          </div>
        )}
      </div>

      <div className="expression-stage__rail">
        <section className="detail-panel">
          <div className="detail-panel__header">
            <h2>Recent Signals</h2>
            <span className="console-badge console-badge--soft">read-only</span>
          </div>
          <div className="detail-list">
            {(props.mission?.queue_hygiene?.signals || []).slice(0, 4).map((item) => (
              <div key={item} className="detail-list__item">
                <strong>{item}</strong>
              </div>
            ))}
            {!(props.mission?.queue_hygiene?.signals || []).length ? (
              <div className="detail-list__item detail-list__item--muted">
                Queue hygiene signals will land here when the mission read model emits them.
              </div>
            ) : null}
          </div>
        </section>

        <section className="detail-panel">
          <div className="detail-panel__header">
            <h2>Interpretation Snippets</h2>
            <span className="console-badge console-badge--accent">Mirror</span>
          </div>
          <div className="detail-list">
            {(props.interpretation.item?.patterns || []).slice(0, 3).map((item) => (
              <div key={item} className="detail-list__item">
                <strong>{item}</strong>
              </div>
            ))}
            {(props.interpretation.item?.suggested_focus || []).slice(0, 2).map((item) => (
              <div key={item} className="detail-list__item detail-list__item--focus">
                <strong>{item}</strong>
              </div>
            ))}
            {!props.interpretation.available ? (
              <div className="detail-list__item detail-list__item--muted">
                Mirror interpretation remains a clean placeholder until a real reflection artifact exists.
              </div>
            ) : null}
          </div>
        </section>

        <section className="detail-panel">
          <div className="detail-panel__header">
            <h2>Timeline Markers</h2>
            <span className="console-badge">timeline</span>
          </div>
          <div className="detail-timeline">
            {recentRuns.slice(0, 2).map((item) => (
              <div key={item.run_id} className="detail-timeline__item">
                <span>{compactTime(item.created_at)}</span>
                <strong>{item.role || "role run"}</strong>
                <p>{item.summary || item.status}</p>
              </div>
            ))}
            {recentTriggers.slice(0, 1).map((item) => (
              <div key={item.trigger_id} className="detail-timeline__item">
                <span>{compactTime(item.created_at)}</span>
                <strong>{item.trigger_kind || "trigger"}</strong>
                <p>{item.reason || item.status}</p>
              </div>
            ))}
            {recentInterventions.slice(0, 1).map((item) => (
              <div key={item.intervention_id} className="detail-timeline__item">
                <span>{compactTime(item.created_at)}</span>
                <strong>{item.action || "intervention"}</strong>
                <p>{item.reason || item.status}</p>
              </div>
            ))}
            {!recentRuns.length && !recentTriggers.length && !recentInterventions.length ? (
              <div className="detail-timeline__item detail-list__item--muted">
                No timeline markers are available for this mission yet.
              </div>
            ) : null}
          </div>
        </section>

        <section className="detail-panel">
          <div className="detail-panel__header">
            <h2>Reference Surfaces</h2>
            <span className="console-badge console-badge--ghost">reserved views</span>
          </div>
          <div className="future-stack">
            <div className="future-card">
              <strong>Art observerbot</strong>
              <p>Reserved for lightweight visual reporting from mission signals and historical frames.</p>
            </div>
            <div className="future-card">
              <strong>Concierge Gemma 4</strong>
              <p>Reserved for conversational shaping, intent refinement, and visible expedition guidance.</p>
            </div>
            <div className="future-card">
              <strong>History / Advisory</strong>
              <p>Reserved for advisory badges and history visuals through the existing API seam.</p>
            </div>
          </div>
        </section>
      </div>
    </section>
  );
}
