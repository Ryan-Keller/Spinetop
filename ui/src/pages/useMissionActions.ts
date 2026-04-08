import type { MutableRefObject } from "react";

import { titleCaseLabel } from "./dashboardSelectors";
import type {
  AssumptionEntry,
  ControlTowerIntervention,
  DismissBucket,
  ExpeditionDetail,
  ExpeditionGroup,
  ExpeditionSummary,
  MissionChatMessage,
  MissionInputRecord,
  PromptTranslation,
  UiNotice,
} from "./dashboardTypes";

type Setter<T> = (value: T | ((prev: T) => T)) => void;

type UseMissionActionsArgs = {
  apiBase: string;
  load: (options?: { preserveScroll?: boolean }) => Promise<void>;
  selectedMissionId: string | null;
  setSelectedMissionId: Setter<string | null>;
  selectedMission: ExpeditionDetail | null;
  setSelectedMission: Setter<ExpeditionDetail | null>;
  selectedMissionSummary: { mission_id: string } | null;
  setViewMode: Setter<"missions" | "diagnostics">;
  setSelectedDraftPath: Setter<string | null>;
  workbenchFolder: string;
  setWorkbenchFolder: Setter<string>;
  newMissionObjective: string;
  setNewMissionObjective: Setter<string>;
  unifiedIntentText: string;
  selectedMissionIsParked: boolean;
  composerEligibleMissionId: string | null;
  activeTranslationPreview: PromptTranslation | null;
  missionInputText: string;
  translatorDraftText: string;
  missionSummaryOperatorReason: string;
  missionSummaryBlockedReason: string;
  missionSummaryNextAnswer: string;
  missionSummaryQuestion: string;
  controlTowerSummary: ExpeditionDetail["control_tower_summary"] | null;
  selectedQueueHygiene: ExpeditionDetail["queue_hygiene"] | undefined;
  latestDraftPreviewPath: string;
  promptTranslationPreview: PromptTranslation | null;
  duplicateFeedGroups: ExpeditionGroup[];
  archiveFeedGroups: ExpeditionGroup[];
  blockedQueueItems: ExpeditionSummary[];
  dominantAction: { action: "clean_queue" | "resume" | "resolve_blocker" | "review" | "start" | "continue" };
  blockerType: "HUMAN" | "SYSTEM" | "JUNK";
  missionSaving: boolean;
  setMissionSaving: Setter<boolean>;
  setTranslatorSaving: Setter<boolean>;
  setMissionActionLabel: Setter<string>;
  setUiNotice: Setter<UiNotice | null>;
  setErrorText: Setter<string>;
  clearUnifiedIntentDraft: (draftKey?: string | null) => void;
  clearMissionInputDraft: (missionId?: string | null) => void;
  clearMissionChatDraft: (missionId?: string | null) => void;
  clearTranslatorDraft: (missionId?: string | null) => void;
  setMissionInputDrafts: Setter<Record<string, string>>;
  setMissionChatDrafts: Setter<Record<string, string>>;
  setTranslatorPreviewByMission: Setter<Record<string, PromptTranslation | null>>;
  setDismissedTranslationByMission: Setter<Record<string, string | null>>;
  rememberDismissedMission: (missionId: string, bucket: DismissBucket) => void;
  setTriageMode: Setter<boolean>;
  setShowArchiveCandidates: Setter<boolean>;
  setShowParkedMissions: Setter<boolean>;
  setShowDuplicateMissions: Setter<boolean>;
  missionInputInFlightRef: MutableRefObject<string | null>;
  missionChatInFlightRef: MutableRefObject<string | null>;
  missionChatComposerRef: MutableRefObject<HTMLTextAreaElement | null>;
};

export function useMissionActions(args: UseMissionActionsArgs) {
  const refreshAssumptions = async () => {
    if (!args.selectedMissionId) {
      args.setErrorText("Select an expedition first");
      return;
    }
    try {
      args.setMissionSaving(true);
      args.setMissionActionLabel("Refreshing assumptions");
      const res = await fetch(`${args.apiBase}/expeditions/${args.selectedMissionId}/refresh-assumptions`, { method: "POST" });
      const payload = (await res.json()) as {
        ok?: boolean;
        item?: ExpeditionDetail;
        refresh?: { active_assumption_count?: number };
        error?: string;
      };
      if (!res.ok || !payload.ok || !payload.item) throw new Error(payload.error || `HTTP ${res.status}`);
      args.setSelectedMission(payload.item);
      args.setUiNotice({
        tone: "good",
        title: "Assumptions refreshed",
        detail: `${payload.refresh?.active_assumption_count ?? payload.item.active_assumption_count ?? 0} active mission-local assumptions are now visible.`,
      });
      await args.load();
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : "Assumption refresh failed");
    } finally {
      args.setMissionSaving(false);
      args.setMissionActionLabel("");
    }
  };

  const reviewAssumption = async (assumptionId: string, action: "confirm" | "reject") => {
    if (!args.selectedMissionId) {
      args.setErrorText("Select an expedition first");
      return;
    }
    try {
      args.setMissionSaving(true);
      args.setMissionActionLabel(action === "confirm" ? "Accepting assumption" : "Rejecting assumption");
      const res = await fetch(`${args.apiBase}/expeditions/${args.selectedMissionId}/assumptions/${assumptionId}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = (await res.json()) as { ok?: boolean; item?: ExpeditionDetail; assumption?: AssumptionEntry; error?: string };
      if (!res.ok || !payload.ok || !payload.item) throw new Error(payload.error || `HTTP ${res.status}`);
      args.setSelectedMission(payload.item);
      args.setUiNotice({
        tone: action === "confirm" ? "good" : "watch",
        title: action === "confirm" ? "Assumption accepted" : "Assumption rejected",
        detail: payload.assumption?.text || `Mission-local assumption ${assumptionId} was reviewed.`,
      });
      await args.load();
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : "Assumption review failed");
    } finally {
      args.setMissionSaving(false);
      args.setMissionActionLabel("");
    }
  };

  const syncRunnerReturns = async () => {
    if (!args.selectedMissionId) {
      args.setErrorText("Select an expedition first");
      return;
    }
    try {
      args.setMissionSaving(true);
      args.setMissionActionLabel("Syncing helper returns");
      const res = await fetch(`${args.apiBase}/expeditions/${args.selectedMissionId}/sync-runner-returns`, { method: "POST" });
      const payload = (await res.json()) as {
        ok?: boolean;
        item?: ExpeditionDetail;
        sync?: { created_count?: number; runner_return_count?: number };
        error?: string;
      };
      if (!res.ok || !payload.ok || !payload.item) throw new Error(payload.error || `HTTP ${res.status}`);
      args.setSelectedMission(payload.item);
      args.setUiNotice({
        tone: "good",
        title: "Helper returns synced",
        detail: `${payload.sync?.created_count ?? 0} new mission-local helper return packet(s) captured.`,
      });
      await args.load();
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : "Runner return sync failed");
    } finally {
      args.setMissionSaving(false);
      args.setMissionActionLabel("");
    }
  };

  const openReviewPreview = (previewPath?: string | null) => {
    if (previewPath) args.setSelectedDraftPath(previewPath);
    args.setViewMode("diagnostics");
    args.setUiNotice({
      tone: "info",
      title: "Review preview opened",
      detail: previewPath ? `Draft preview focus set to ${previewPath}.` : "Draft previews are visible in diagnostics.",
    });
  };

  const createMission = async (objectiveOverride?: string) => {
    const objective = (objectiveOverride ?? args.newMissionObjective).trim();
    if (!objective) {
      args.setErrorText("Objective is required to create an expedition");
      return;
    }
    try {
      args.setMissionSaving(true);
      args.setMissionActionLabel("Creating expedition");
      const res = await fetch(`${args.apiBase}/expeditions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective }),
      });
      const payload = (await res.json()) as { ok?: boolean; item?: ExpeditionDetail; error?: string };
      if (!res.ok || !payload.ok || !payload.item) throw new Error(payload.error || `HTTP ${res.status}`);
      args.setNewMissionObjective("");
      args.clearUnifiedIntentDraft("__new__");
      args.setSelectedMissionId(payload.item.mission_id);
      args.setSelectedMission(payload.item);
      args.setWorkbenchFolder(payload.item.workbench.folders[0]?.name || args.workbenchFolder);
      args.clearMissionInputDraft(payload.item.mission_id);
      args.clearMissionChatDraft(payload.item.mission_id);
      args.setUiNotice({
        tone: "good",
        title: "Mission created",
        detail: `${payload.item.mission_id} is active and ready for operator input.`,
      });
      args.setViewMode("missions");
      await args.load();
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : "Mission creation failed");
    } finally {
      args.setMissionSaving(false);
      args.setMissionActionLabel("");
    }
  };

  const sendMissionInput = async (contentOverride?: string, missionIdOverride?: string) => {
    const missionId = missionIdOverride || args.selectedMissionId;
    if (!missionId) {
      args.setErrorText("Select an expedition first");
      return;
    }
    const content = (contentOverride ?? args.missionInputText).trim();
    if (!content) {
      args.setErrorText("Mission input cannot be empty");
      return;
    }
    const submissionKey = `${missionId}:${content}`;
    if (args.missionInputInFlightRef.current === submissionKey) return;
    try {
      args.missionInputInFlightRef.current = submissionKey;
      args.setMissionSaving(true);
      args.setMissionActionLabel("Sending mission input");
      const res = await fetch(`${args.apiBase}/expeditions/${missionId}/input`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const payload = (await res.json()) as {
        ok?: boolean;
        item?: MissionInputRecord;
        translation?: PromptTranslation;
        mission?: ExpeditionDetail;
        error?: string;
      };
      if (!res.ok || !payload.ok) throw new Error(payload.error || `HTTP ${res.status}`);
      args.clearMissionInputDraft(missionId);
      if (!contentOverride) args.clearUnifiedIntentDraft(missionId);
      if (payload.mission) args.setSelectedMission(payload.mission);
      if (payload.translation) {
        args.setTranslatorPreviewByMission((prev) => ({ ...prev, [missionId]: payload.translation ?? null }));
        args.setDismissedTranslationByMission((prev) => ({ ...prev, [missionId]: null }));
      }
      args.setUiNotice({
        tone: "good",
        title: "Mission updated",
        detail: "The confirmed action landed once in the workbench intake folder as mission input.",
      });
      await args.load();
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : "Mission input failed");
    } finally {
      args.missionInputInFlightRef.current = null;
      args.setMissionSaving(false);
      args.setMissionActionLabel("");
    }
  };

  const translateMissionPrompt = async (contentOverride?: string, missionIdOverride?: string, silent = false) => {
    const missionId = missionIdOverride || args.selectedMissionId;
    if (!missionId) {
      args.setErrorText("Select an expedition first");
      return;
    }
    const content = (contentOverride ?? args.translatorDraftText).trim();
    if (!content) {
      args.setErrorText("Prompt translator input cannot be empty");
      return;
    }
    try {
      args.setTranslatorSaving(true);
      const res = await fetch(`${args.apiBase}/expeditions/${missionId}/translate-prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const payload = (await res.json()) as { ok?: boolean; translation?: PromptTranslation; mission?: ExpeditionDetail; error?: string };
      if (!res.ok || !payload.ok || !payload.translation) throw new Error(payload.error || `HTTP ${res.status}`);
      if (payload.mission) args.setSelectedMission(payload.mission);
      args.setTranslatorPreviewByMission((prev) => ({ ...prev, [missionId]: payload.translation ?? null }));
      args.setDismissedTranslationByMission((prev) => ({ ...prev, [missionId]: null }));
      if (!silent) {
        args.setUiNotice({ tone: "info", title: "Prompt translated", detail: "Proposal saved for review only. Nothing was executed." });
      }
      await args.load();
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : "Prompt translation failed");
    } finally {
      args.setTranslatorSaving(false);
    }
  };

  const sendMissionChat = async (content: string, quickReply?: string, missionIdOverride?: string | null) => {
    const missionId = missionIdOverride || args.selectedMissionId;
    if (!missionId) {
      args.setErrorText("Select an expedition first");
      return;
    }
    const message = content.trim();
    if (!message) {
      args.setErrorText("Chat message cannot be empty");
      return;
    }
    const submissionKey = `${missionId}:${quickReply || ""}:${message}`;
    if (args.missionChatInFlightRef.current === submissionKey) return;
    try {
      args.missionChatInFlightRef.current = submissionKey;
      args.setMissionSaving(true);
      args.setMissionActionLabel("Sending mission chat");
      const res = await fetch(`${args.apiBase}/expeditions/${missionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: message, quick_reply: quickReply || undefined }),
      });
      const payload = (await res.json()) as {
        ok?: boolean;
        kind?: string;
        item?: ExpeditionDetail;
        messages?: MissionChatMessage[];
        exchange?: Record<string, unknown>;
        response?: { kind?: string; artifact_path?: string; message?: string };
        save_detected?: boolean;
        mirror_artifact?: { path?: string };
        artifact_path?: string;
        message?: string;
        error?: string;
      };
      if (!res.ok || !payload.ok) throw new Error(payload.error || `HTTP ${res.status}`);
      args.clearMissionChatDraft(missionId);
      if (payload.item) args.setSelectedMission(payload.item);
      const isOperatorSave = payload.kind === "operator_save" || payload.save_detected;
      const isConciergeMirrorRetrieval = payload.kind === "concierge_mirror_retrieval" || payload.response?.kind === "concierge_mirror_retrieval";
      const saveArtifactPath = payload.artifact_path || payload.mirror_artifact?.path || payload.response?.artifact_path || "";
      args.setUiNotice({
        tone: "good",
        title: isOperatorSave ? "Mirror note saved" : isConciergeMirrorRetrieval ? "Concierge retrieval" : "Mission chat updated",
        detail: isOperatorSave
          ? (saveArtifactPath ? `Saved once to ${saveArtifactPath}.` : (payload.message || "Saved once to the mission-local mirror lane."))
          : isConciergeMirrorRetrieval
            ? (payload.response?.message || payload.message || "Mirror retrieval completed once for this mission.")
          : (quickReply ? `Quick reply sent once: ${quickReply}` : "Your message was accepted and added once to the mission chat."),
      });
      await args.load();
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : "Mission chat failed");
    } finally {
      args.missionChatInFlightRef.current = null;
      args.setMissionSaving(false);
      args.setMissionActionLabel("");
    }
  };

  const runMissionQuickReply = async (reply: { label: string; value: string }) => {
    if (reply.value === "Open review preview") {
      openReviewPreview(args.latestDraftPreviewPath);
      return;
    }
    await sendMissionChat(reply.value, reply.value);
  };

  const setMissionParking = async (status: "parked" | "active", missionIdOverride?: string) => {
    const missionId = missionIdOverride || args.selectedMissionId;
    if (!missionId) {
      args.setErrorText("Select an expedition first");
      return;
    }
    try {
      args.setMissionSaving(true);
      args.setMissionActionLabel(status === "parked" ? "Parking mission" : "Resuming mission");
      const reason = status === "parked" ? args.missionSummaryOperatorReason || args.missionSummaryBlockedReason || "Parked from the mission console." : "Resumed from the mission console.";
      const resumeHint = status === "parked" ? args.missionSummaryNextAnswer || args.missionSummaryQuestion : "";
      const res = await fetch(`${args.apiBase}/expeditions/${missionId}/parking`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, reason, resume_hint: resumeHint || undefined }),
      });
      const payload = (await res.json()) as { ok?: boolean; item?: ExpeditionDetail; error?: string };
      if (!res.ok || !payload.ok || !payload.item) throw new Error(payload.error || `HTTP ${res.status}`);
      if (args.selectedMissionId === missionId) args.setSelectedMission(payload.item);
      args.setUiNotice({
        tone: "good",
        title: status === "parked" ? "Mission parked" : "Mission resumed",
        detail: status === "parked" ? "The mission left the main feed and stays retrievable in parked missions." : "The mission is active again in the main feed.",
      });
      await args.load();
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : "Mission parking failed");
    } finally {
      args.setMissionSaving(false);
      args.setMissionActionLabel("");
    }
  };

  const runLoggedControlTowerIntervention = async (
    action: string,
    options?: { label?: string; reason?: string },
    missionIdOverride?: string
  ) => {
    const missionId = missionIdOverride || args.selectedMissionId;
    if (!missionId) {
      args.setErrorText("Select an expedition first");
      return false;
    }
    const label = options?.label || titleCaseLabel(action.replace(/_/g, " "));
    try {
      args.setMissionSaving(true);
      args.setMissionActionLabel(label);
      const res = await fetch(`${args.apiBase}/expeditions/${missionId}/interventions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, reason: options?.reason || undefined }),
      });
      const payload = (await res.json()) as { ok?: boolean; blocked?: boolean; error?: string; item?: ExpeditionDetail; intervention?: ControlTowerIntervention };
      if (payload.item && args.selectedMissionId === missionId) args.setSelectedMission(payload.item);
      if (res.status === 409 || payload.blocked) {
        const blockedTitle =
          action === "mark_archive_candidate" ? "Archive candidate rejected" : action === "retry_bounded_action" ? "Bounded retry unavailable" : `${label} unavailable`;
        args.setUiNotice({
          tone: "watch",
          title: blockedTitle,
          detail: payload.error || payload.intervention?.blocked_reason || "This intervention is not currently safe to apply.",
        });
        return false;
      }
      if (!res.ok || !payload.ok || !payload.item) throw new Error(payload.error || `HTTP ${res.status}`);
      const successTitle =
        action === "mark_archive_candidate"
          ? "Archive candidate marked"
          : action === "retry_bounded_action"
            ? "Bounded retry requested"
            : action === "refresh_assumptions"
              ? "Assumptions refreshed"
              : action === "sync_helper_returns"
                ? "Helper return sync requested"
                : action === "resume_mission"
                  ? "Mission resumed"
                  : `${label} complete`;
      args.setUiNotice({
        tone: "good",
        title: successTitle,
        detail: payload.intervention?.reason || "The mission state was updated without changing system rules.",
      });
      await args.load();
      return true;
    } catch (error) {
      args.setErrorText(error instanceof Error ? error.message : `${label} failed`);
      return false;
    } finally {
      args.setMissionSaving(false);
      args.setMissionActionLabel("");
    }
  };

  const dismissMissionGroup = async (group: ExpeditionGroup) => {
    const expedition = group.primary;
    if (group.duplicate_count > 1) {
      args.rememberDismissedMission(expedition.mission_id, "duplicates");
      args.setUiNotice({
        tone: "good",
        title: `${group.hidden_duplicate_count || 1} duplicate${(group.hidden_duplicate_count || 1) === 1 ? "" : "s"} collapsed`,
        detail: `${expedition.objective || expedition.mission_id} stays available in duplicates.`,
      });
      return;
    }
    if (expedition.queue_hygiene?.archive_candidate || expedition.triage_bucket === "review") {
      const ok = await runLoggedControlTowerIntervention(
        "mark_archive_candidate",
        {
          label: "Marking archive candidate",
          reason: expedition.queue_action_reason || "Operator dismissed the mission from the feed into archive candidates.",
        },
        expedition.mission_id
      );
      if (ok) {
        args.rememberDismissedMission(expedition.mission_id, "archive");
        args.setUiNotice({
          tone: "good",
          title: "Archive candidate marked",
          detail: `${expedition.objective || expedition.mission_id} left the main feed and stays retrievable in archive candidates.`,
        });
      }
      return;
    }
    await setMissionParking("parked", expedition.mission_id);
    args.rememberDismissedMission(expedition.mission_id, "parked");
    args.setUiNotice({
      tone: "good",
      title: "Mission parked",
      detail: `${expedition.objective || expedition.mission_id} left the main feed and stays retrievable in parked missions.`,
    });
  };

  const collapseDuplicateGroups = async () => {
    args.duplicateFeedGroups.forEach((group) => args.rememberDismissedMission(group.primary.mission_id, "duplicates"));
    args.setShowDuplicateMissions(true);
    const collapsedCount = args.duplicateFeedGroups.reduce((sum, group) => sum + Math.max(1, group.hidden_duplicate_count || 0), 0);
    args.setUiNotice({
      tone: "good",
      title: `${collapsedCount} duplicate${collapsedCount === 1 ? "" : "s"} collapsed`,
      detail: `${args.duplicateFeedGroups.length} duplicate group${args.duplicateFeedGroups.length === 1 ? "" : "s"} moved out of the main feed.`,
    });
  };

  const markArchiveCandidates = async () => {
    let markedCount = 0;
    for (const group of args.archiveFeedGroups) {
      if (!group.primary.queue_hygiene?.archive_candidate) continue;
      const ok = await runLoggedControlTowerIntervention(
        "mark_archive_candidate",
        {
          label: "Marking archive candidate",
          reason: group.primary.queue_action_reason || "Operator batched archive-candidate cleanup from the feed.",
        },
        group.primary.mission_id
      );
      if (ok) {
        args.rememberDismissedMission(group.primary.mission_id, "archive");
        markedCount += 1;
      }
    }
    args.setShowArchiveCandidates(true);
    if (markedCount) {
      args.setUiNotice({
        tone: "good",
        title: `${markedCount} archive candidate${markedCount === 1 ? "" : "s"} marked`,
        detail: "Marked missions left the main feed and stay retrievable in archive candidates.",
      });
    }
  };

  const parkBlockedMissions = async () => {
    let parkedCount = 0;
    for (const expedition of args.blockedQueueItems) {
      await setMissionParking("parked", expedition.mission_id);
      args.rememberDismissedMission(expedition.mission_id, "parked");
      parkedCount += 1;
    }
    args.setShowParkedMissions(true);
    if (parkedCount) {
      args.setUiNotice({
        tone: "good",
        title: `${parkedCount} blocked mission${parkedCount === 1 ? "" : "s"} parked`,
        detail: "Parked missions left the main feed and stay retrievable below.",
      });
    }
  };

  const answerBlocker = () => {
    args.missionChatComposerRef.current?.focus();
    args.setUiNotice({
      tone: "info",
      title: "Answer blocker in mission chat",
      detail: args.missionSummaryQuestion || args.missionSummaryNextAnswer || "Use the mission chat composer below to send the missing detail.",
    });
  };

  const runControlTowerAction = async (action: string) => {
    const normalized = action.trim().toLowerCase();
    if (normalized === "resume mission") return void (await runLoggedControlTowerIntervention("resume_mission", { label: "Resuming mission", reason: "operator explicitly resumed the parked mission from control tower" }));
    if (normalized === "park mission") return void (await setMissionParking("parked"));
    if (normalized === "retry bounded action") return void (await runLoggedControlTowerIntervention("retry_bounded_action", { label: "Requesting bounded retry", reason: args.controlTowerSummary?.operator_attention_reason || args.controlTowerSummary?.last_retry_reason || args.controlTowerSummary?.last_blocked_reason || "Operator requested one bounded retry from the control tower." }));
    if (normalized === "refresh assumptions") return void (await runLoggedControlTowerIntervention("refresh_assumptions", { label: "Refreshing assumptions" }));
    if (normalized === "sync helper returns") return void (await runLoggedControlTowerIntervention("sync_helper_returns", { label: "Syncing helper returns" }));
    if (normalized === "clear stale pending handoff") return void (await runLoggedControlTowerIntervention("clear_stale_pending_handoff", { label: "Clearing stale handoff" }));
    if (normalized === "mark archive candidate") return void (await runLoggedControlTowerIntervention("mark_archive_candidate", { label: "Marking archive candidate", reason: args.selectedQueueHygiene?.recommendation_reason || "Operator explicitly marked this mission as an archive-review candidate." }));
    if (normalized === "answer blocker") answerBlocker();
  };

  const commitUnifiedIntent = async (mode?: "chat" | "input" | "create", missionIdOverride?: string | null) => {
    const text = args.unifiedIntentText.trim();
    if (!text) {
      args.setUiNotice({ tone: "watch", title: "No intent to confirm", detail: "Add intent in the top field before running an explicit action." });
      return;
    }
    const targetMissionId = missionIdOverride ?? args.composerEligibleMissionId ?? null;
    const hasExistingTarget = !!targetMissionId && args.activeTranslationPreview?.target_type !== "new_mission";
    const safeAction = (args.activeTranslationPreview?.recommended_safe_action || "").toLowerCase();
    const resolvedMode = mode || (!hasExistingTarget ? "create" : /chat|answer|reply/.test(safeAction) ? "chat" : "input");

    if (resolvedMode === "create") return void (await createMission(text));
    if (resolvedMode === "chat") {
      await sendMissionChat(text, undefined, targetMissionId);
      args.clearUnifiedIntentDraft(args.selectedMissionId || "__new__");
      return;
    }
    if (targetMissionId) args.setMissionInputDrafts((prev) => ({ ...prev, [targetMissionId]: text }));
    await sendMissionInput(text, targetMissionId || undefined);
    args.clearUnifiedIntentDraft(args.selectedMissionId || "__new__");
  };

  const runDominantAction = async () => {
    if (args.dominantAction.action === "clean_queue") {
      args.setTriageMode(true);
      args.setShowArchiveCandidates(true);
      args.setShowParkedMissions(true);
      args.setShowDuplicateMissions(true);
      await collapseDuplicateGroups();
      await markArchiveCandidates();
      await parkBlockedMissions();
      args.setUiNotice({
        tone: "good",
        title: "Queue cleaned",
        detail: "Duplicates collapsed, blocked missions parked, and archive candidates marked without deleting anything.",
      });
      return;
    }
    if (args.dominantAction.action === "resume") return void (await setMissionParking("active"));
    if (args.dominantAction.action === "resolve_blocker") {
      if (args.blockerType === "JUNK") {
        await runLoggedControlTowerIntervention("mark_archive_candidate", {
          label: "Ignoring junk blocker",
          reason: "operator classified the blocker as junk during mission resolution",
        });
        return;
      }
      if (args.blockerType === "SYSTEM") return void (await runReturnToBaseOption("retry"));
      if (args.unifiedIntentText.trim()) {
        await sendMissionChat(args.unifiedIntentText, "Resolve blocker");
        args.clearUnifiedIntentDraft(args.selectedMissionId);
        return;
      }
      answerBlocker();
      return;
    }
    if (args.dominantAction.action === "review") return void openReviewPreview(args.latestDraftPreviewPath);
    await commitUnifiedIntent(args.dominantAction.action === "start" ? "create" : undefined);
  };

  const submitMissionComposer = async () => {
    const lower = args.unifiedIntentText.trim().toLowerCase();
    const wantsQueueCleanup =
      !!lower &&
      /(clean|clear|fix|tidy|sort|collapse|dedupe|de-dupe|archive|park).*(queue|feed|missions|duplicates)|queue cleanup|clean the queue/i.test(lower);
    const wantsNewMission =
      (!args.selectedMissionId && !!args.unifiedIntentText.trim()) ||
      /(new mission|start (a )?mission|create (a )?mission|fresh mission|separate mission)/i.test(lower);

    if (wantsQueueCleanup) {
      await collapseDuplicateGroups();
      await markArchiveCandidates();
      await parkBlockedMissions();
      args.setTriageMode(true);
      args.setShowArchiveCandidates(true);
      args.setShowParkedMissions(true);
      args.setShowDuplicateMissions(true);
      args.setUiNotice({
        tone: "good",
        title: "Queue cleaned",
        detail: "Duplicates collapsed, blocked missions parked, and archive candidates marked without deleting anything.",
      });
      return;
    }

    if (wantsNewMission || (!args.selectedMissionId && args.unifiedIntentText.trim())) {
      await commitUnifiedIntent("create");
      return;
    }

    await runDominantAction();
  };

  const runReturnToBaseOption = async (optionKey: "retry" | "narrow" | "alternate", autoTriggered = false) => {
    if (optionKey === "retry") {
      await runLoggedControlTowerIntervention("retry_bounded_action", {
        label: autoTriggered ? "Auto retrying safe assumptions" : "Retrying safe assumptions",
        reason: autoTriggered ? "return-to-base default option 1 applied after visible delay" : "operator selected retry with safe assumptions from return-to-base",
      });
      return;
    }
    if (optionKey === "narrow") return void (await sendMissionChat("Narrow scope and continue with a safe partial result.", "Narrow scope / partial result"));
    await sendMissionChat("Try an alternate safe approach and continue.", "Alternate approach");
  };

  return {
    refreshAssumptions,
    reviewAssumption,
    syncRunnerReturns,
    openReviewPreview,
    createMission,
    sendMissionInput,
    translateMissionPrompt,
    sendMissionChat,
    runMissionQuickReply,
    setMissionParking,
    runLoggedControlTowerIntervention,
    dismissMissionGroup,
    collapseDuplicateGroups,
    markArchiveCandidates,
    parkBlockedMissions,
    runControlTowerAction,
    commitUnifiedIntent,
    submitMissionComposer,
    runReturnToBaseOption,
    runDominantAction,
    answerBlocker,
  };
}
