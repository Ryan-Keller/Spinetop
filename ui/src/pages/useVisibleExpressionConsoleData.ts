import { useEffect, useMemo, useState } from "react";

import type { ExpeditionSummary, MissionChatMessage } from "./dashboardTypes";
import { groupExpeditions, isMissionParked } from "./dashboardSelectors";
import { useExpressionConsoleData } from "./useExpressionConsoleData";

const API_BASE = (import.meta.env.VITE_SPINETOP_API_BASE as string | undefined)?.trim() || "/api";

export type MirrorExpressionSpec = {
  expression_mode: "art" | "signal_field" | "tension_map";
  lens: "contradictions" | "activity" | "memory_tension" | "handoff";
  intensity: number;
  emphasis: string[];
  mood: "charged" | "watchful" | "steady" | "blocked";
  motion_style: "pulse" | "drift" | "hold";
  overlay_hints: string[];
  summary: string;
  secondary_summary: string;
  primary_source: "mirror_note" | "concierge_retrieval" | "role_output" | "blocker" | "quiet";
  quiet: boolean;
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

export type MirrorNote = {
  artifact_id: string;
  text: string;
  created_at: string;
  artifact_kind: string;
};

type MirrorNotesResponse = {
  ok: boolean;
  items?: MirrorNote[];
  error?: string;
};

type VisibleAgentRun = {
  run_id?: string;
  role?: string;
  status?: string;
  summary?: string;
  created_at?: string;
};

type VisibleTrigger = {
  trigger_id?: string;
  trigger_kind?: string;
  status?: string;
  reason?: string;
  blocked_reason?: string | null;
  created_at?: string;
};

type VisibleIntervention = {
  intervention_id?: string;
  action?: string;
  status?: string;
  reason?: string;
  blocked_reason?: string | null;
  created_at?: string;
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const firstString = (...values: Array<string | undefined | null>) => values.find((value) => typeof value === "string" && value.trim())?.trim() || "";
const normalizedText = (value?: string | null) => String(value || "").replace(/\s+/g, " ").trim();
const normalizedLower = (value?: string | null) => normalizedText(value).toLowerCase();

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

const LEGACY_COACHING_FRAGMENTS = [
  "continue cautiously and add context if it would reduce uncertainty",
  "proceed with the current assumptions and add more context only if it will improve confidence",
  "continue under the current assumptions and answer the top question when ready",
  "continue the run, then refresh mission detail for the latest state",
  "mirror expression remains bounded to visible mission signals",
  "saved mission-local mirror notes will settle here when present",
  "no live activity artifact is visible right now",
  "contradiction indicators will surface here when present",
  "mirror snippets appear only when a real interpretation artifact is present",
  "related evidence will appear here as stage artifacts accumulate",
  "advisory seam is reserved",
  "advisory seam is quiet",
  "awaiting clearer signal",
];

const ZOMBIE_SURFACE_FRAGMENTS = [
  "role invocation blocked because the mapped runtime is inactive",
  "operator may inspect existing artifacts or explicitly activate the role before retrying",
  "disabled-safe",
  "no model run was attempted",
  "proposal-only",
  "translated prompt",
  "translator-first",
  "dispatch petition",
  "collective truth",
  "system pressure",
  "future observer",
];

const isLegacyNoiseText = (value?: string | null) => {
  const normalized = normalizedLower(value);
  return normalized ? LEGACY_COACHING_FRAGMENTS.some((fragment) => normalized.includes(fragment)) : false;
};

const isZombieSurfaceText = (value?: string | null) => {
  const normalized = normalizedLower(value);
  return normalized ? ZOMBIE_SURFACE_FRAGMENTS.some((fragment) => normalized.includes(fragment)) : false;
};

const isMeaningfulVisibleText = (value?: string | null) => {
  const text = normalizedText(value);
  if (!text) return false;
  return !isLegacyNoiseText(text) && !isZombieSurfaceText(text);
};

const isVisibleMissionCandidate = (item: ExpeditionSummary) =>
  !isMissionParked(item) &&
  !item.queue_hygiene?.archive_candidate &&
  !item.queue_hygiene?.duplicate_candidate &&
  !item.queue_hygiene?.junk_pattern &&
  !item.queue_hygiene?.superseded_by_newer_similar;

const visibleExpeditionList = (items: ExpeditionSummary[], selectedMissionId: string) => {
  const { allGroups } = groupExpeditions(items, selectedMissionId);
  const preferred = allGroups.filter((group) => isVisibleMissionCandidate(group.primary));
  return (preferred.length ? preferred : allGroups).map((group) => group.primary);
};

const isVisibleRoleRun = (item: VisibleAgentRun) => normalizedLower(item.status) === "success" && isMeaningfulVisibleText(item.summary);

const isVisibleTrigger = (item: VisibleTrigger) =>
  normalizedLower(item.status) === "blocked" && isMeaningfulVisibleText(firstString(item.blocked_reason || "", item.reason || ""));

const isVisibleIntervention = (item: VisibleIntervention) => {
  const normalizedAction = normalizedLower(item.action);
  if (includesAny(normalizedAction, ["archive", "park", "duplicate", "translator", "proposal"])) return false;
  return isMeaningfulVisibleText(firstString(item.blocked_reason || "", item.reason || "", item.action || ""));
};

const isConciergeRetrievalMessage = (message: MissionChatMessage) => normalizedLower(message.kind) === "concierge_mirror_retrieval";

const isVisibleChatMessage = (message: MissionChatMessage) => {
  if (message.sender === "user") return isMeaningfulVisibleText(message.message);
  if (isConciergeRetrievalMessage(message)) return true;
  const role = normalizedLower(`${message.role} ${message.kind}`);
  if (role.includes("system") || role.includes("intervention")) return false;
  return isMeaningfulVisibleText(message.message);
};

const advisoryFromMessage = (message: MissionChatMessage): AdvisorySurface | null => {
  if (isConciergeRetrievalMessage(message)) {
    return {
      kind: "expedition_advisory",
      suggestion: message.message,
      reason: "Read-only concierge retrieval from saved mirror notes",
      strength: "low",
      created_at: message.created_at,
      source: "chat",
    };
  }
  return null;
};

export function useVisibleExpressionConsoleData() {
  const data = useExpressionConsoleData();
  const [mirrorNotes, setMirrorNotes] = useState<MirrorNote[]>([]);
  const visibleExpeditions = useMemo(
    () => visibleExpeditionList(data.expeditions, data.selectedMissionId),
    [data.expeditions, data.selectedMissionId],
  );

  useEffect(() => {
    if (!visibleExpeditions.length) return;
    if (visibleExpeditions.some((item) => item.mission_id === data.selectedMissionId)) return;
    data.setSelectedMissionId(visibleExpeditions[0].mission_id);
  }, [data.selectedMissionId, data.setSelectedMissionId, visibleExpeditions]);

  useEffect(() => {
    if (!data.selectedMissionId) {
      setMirrorNotes([]);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    const run = async () => {
      try {
        const response = await fetch(`${API_BASE}/expeditions/${data.selectedMissionId}/mirror-notes`, { signal: controller.signal });
        const payload = (await response.json().catch(() => ({}))) as MirrorNotesResponse;
        if (!response.ok) {
          throw new Error(payload.error || `HTTP ${response.status}`);
        }
        if (cancelled) return;
        const items = Array.isArray(payload.items)
          ? payload.items.map((item) => ({
              artifact_id: typeof item?.artifact_id === "string" ? item.artifact_id : "",
              text: typeof item?.text === "string" ? item.text : "",
              created_at: typeof item?.created_at === "string" ? item.created_at : "",
              artifact_kind: typeof item?.artifact_kind === "string" ? item.artifact_kind : "",
            }))
          : [];
        setMirrorNotes(items);
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        setMirrorNotes([]);
      }
    };

    void run();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [data.refreshTick, data.selectedMissionId]);

  return useMemo(() => {
    const filteredMirrorNotes = mirrorNotes.filter((item) => isMeaningfulVisibleText(item.text));
    const latestMirrorNote = filteredMirrorNotes[0] || null;
    const filteredMessages = data.messages.filter(isVisibleChatMessage).slice(-12);
    const retrievalMessages = filteredMessages.filter(isConciergeRetrievalMessage);
    const latestRetrievalMessage = retrievalMessages[retrievalMessages.length - 1] || null;
    const visibleAgentRuns = (data.timeline.item?.recent_agent_runs || []).filter(isVisibleRoleRun).slice(0, 3);
    const latestVisibleRun = visibleAgentRuns[0] || null;
    const visibleTriggers = (data.timeline.item?.recent_triggers || []).filter(isVisibleTrigger).slice(0, 2);
    const visibleInterventions = (data.timeline.item?.recent_interventions || []).filter(isVisibleIntervention).slice(0, 2);
    const interpretationSummary = isMeaningfulVisibleText(data.interpretation.item?.summary) ? normalizedText(data.interpretation.item?.summary) : "";
    const interpretationPatterns = (data.interpretation.item?.patterns || []).filter(isMeaningfulVisibleText);
    const interpretationContradictions = (data.interpretation.item?.contradictions || []).filter(isMeaningfulVisibleText);
    const liveActivitySummary = isMeaningfulVisibleText(data.signals.item?.activity?.summary) ? normalizedText(data.signals.item?.activity?.summary) : "";
    const contradictionSummary = isMeaningfulVisibleText(data.signals.item?.contradiction?.summary) ? normalizedText(data.signals.item?.contradiction?.summary) : "";
    const blockerReason = firstString(
      data.signals.item?.blocked?.reason,
      data.mission?.mission_summary?.blocked_reason,
      data.mission?.mission_summary?.blocking_questions?.[0],
      data.mission?.blocking_questions?.[0],
      data.mission?.mission_summary?.next_question,
      data.mission?.mission_summary?.clarification_reason,
    );
    const hasTrueBlocker =
      Boolean(data.signals.item?.blocked?.present || blockerReason) &&
      (data.mission?.mission_summary?.can_continue_without_input === false ||
        data.mission?.mission_summary?.operator_posture === "needs_operator_answer" ||
        data.mission?.operator_posture === "needs_operator_answer" ||
        Boolean(data.signals.item?.blocked?.present));
    const blockerText = hasTrueBlocker && isMeaningfulVisibleText(blockerReason) ? normalizedText(blockerReason) : "";
    const confidence = clamp(data.mission?.mission_summary?.confidence ?? 0.18, 0, 1);
    const currentState = firstString(data.mission?.current_state, data.state.item?.current_state, "planning");
    const blocked = Boolean(blockerText);
    const interpretationReady = Boolean(interpretationSummary || filteredMirrorNotes.length || interpretationPatterns.length || interpretationContradictions.length);
    const handoff =
      Boolean(data.signals.item?.handoff?.present || data.signals.item?.handoff?.target_role) &&
      includesAny(normalizedLower(data.signals.item?.handoff?.status), ["pending", "active"]);
    const phase = derivePhase(currentState, blocked, handoff, interpretationReady);

    const checkpoints = [
      Boolean(data.mission?.objective),
      Boolean(liveActivitySummary || latestRetrievalMessage || visibleAgentRuns.length),
      interpretationReady,
      phase === "returning" || phase === "complete",
    ];

    const lastUpdateMs = latestTimestamp([
      liveActivitySummary ? data.signals.item?.activity?.created_at : "",
      data.state.item?.latest_meaningful_activity?.created_at,
      latestVisibleRun?.created_at,
      latestRetrievalMessage?.created_at,
      visibleTriggers[0]?.created_at,
      visibleInterventions[0]?.created_at,
      latestMirrorNote?.created_at,
      data.mission?.last_updated,
    ]);

    const contradictionCount = data.signals.item?.contradiction?.count ?? interpretationContradictions.length ?? 0;
    const activity = Boolean(liveActivitySummary || latestRetrievalMessage || latestVisibleRun);
    const primarySource = latestMirrorNote
      ? "mirror_note"
      : latestRetrievalMessage
        ? "concierge_retrieval"
        : latestVisibleRun
          ? "role_output"
          : blockerText
            ? "blocker"
            : "quiet";
    const quiet = primarySource === "quiet";
    const intensity = clamp(
      confidence * 0.45 + (contradictionCount ? 0.25 : 0) + (activity ? 0.15 : 0) + (blocked ? 0.2 : 0),
      0.16,
      0.96,
    );

    const lens = blocked ? "memory_tension" : contradictionCount ? "contradictions" : handoff ? "handoff" : "activity";
    const emphasis = [
      latestRetrievalMessage ? "retrieval" : activity ? "activity" : "",
      contradictionCount ? "contradiction" : "",
      blocked ? "memory_tension" : "",
      latestVisibleRun ? "role_output" : "",
      handoff ? "handoff_edge" : "",
    ].filter(Boolean);

    const advisories: AdvisorySurface[] = [];
    if (latestRetrievalMessage) {
      const advisory = advisoryFromMessage(latestRetrievalMessage);
      if (advisory) advisories.push(advisory);
    }
    if (blockerText) {
      advisories.push({
        kind: "expedition_intervention",
        instruction: `Blocked: ${blockerText}`,
        reason: "Selected mission needs operator resolution before it can move cleanly.",
        strength: "high",
        source: "signals",
      });
    } else {
      visibleInterventions.forEach((item) => {
        advisories.push({
          kind: "expedition_intervention",
          instruction: firstString(item.blocked_reason || "", item.reason || "", item.action || ""),
          reason: "Visible mission intervention",
          strength: "high",
          created_at: item.created_at,
          source: "timeline",
        });
      });
    }

    const progress: DerivedExpeditionProgress = {
      phase,
      status: phase === "complete" ? "complete" : blocked ? "blocked" : activity ? "running" : "idle",
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
        data.signals.item?.stall?.present && blocked ? "stall_trace" : "",
        handoff ? "ghost_pressure" : "",
        latestMirrorNote ? "mirror_summary" : "",
      ].filter(Boolean),
      summary:
        latestMirrorNote?.text ||
        latestRetrievalMessage?.message ||
        latestVisibleRun?.summary ||
        liveActivitySummary ||
        (blockerText ? `Blocked: ${blockerText}` : "Mirror is quiet."),
      secondary_summary:
        primarySource === "mirror_note"
          ? "Latest mission-local mirror note."
          : primarySource === "concierge_retrieval"
            ? "Read-only concierge retrieval from saved mirror notes."
            : primarySource === "role_output"
              ? `Latest active role output from ${firstString(latestVisibleRun?.role, "the active role")}.`
              : primarySource === "blocker"
                ? "The visible lane only surfaces blockers when the mission cannot continue cleanly."
                : "No recent mirror note, retrieval, active role output, or blocker is visible for this mission.",
      primary_source: primarySource,
      quiet,
    };

    const timelineItem = data.timeline.item || {
      recent_agent_runs: [],
      recent_triggers: [],
      recent_interventions: [],
    };
    const filteredTimeline = {
      ...data.timeline,
      item: {
        ...timelineItem,
        recent_agent_runs: visibleAgentRuns,
        recent_triggers: blockerText ? visibleTriggers : [],
        recent_interventions: visibleInterventions,
      },
    };
    const filteredInterpretation = {
      ...data.interpretation,
      item: data.interpretation.item
        ? {
            ...data.interpretation.item,
            summary: interpretationSummary,
            patterns: quiet ? [] : interpretationPatterns.slice(0, 4),
            contradictions: quiet ? [] : interpretationContradictions.slice(0, 3),
          }
        : null,
    };
    const filteredSignals = {
      ...data.signals,
      item: data.signals.item
        ? {
            ...data.signals.item,
            activity: liveActivitySummary
              ? {
                  ...(data.signals.item.activity || {}),
                  summary: liveActivitySummary,
                }
              : null,
            contradiction:
              contradictionCount || contradictionSummary
                ? {
                    ...(data.signals.item.contradiction || {}),
                    summary: contradictionSummary,
                    count: contradictionCount,
                  }
                : null,
            blocked: blockerText
              ? {
                  ...(data.signals.item.blocked || {}),
                  reason: blockerText,
                  present: true,
                }
              : null,
          }
        : null,
    };

    return {
      ...data,
      expeditions: visibleExpeditions,
      timeline: filteredTimeline,
      interpretation: filteredInterpretation,
      signals: filteredSignals,
      messages: filteredMessages,
      mirrorNotes: filteredMirrorNotes,
      progress,
      expressionSpec,
      advisories: advisories.slice(0, 4),
    };
  }, [data, mirrorNotes, visibleExpeditions]);
}
