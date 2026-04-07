import { useMemo } from "react";

import type { MissionChatMessage } from "./dashboardTypes";
import { useExpressionConsoleData } from "./useExpressionConsoleData";

export type MirrorExpressionSpec = {
  expression_mode: "art" | "signal_field" | "tension_map";
  lens: "contradictions" | "activity" | "memory_tension" | "handoff";
  intensity: number;
  emphasis: string[];
  mood: "charged" | "watchful" | "steady" | "blocked";
  motion_style: "pulse" | "drift" | "hold";
  overlay_hints: string[];
  summary: string;
};

export type DerivedExpeditionProgress = {
  phase: "planning" | "first_pass" | "refinement" | "blocked" | "returning" | "complete";
  status: "running" | "blocked" | "idle" | "complete";
  confidence: number;
  last_update: string;
  steps_completed: number;
  steps_total: number;
};

export type AdvisorySurface = {
  kind: "expedition_advisory" | "expedition_intervention";
  suggestion?: string;
  instruction?: string;
  reason: string;
  strength: "low" | "high";
  created_at?: string;
  source: string;
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const firstString = (...values: Array<string | undefined | null>) => values.find((value) => typeof value === "string" && value.trim())?.trim() || "";

const includesAny = (value: string, tokens: string[]) => tokens.some((token) => value.includes(token));

const latestTimestamp = (items: Array<string | undefined | null>) =>
  items
    .map((item) => (item ? new Date(item).getTime() : Number.NaN))
    .filter((item) => Number.isFinite(item))
    .sort((a, b) => b - a)[0];

const derivePhase = (rawState: string, blocked: boolean, handoff: boolean, interpretationReady: boolean) => {
  const normalized = rawState.toLowerCase();
  if (blocked) return "blocked";
  if (includesAny(normalized, ["complete", "returned", "review"])) return "complete";
  if (handoff || includesAny(normalized, ["return", "handoff"])) return "returning";
  if (interpretationReady || includesAny(normalized, ["refine"])) return "refinement";
  if (includesAny(normalized, ["first", "doing", "active", "run"])) return "first_pass";
  return "planning";
};

const advisoryFromMessage = (message: MissionChatMessage): AdvisorySurface | null => {
  const role = `${message.role || ""} ${message.kind || ""}`.toLowerCase();
  if (role.includes("concierge")) {
    return {
      kind: "expedition_advisory",
      suggestion: message.message,
      reason: "Visible concierge guidance from mission chat",
      strength: "low",
      created_at: message.created_at,
      source: "chat",
    };
  }
  if (role.includes("intervention")) {
    return {
      kind: "expedition_intervention",
      instruction: message.message,
      reason: "Visible intervention-style chat message",
      strength: "high",
      created_at: message.created_at,
      source: "chat",
    };
  }
  return null;
};

export function useVisibleExpressionConsoleData() {
  const data = useExpressionConsoleData();

  return useMemo(() => {
    const confidence = clamp(data.mission?.mission_summary?.confidence ?? 0.18, 0, 1);
    const currentState = firstString(data.mission?.current_state, data.state.item?.current_state, "planning");
    const blocked = Boolean(data.signals.item?.blocked?.present || data.signals.item?.blocked?.reason);
    const interpretationReady = Boolean(data.interpretation.available || data.mission?.mirror_notes?.length);
    const handoff = Boolean(data.signals.item?.handoff?.present || data.signals.item?.handoff?.target_role);
    const phase = derivePhase(currentState, blocked, handoff, interpretationReady);

    const checkpoints = [
      Boolean(data.mission?.objective),
      Boolean(data.signals.item?.activity || data.timeline.item?.recent_agent_runs?.length),
      interpretationReady,
      phase === "returning" || phase === "complete",
    ];

    const lastUpdateMs = latestTimestamp([
      data.signals.item?.activity?.created_at,
      data.state.item?.latest_meaningful_activity?.created_at,
      data.timeline.item?.recent_agent_runs?.[0]?.created_at,
      data.timeline.item?.recent_triggers?.[0]?.created_at,
      data.timeline.item?.recent_interventions?.[0]?.created_at,
      data.mission?.last_updated,
    ]);

    const contradictionCount = data.signals.item?.contradiction?.count ?? data.interpretation.item?.contradictions?.length ?? 0;
    const activity = Boolean(data.signals.item?.activity);
    const intensity = clamp(
      confidence * 0.45 + (contradictionCount ? 0.25 : 0) + (activity ? 0.15 : 0) + (blocked ? 0.2 : 0),
      0.16,
      0.96,
    );

    const lens = blocked ? "memory_tension" : contradictionCount ? "contradictions" : handoff ? "handoff" : "activity";
    const emphasis = [
      activity ? "activity" : "",
      contradictionCount ? "contradiction" : "",
      blocked ? "memory_tension" : "",
      handoff ? "handoff_edge" : "",
    ].filter(Boolean);

    const advisories: AdvisorySurface[] = [];
    (data.interpretation.item?.suggested_focus || []).slice(0, 2).forEach((item) => {
      advisories.push({
        kind: "expedition_advisory",
        suggestion: item,
        reason: "Mirror suggested focus from interpretation",
        strength: "low",
        source: "interpretation",
      });
    });
    (data.timeline.item?.recent_interventions || []).slice(0, 2).forEach((item) => {
      advisories.push({
        kind: "expedition_intervention",
        instruction: firstString(item.action, item.reason, "Visible intervention"),
        reason: firstString(item.reason, item.status, "Mission-local intervention record"),
        strength: "high",
        created_at: item.created_at,
        source: "timeline",
      });
    });
    data.messages.slice(-4).forEach((message) => {
      const advisory = advisoryFromMessage(message);
      if (advisory) advisories.push(advisory);
    });

    const progress: DerivedExpeditionProgress = {
      phase,
      status: phase === "complete" ? "complete" : blocked ? "blocked" : checkpoints[1] ? "running" : "idle",
      confidence,
      last_update: Number.isFinite(lastUpdateMs) ? new Date(lastUpdateMs).toISOString() : new Date(data.refreshTick).toISOString(),
      steps_completed: checkpoints.filter(Boolean).length,
      steps_total: checkpoints.length,
    };

    const expressionSpec: MirrorExpressionSpec = {
      expression_mode: contradictionCount || blocked ? "art" : activity ? "signal_field" : "tension_map",
      lens,
      intensity,
      emphasis,
      mood: blocked ? "blocked" : contradictionCount ? "charged" : activity ? "watchful" : "steady",
      motion_style: blocked ? "hold" : activity ? "pulse" : "drift",
      overlay_hints: [
        data.signals.item?.stall?.present ? "stall_trace" : "",
        data.signals.item?.handoff?.target_role ? "ghost_pressure" : "",
        data.interpretation.available ? "mirror_summary" : "mirror_placeholder",
        "replay_seam_ready",
      ].filter(Boolean),
      summary:
        firstString(
          data.interpretation.item?.summary,
          data.signals.item?.contradiction?.summary,
          data.signals.item?.activity?.summary,
          data.state.item?.recommended_next_step,
        ) || "Mirror expression remains bounded to visible mission signals until a reflection artifact sharpens the stage.",
    };

    return {
      ...data,
      progress,
      expressionSpec,
      advisories: advisories.slice(0, 4),
    };
  }, [data]);
}
