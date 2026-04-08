import type {
  DraftRecord,
  DismissBucket,
  ExpeditionGroup,
  ExpeditionStatusBadge,
  ExpeditionSummary,
  FeedState,
  MissionAttentionItem,
  QueueSummary,
  StatusResponse,
  StripTone,
} from "./dashboardTypes";

export function isMissionParked(
  expedition?:
    | {
        parking_status?: { status?: string | null } | null;
        triage_bucket?: string | null;
        operator_posture?: string | null;
        mission_summary?: { operator_posture?: string | null; triage_bucket?: string | null } | null;
      }
    | null
): boolean {
  if (!expedition) return false;
  return (
    expedition.parking_status?.status === "parked" ||
    expedition.triage_bucket === "parked" ||
    expedition.operator_posture === "parked" ||
    expedition.mission_summary?.triage_bucket === "parked" ||
    expedition.mission_summary?.operator_posture === "parked"
  );
}

function expeditionPriority(expedition: ExpeditionSummary, selectedMissionId?: string | null): number {
  if (expedition.mission_id === selectedMissionId) return 0;
  if (isMissionParked(expedition)) return 4;
  if (expedition.triage_bucket === "review") return 1;
  if (expedition.triage_bucket === "waiting") return 2;
  if (expedition.triage_bucket === "do_now") return 3;
  return 5;
}

export function groupExpeditions(expeditions: ExpeditionSummary[], selectedMissionId?: string | null) {
  const grouped = new Map<string, ExpeditionSummary[]>();
  for (const expedition of expeditions) {
    const groupKey = expedition.duplicate_group_key || expedition.objective_normalized || expedition.mission_id;
    if (!grouped.has(groupKey)) grouped.set(groupKey, []);
    grouped.get(groupKey)!.push(expedition);
  }

  const groups: ExpeditionGroup[] = Array.from(grouped.entries()).map(([groupKey, items]) => {
    const sortedItems = [...items].sort((a, b) => {
      const rankDiff = (a.duplicate_rank ?? 9999) - (b.duplicate_rank ?? 9999);
      if (rankDiff !== 0) return rankDiff;
      const lastUpdatedDiff = (b.last_updated || "").localeCompare(a.last_updated || "");
      if (lastUpdatedDiff !== 0) return lastUpdatedDiff;
      const createdDiff = (b.created_at || "").localeCompare(a.created_at || "");
      if (createdDiff !== 0) return createdDiff;
      return (a.mission_id || "").localeCompare(b.mission_id || "");
    });
    const primary = sortedItems.find((item) => item.is_group_primary) ?? sortedItems[0];
    return {
      group_key: groupKey,
      primary,
      items: sortedItems,
      duplicate_count: sortedItems.length,
      hidden_duplicate_count: Math.max(0, sortedItems.length - 1),
    };
  });

  groups.sort((a, b) => {
    const priorityDiff = expeditionPriority(a.primary, selectedMissionId) - expeditionPriority(b.primary, selectedMissionId);
    if (priorityDiff !== 0) return priorityDiff;
    const updatedDiff = (b.primary.last_updated || "").localeCompare(a.primary.last_updated || "");
    if (updatedDiff !== 0) return updatedDiff;
    const createdDiff = (b.primary.created_at || "").localeCompare(a.primary.created_at || "");
    if (createdDiff !== 0) return createdDiff;
    return (a.primary.mission_id || "").localeCompare(b.primary.mission_id || "");
  });

  const parked = groups.filter((group) => missionFeedState(group.primary) === "PARKED");
  const nonParked = groups.filter((group) => missionFeedState(group.primary) !== "PARKED");
  const selectedParked =
    selectedMissionId && parked.some((group) => group.items.some((item) => item.mission_id === selectedMissionId))
      ? parked.filter((group) => group.primary.mission_id === selectedMissionId || group.items.some((item) => item.mission_id === selectedMissionId))
      : [];

  return {
    groups: [...nonParked, ...selectedParked].slice(0, 8),
    allGroups: groups,
    hiddenParkedCount: Math.max(0, parked.length - selectedParked.length),
    hiddenDuplicateCount: groups.reduce((sum, group) => sum + group.hidden_duplicate_count, 0),
    totalGroups: groups.length,
  };
}

export function missionFeedState(expedition: ExpeditionSummary): FeedState {
  if (isMissionParked(expedition)) return "PARKED";
  if (expedition.queue_hygiene?.review_ready || expedition.triage_bucket === "review") return "RETURNED";
  if (
    expedition.queue_hygiene?.blocked_candidate ||
    expedition.operator_posture === "needs_operator_answer" ||
    expedition.triage_bucket === "waiting" ||
    expedition.status_badge === "waiting_for_user"
  ) {
    return "BLOCKED";
  }
  return "ACTIVE";
}

export function missionConfidenceLabel(expedition: ExpeditionSummary): "LOW" | "MEDIUM" | "HIGH" {
  const label = expedition.mission_summary?.confidence_label;
  if (label === "high") return "HIGH";
  if (label === "low") return "LOW";
  return "MEDIUM";
}

export function missionFeedSummary(expedition: ExpeditionSummary): string {
  return (
    expedition.mission_summary?.latest_summary ||
    expedition.mission_summary?.summary ||
    expedition.summary ||
    expedition.operator_posture_reason ||
    expedition.queue_action_reason ||
    "No compressed mission summary yet."
  );
}

export function missionPrimaryActionLabel(expedition: ExpeditionSummary): string {
  const state = missionFeedState(expedition);
  if (state === "BLOCKED") return "Resolve";
  if (state === "RETURNED") return "Review";
  if (state === "PARKED") return "Resume";
  return "Continue";
}

export function getRecordString(record: unknown, key: string): string {
  if (!record || typeof record !== "object") return "";
  const value = (record as Record<string, unknown>)[key];
  return typeof value === "string" ? value : "";
}

export function getRecordObject(record: unknown, key: string): Record<string, unknown> | null {
  if (!record || typeof record !== "object") return null;
  const value = (record as Record<string, unknown>)[key];
  if (!value || typeof value !== "object") return null;
  return value as Record<string, unknown>;
}

export function dismissLabelForBucket(bucket: DismissBucket): string {
  if (bucket === "duplicates") return "Hide duplicate";
  if (bucket === "archive") return "Mark archive candidate";
  return "Park mission";
}

export function dismissBucketForGroup(group: ExpeditionGroup): DismissBucket {
  const expedition = group.primary;
  if (group.duplicate_count > 1) return "duplicates";
  if (missionFeedState(expedition) === "RETURNED" || expedition.queue_hygiene?.archive_candidate) return "archive";
  return "parked";
}

export function titleCaseLabel(value: string): string {
  return value
    .split(/[\s_]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function compactLabel(value: string | null | undefined, fallback: string): string {
  const text = String(value || "").trim();
  return text ? titleCaseLabel(text) : fallback;
}

export function missionStateGaugeLabel(args: {
  parked: boolean;
  blocked: boolean;
  caution: boolean;
}): "ACTIVE" | "CAUTION" | "BLOCKED" | "PARKED" {
  if (args.parked) return "PARKED";
  if (args.blocked) return "BLOCKED";
  if (args.caution) return "CAUTION";
  return "ACTIVE";
}

export function queuePressureLabel(queueSummary: QueueSummary, totalExpeditions: number): "LIGHT" | "MODERATE" | "OVERLOADED" {
  const totalQueued = queueSummary.total_queued ?? totalExpeditions;
  const blocked = queueSummary.blocked ?? 0;
  const duplicates = queueSummary.duplicate_candidates ?? 0;
  if (totalQueued >= 8 || blocked >= 3 || duplicates >= 3) return "OVERLOADED";
  if (totalQueued >= 4 || blocked >= 1 || duplicates >= 1) return "MODERATE";
  return "LIGHT";
}

export function blockerTypeLabel(args: {
  canContinue: boolean;
  operatorPosture: string;
  blockingQuestions: string[];
  queueHygiene?: ExpeditionSummary["queue_hygiene"];
  blockedReason: string;
}): "HUMAN" | "SYSTEM" | "JUNK" {
  if (args.queueHygiene?.junk_pattern || args.queueHygiene?.duplicate_candidate || args.queueHygiene?.archive_candidate) return "JUNK";
  if (!args.canContinue || args.operatorPosture === "needs_operator_answer" || args.blockingQuestions.length > 0) return "HUMAN";
  return /(retry|budget|handoff|system|refresh|pending|guard|blocked)/i.test(args.blockedReason || "") ? "SYSTEM" : "SYSTEM";
}

export function compactIntentLabel(value: string, fallback: string): string {
  const trimmed = value.replace(/\s+/g, " ").trim().replace(/[.?!,:;]+$/g, "");
  if (!trimmed) return fallback;
  return trimmed.length > 72 ? `${trimmed.slice(0, 69).trimEnd()}...` : trimmed;
}

export function deriveQueueCounts(data: StatusResponse): number[] {
  const events = data.events_recent || [];
  return [
    events.filter((e) => e.event_type === "hermes_write").length,
    events.filter((e) => e.event_type === "watcher_scan" || e.event_type === "promote").length,
    events.filter((e) => e.event_type === "approve").length,
    data.honcho_sessions_total || 0,
  ];
}

export function deriveGateOpen(data: StatusResponse): boolean[] {
  const events = data.events_recent || [];
  return [
    true,
    events.some((e) => e.event_type === "watcher_scan"),
    events.some((e) => e.event_type === "approve" && e.status === "success"),
    events.some((e) => e.event_type === "honcho_bridge" && e.status === "success"),
  ];
}

export function deriveAttentionItems(expeditions: ExpeditionSummary[], petitionDrafts: DraftRecord[], repeatedItemCount: number): MissionAttentionItem[] {
  const items: MissionAttentionItem[] = [];
  for (const expedition of expeditions) {
    if (isMissionParked(expedition)) {
      items.push({ key: `parked-${expedition.mission_id}`, mission_id: expedition.mission_id, title: expedition.objective || expedition.mission_id, detail: expedition.operator_posture_reason || expedition.summary || expedition.current_state, badge: "Parked", tone: "watch" });
    } else if (expedition.triage_bucket === "waiting" || expedition.operator_posture === "needs_operator_answer" || expedition.status_badge === "waiting_for_user") {
      items.push({ key: `wait-${expedition.mission_id}`, mission_id: expedition.mission_id, title: expedition.objective || expedition.mission_id, detail: expedition.operator_posture_reason || expedition.summary || expedition.current_state, badge: "Needs operator", tone: "watch" });
    } else if (expedition.triage_bucket === "do_now" && expedition.operator_posture === "proceed_with_assumptions") {
      items.push({ key: `assume-${expedition.mission_id}`, mission_id: expedition.mission_id, title: expedition.objective || expedition.mission_id, detail: expedition.operator_posture_reason || expedition.summary || "Can continue under assumptions", badge: "Assumption-capable", tone: "good" });
    } else if (expedition.status_badge === "ready_for_review" || expedition.current_state === "PACKAGE_READY") {
      items.push({ key: `review-${expedition.mission_id}`, mission_id: expedition.mission_id, title: expedition.objective || expedition.mission_id, detail: expedition.summary || "ready for review", badge: "Ready for review", tone: "good" });
    }
  }

  for (const draft of petitionDrafts) {
    const preview = draft.review_preview;
    if (draft.ok && preview && !preview.submission_allowed) {
      items.push({
        key: `draft-${draft.source_path || draft.draft?.petition_id || "draft"}`,
        title: draft.draft?.petition_id || draft.source_path || "draft",
        detail: preview.submission_gate?.reason || "review preview blocked",
        badge: "Draft blocked",
        tone: "watch",
      });
    }
  }

  if (repeatedItemCount > 0) {
    items.push({
      key: "noisy-signals",
      title: "Repeated telemetry",
      detail: `${repeatedItemCount} repeated record${repeatedItemCount === 1 ? "" : "s"} in recent events`,
      badge: "Noisy",
      tone: "watch",
    });
  }

  return items.slice(0, 8);
}

export function deriveFeedBuckets(args: {
  visibleGroups: ReturnType<typeof groupExpeditions>;
  dismissedMissionBuckets: Record<string, DismissBucket>;
}) {
  const allExpeditionGroups = args.visibleGroups.allGroups;
  const mainFeedGroups = allExpeditionGroups.filter((group) => {
    const missionId = group.primary.mission_id;
    if (args.dismissedMissionBuckets[missionId]) return false;
    const state = missionFeedState(group.primary);
    if (group.primary.queue_hygiene?.archive_candidate) return false;
    if (state === "PARKED") return false;
    return true;
  });
  const parkedFeedGroups = allExpeditionGroups.filter((group) => {
    const missionId = group.primary.mission_id;
    return args.dismissedMissionBuckets[missionId] === "parked" || missionFeedState(group.primary) === "PARKED";
  });
  const archiveFeedGroups = allExpeditionGroups.filter((group) => {
    const missionId = group.primary.mission_id;
    return args.dismissedMissionBuckets[missionId] === "archive" || !!group.primary.queue_hygiene?.archive_candidate;
  });
  const duplicateFeedGroups = allExpeditionGroups.filter((group) => {
    const missionId = group.primary.mission_id;
    return args.dismissedMissionBuckets[missionId] === "duplicates" || group.duplicate_count > 1;
  });

  return { mainFeedGroups, parkedFeedGroups, archiveFeedGroups, duplicateFeedGroups };
}

export function derivePrimaryAction(args: {
  queuePressure: "LIGHT" | "MODERATE" | "OVERLOADED";
  missionStateGauge: "ACTIVE" | "CAUTION" | "BLOCKED" | "PARKED";
  blockerType: "HUMAN" | "SYSTEM" | "JUNK";
  selectedMissionStatusBadge?: ExpeditionStatusBadge;
  latestDraftReviewPreview: Record<string, unknown> | null;
  composerEligibleMissionId: string | null;
  composerWantsNewMission: boolean;
  composerRetargetedFromParkedMission: boolean;
  unifiedIntentText: string;
}) {
  if (args.queuePressure === "OVERLOADED") {
    return { label: "Clean Queue", detail: "Group duplicates, park blocked missions, and mark archive candidates without deleting anything.", action: "clean_queue" as const };
  }
  if (args.missionStateGauge === "PARKED" && !args.unifiedIntentText.trim()) {
    return { label: "Resume mission", detail: "Bring the parked mission back into the active lane.", action: "resume" as const };
  }
  if (args.missionStateGauge === "BLOCKED") {
    return { label: "Resolve blocker", detail: `Current blocker type: ${args.blockerType}.`, action: "resolve_blocker" as const };
  }
  if (args.selectedMissionStatusBadge === "ready_for_review" || !!args.latestDraftReviewPreview) {
    return { label: "Review mission", detail: "Open the latest review-ready material without changing backend behavior.", action: "review" as const };
  }
  if (!args.composerEligibleMissionId || args.composerWantsNewMission) {
    return { label: "Start mission", detail: "Create a new mission from the confirmed intent in the top input.", action: "start" as const };
  }
  return {
    label: "Continue mission",
    detail: args.composerRetargetedFromParkedMission
      ? "Commit the confirmed intent to another eligible active mission until the parked mission is explicitly resumed."
      : "Commit the confirmed intent to the focused mission through an explicit safe action.",
    action: "continue" as const,
  };
}

export function deriveExpeditionStatusTone(): Record<ExpeditionStatusBadge, StripTone> {
  return {
    waiting_for_user: "watch",
    researching: "good",
    ready_for_review: "good",
    idle: "off",
  };
}
