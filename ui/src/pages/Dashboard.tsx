import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useRef } from "react";
import {
  Activity,
  Database,
  RefreshCw,
  CircleDot,
  AlertTriangle,
  CheckCircle2,
  FileText,
  ClipboardList,
} from "lucide-react";
import {
  blockerTypeLabel,
  compactIntentLabel,
  compactLabel,
  deriveAttentionItems,
  deriveExpeditionStatusTone,
  deriveFeedBuckets,
  deriveGateOpen,
  derivePrimaryAction,
  deriveQueueCounts,
  dismissBucketForGroup,
  dismissLabelForBucket,
  getRecordObject,
  getRecordString,
  groupExpeditions,
  isMissionParked,
  missionConfidenceLabel,
  missionFeedState,
  missionFeedSummary,
  missionStateGaugeLabel,
  queuePressureLabel,
} from "./dashboardSelectors";
import { useDashboardData } from "./useDashboardData";
import { useMissionActions } from "./useMissionActions";

type EventStatus = "created" | "promotable" | "success" | "error" | "skipped";

type TopologyEvent = {
  timestamp: string;
  event_type: string;
  record_name: string;
  status: EventStatus | string;
  detail?: string;
  machine?: string;
};

type HonchoSession = {
  id: string;
  is_active?: boolean;
  metadata?: {
    agent_id?: string;
    workspace?: string;
    created_by?: string;
  };
  created_at?: string;
};

type HonchoPeer = {
  id: string;
  metadata?: {
    created_by?: string;
  };
};

type ReturnAllState = {
  ok: boolean;
  enabled: boolean;
  issued_by: string;
  issued_at: string;
  reason: string;
  allow_custodial_bypass: boolean;
};

type NannySignal = {
  id: string;
  level: "signal" | "issue" | string;
  title: string;
  cause: string;
  action_label: string;
  action_kind: string;
  severity?: "watch" | "bad" | string;
};

type NannyLearningSummary = {
  stored_path?: string;
  updated_at?: string;
  counts?: Record<string, number>;
  weak_question_count?: number;
};

type NannyWarning = string | { agent_id?: string; reason?: string };

type NannyState = {
  ok: boolean;
  temperature: string;
  burst_score: number;
  error_score: number;
  active_agent_warnings: NannyWarning[];
  recommended_actions: string[];
  global_cooldown_seconds: number;
  system_signals?: NannySignal[];
  signal_count?: number;
  learning_summary?: NannyLearningSummary;
  derived_counts?: Record<string, number>;
};

type DispatchCounts = {
  pending: number;
  approved: number;
  deferred: number;
  rejected: number;
  total: number;
};

type SupportHelperItem = {
  lane: "orchestration" | "retrieval";
  helper_id: string;
  helper_type: string;
  mandate_id: string;
  task_scope: string;
  status: string;
  created_at?: string;
  expires_at?: string;
  source_file?: string;
};

type SupportHelperActivity = {
  available: boolean;
  total: number;
  lane_counts: Record<string, number>;
  status_counts: Record<string, number>;
  items: SupportHelperItem[];
  source_dirs: Record<string, string>;
};

type MirrorDoorFailure = {
  category: string;
  case_id: string;
  expected: string;
  actual: string;
  reason: string;
  attack_surface: string;
  source_file: string;
};

type MirrorDoorTestStatus = {
  available: boolean;
  script_path: string;
  fixture_root: string;
  fixture_categories: string[];
  fixture_files: number;
  total?: number;
  correctly_blocked?: number;
  validly_accepted?: number;
  unexpected_accept?: number;
  unexpected_error?: number;
  recent_failures?: MirrorDoorFailure[];
  generated_at?: string;
  error?: string;
};

type Helper2bRuntimeStatus = {
  available: boolean;
  configured: boolean;
  enabled: boolean;
  role_id: string;
  execution_backend?: string;
  provider_requirement?: string;
  default_model_key?: string;
  fallback_model_key?: string;
  provider?: string;
  model?: string;
  mapped_helpers?: string[];
  role_description?: string;
  liveness?: string;
  notes?: string[];
  authority_boundary?: {
    derived_outputs_only?: boolean;
    returns_must_remain_structured?: boolean;
  };
  error?: string;
};

type StripTone = "good" | "watch" | "off";

type StorageAreaSummary = {
  name: string;
  path: string;
  available: boolean;
  file_count: number;
  json_file_count: number;
  total_bytes: number;
  total_bytes_label: string;
  oldest_modified_at: string;
  newest_modified_at: string;
  newest_age_minutes?: number | null;
  largest_file?: {
    name: string;
    bytes: number;
    bytes_label: string;
  } | null;
  pressure_score: number;
  pressure_label: string;
  notes: string[];
};

type StorageFootprint = {
  group_names: string[];
  total_bytes: number;
  total_bytes_label: string;
  total_files: number;
  groups: StorageAreaSummary[];
};

type CollectiveDoorFootprint = {
  path: string;
  total_files: number;
  total_bytes: number;
  total_bytes_label: string;
  admitted_count: number;
  admitted_bytes: number;
  admitted_bytes_label: string;
  blocked_count: number;
  blocked_bytes: number;
  blocked_bytes_label: string;
  malformed_count: number;
  legacy_count: number;
  admitted_ratio: number;
  door_reasons: Record<string, number>;
};

type StorageOverview = {
  available: boolean;
  generated_at?: string;
  areas: StorageAreaSummary[];
  hotspots: StorageAreaSummary[];
  collective_door: CollectiveDoorFootprint;
  footprints: {
    active: StorageFootprint;
    archive: StorageFootprint;
    compaction: StorageFootprint;
    all_observed_bytes: string;
  };
  compactor_last_run?: CompactorLastRunSummary | Record<string, unknown>;
};

type CompactorLastRunSummary = {
  ok?: boolean;
  timestamp?: string;
  groups_scanned?: number;
  groups_compacted?: number;
  records_compacted?: number;
  records_skipped?: number;
};

type HermesRun = {
  ok?: boolean;
  source_path?: string;
  captured_at?: string;
  run_id?: string;
  mode?: string;
  status?: string;
  summary?: string;
  evidence_refs?: string[];
  recommended_action?: string;
  petition_kind?: string | null;
  confidence?: number;
  classification?: {
    kind?: string;
    title?: string;
    severity?: string;
    boundedness?: string;
    affected_system?: string;
  } | null;
  error?: string;
};

type ReviewPreview = {
  draft_path: string;
  draft: {
    petition_id: string;
    mode: string;
    petition_kind: string;
    petition_type: string;
    requested_action: string;
    confidence: number;
    source_run_id: string;
    summary: string;
    evidence_refs: string[];
  };
  submission_allowed: boolean;
  submission_gate: {
    status: string;
    reason: string;
  };
  dispatch_preview?: Record<string, unknown>;
  dispatch_path: string;
  dispatch_petition_id: string;
};

type DraftRecord = {
  ok?: boolean;
  source_path?: string;
  draft?: ReviewPreview["draft"];
  review_preview?: ReviewPreview;
  error?: string;
};

type RunnerReturn = {
  mission_id: string;
  runner_id: string;
  instance_id: string;
  created_at: string;
  kind: string;
  summary: string;
  findings: string[];
  confidence: number;
  open_questions: string[];
  recommended_next_step: string;
  lane: string;
  derived_only: boolean;
  helper_type?: string;
  source_ref?: string;
  path?: string;
};

type ExpeditionStatusBadge = "waiting_for_user" | "researching" | "ready_for_review" | "idle";

type ExpeditionSummary = {
  mission_id: string;
  objective: string;
  objective_normalized?: string;
  duplicate_group_key?: string;
  duplicate_rank?: number;
  duplicate_count?: number;
  is_duplicate_candidate?: boolean;
  is_group_primary?: boolean;
  duplicate_of_mission_id?: string;
  current_state: string;
  status_badge: ExpeditionStatusBadge;
  latest_run_id: string;
  last_updated: string;
  created_at: string;
  artifact_count: number;
  input_count: number;
  summary: string;
  manifest_status: string;
  operator_posture?: string;
  operator_posture_reason?: string;
  triage_bucket?: string;
  mission_summary?: ExpeditionDetail["mission_summary"];
  parking_status?: ExpeditionDetail["parking_status"];
  control_tower_summary?: ControlTowerSummary;
  queue_hygiene?: {
    last_activity_at?: string;
    last_activity_age_days?: number | null;
    parked_age_days?: number | null;
    duplicate_candidate?: boolean;
    stale_candidate?: boolean;
    blocked_candidate?: boolean;
    parked_candidate?: boolean;
    review_ready?: boolean;
    archive_candidate?: boolean;
    superseded_by_newer_similar?: boolean;
    junk_pattern?: boolean;
    signals?: string[];
    recommended_action?: string;
    recommendation_reason?: string;
  };
  recommended_queue_action?: string;
  queue_action_reason?: string;
  path: string;
};

type DismissBucket = "archive" | "parked" | "duplicates";

type MissionAttentionItem = {
  key: string;
  mission_id?: string;
  title: string;
  detail: string;
  badge: string;
  tone: StripTone;
};

type CalibrationAxis = {
  key: string;
  label: string;
  value: number;
  hint: string;
};

type MissionInputRecord = {
  input_id: string;
  mission_id: string;
  source_type: string;
  status: string;
  content: string;
  created_at: string;
  path: string;
};

type WorkbenchFile = {
  path: string;
  folder: string;
  name: string;
  modified_at: string;
  bytes: number;
  bytes_label: string;
};

type WorkbenchFolder = {
  name: string;
  path: string;
  available: boolean;
  file_count: number;
  newest_modified_at: string;
};

type AssumptionConfirmation = {
  operator_status: string;
  operator_note: string;
  operator_updated_at: string;
};

type AssumptionEntry = {
  assumption_id: string;
  mission_id: string;
  created_at: string;
  updated_at: string;
  text: string;
  reason: string;
  confidence: number;
  basis_refs: string[];
  invalidation_triggers: string[];
  status: string;
  confirmation: AssumptionConfirmation;
  derived_only: boolean;
};

type AssumptionChange = {
  assumption_id: string;
  text: string;
  status: string;
  updated_at: string;
  operator_status: string;
};

type ControlTowerActivity = {
  role?: string;
  kind?: string;
  summary?: string;
  created_at?: string;
  source_ref?: string;
};

type ControlTowerHandoff = {
  target_role?: string;
  allowed_action?: string;
  status?: string;
  reason?: string;
  updated_at?: string;
};

type ControlTowerTrigger = {
  trigger_kind?: string;
  status?: string;
  created_at?: string;
  reason?: string;
};

type ControlTowerIntervention = {
  intervention_id?: string;
  action?: string;
  status?: string;
  reason?: string;
  note?: string;
  blocked_reason?: string;
  created_at?: string;
  changed_paths?: string[];
};

type ControlTowerSummary = {
  autonomy_state?: string;
  last_trigger?: ControlTowerTrigger | null;
  last_trigger_outcome?: string;
  retry_budget?: number;
  retry_used?: number;
  last_retry_reason?: string;
  last_blocked_reason?: string;
  active_role_handoff?: ControlTowerHandoff | null;
  latest_role_activity?: ControlTowerActivity | null;
  operator_attention_reason?: string;
  recent_operator_interventions?: ControlTowerIntervention[];
  safe_operator_actions?: string[];
};

type WorkbenchSummary = {
  root: string;
  folders: WorkbenchFolder[];
  files: WorkbenchFile[];
};

type PromptTranslation = {
  translation_id: string;
  created_at: string;
  source_text: string;
  target_type: "existing_mission" | "new_mission" | "unknown" | string;
  target_mission_id?: string | null;
  recommended_role: string;
  recommended_mode: string;
  scope: string;
  sufficiency: {
    can_proceed: boolean;
    missing_requirements: string[];
  };
  recommended_safe_action: string;
  requires_operator_confirmation: boolean;
  translated_instruction: string;
  notes?: string[];
  derived_only?: boolean;
  path?: string;
};

type ExpeditionDetail = {
  mission_id: string;
  objective: string;
  current_state: string;
  status_badge: ExpeditionStatusBadge;
  latest_run_id: string;
  last_updated: string;
  created_at: string;
  mission_brief: Record<string, unknown>;
  state: Record<string, unknown>;
  manifest?: Record<string, unknown> | null;
  artifact_index: {
    mission_id: string;
    items: {
      kind: string;
      path: string;
      created_at: string;
    }[];
  };
  artifact_refs: Record<string, unknown>[];
  latest_hermes_run?: HermesRun | Record<string, unknown> | null;
  latest_draft?: DraftRecord | Record<string, unknown> | null;
  latest_clarification_packet?: Record<string, unknown> | null;
  latest_runner_return?: RunnerReturn | Record<string, unknown> | null;
  latest_agent_run?: Record<string, unknown> | null;
  runner_return_count?: number;
  agent_run_count?: number;
  assumptions?: AssumptionEntry[];
  active_assumption_count?: number;
  assumption_count?: number;
  assumptions_last_updated?: string;
  assumption_review_needed?: boolean;
  latest_assumption_changes?: AssumptionChange[];
  parking_status?: {
    mission_id: string;
    status: "active" | "parked";
    reason?: string;
    parked_at?: string;
    parked_by?: string;
    resume_hint?: string;
    updated_at?: string;
  };
  autonomy_status?: {
    mission_id: string;
    status: string;
    autonomy_status: string;
    last_trigger_outcome: string;
    retry_budget_summary: string;
    last_blocked_reason: string;
    kill_switch_active?: boolean;
    parked?: boolean;
    pending_action?: string;
    pending_status?: string;
  };
  control_tower_summary?: ControlTowerSummary;
  operator_posture?: string;
  operator_posture_reason?: string;
  assumptions_active?: string[];
  blocking_questions?: string[];
  operator_options?: { label: string; value: string; kind?: string }[];
  triage_bucket?: string;
  queue_hygiene?: ExpeditionSummary["queue_hygiene"];
  mission_summary?: {
    mission_id: string;
    status: string;
    life_cycle_state?: string;
    operating_status?: string;
    can_continue_without_input?: boolean;
    blocked_reason?: string;
    summary: string;
    latest_summary?: string;
    what_we_believe: string[];
    confirmed_facts?: string[];
    active_assumptions?: string[];
    assumptions_active?: string[];
    open_questions?: string[];
    deferred_questions?: string[];
    blocking_questions?: string[];
    confidence: number;
    confidence_label: "low" | "moderate" | "high";
    confidence_reduction?: number;
    what_we_need_from_you: string[];
    clarification_reason?: string;
    next_question?: string;
    next_best_operator_answer?: string;
    quick_replies?: { label: string; value: string; kind?: string }[];
    operator_posture?: string;
    operator_posture_reason?: string;
    operator_options?: { label: string; value: string; kind?: string }[];
    triage_bucket?: string;
    recommended_next_step: string;
    last_operator_reply_at?: string;
    crew_status?: string;
    expedition_activity?: string;
    parked_at?: string;
    wake_hint?: string;
  };
  latest_prompt_translation?: PromptTranslation | null;
  prompt_translation_count?: number;
  prompt_translations?: PromptTranslation[];
  mission_inputs: MissionInputRecord[];
  mission_chat: MissionChatMessage[];
  workbench: WorkbenchSummary;
  artifact_count: number;
  input_count: number;
  chat_count: number;
  agent_runs?: Record<string, unknown>[];
};

type MissionChatMessage = {
  message_id: string;
  mission_id: string;
  sender: "user" | "assistant";
  role: string;
  message: string;
  tone: "good" | "watch" | "info" | "bad";
  created_at: string;
  kind: string;
};

type StatusResponse = {
  ok: boolean;
  workspace_id: string;
  honcho_sessions_total: number;
  honcho_peers_total: number;
  honcho_sessions: HonchoSession[];
  honcho_peers: HonchoPeer[];
  events_recent: TopologyEvent[];
  return_all: ReturnAllState;
  nanny: NannyState;
  dispatch_counts: DispatchCounts;
  support_helper_activity?: SupportHelperActivity;
  helper_2b_runtime?: Helper2bRuntimeStatus;
  mirror_door_test: MirrorDoorTestStatus;
  storage_overview?: StorageOverview;
};

type NoticeTone = "good" | "watch" | "bad" | "info";

type UiNotice = {
  tone: NoticeTone;
  title: string;
  detail: string;
};

const API_BASE = (import.meta.env.VITE_SPINETOP_API_BASE as string | undefined)?.trim() || "/api";

const fallbackData: StatusResponse = {
  ok: true,
  workspace_id: "shared-coordination",
  honcho_sessions_total: 6,
  honcho_peers_total: 1,
  honcho_sessions: [
    {
      id: "hermes-desktop-session-20260402-212109",
      is_active: true,
      metadata: { agent_id: "hermes-desktop", workspace: "spinetop" },
      created_at: "2026-04-02T21:46:13",
    },
  ],
  honcho_peers: [
    {
      id: "peer-hermes-desktop",
      metadata: { created_by: "honcho_bridge" },
    },
  ],
  events_recent: [
    {
      timestamp: "2026-04-02T21:21:07",
      event_type: "hermes_write",
      record_name: "hermes_20260402_212107.json",
      status: "created",
      detail: "promotion_candidate=true",
      machine: "Spinetop",
    },
    {
      timestamp: "2026-04-02T21:21:10",
      event_type: "watcher_scan",
      record_name: "hermes_20260402_212107.json",
      status: "promotable",
      detail: "starting promotion flow",
      machine: "Spinetop",
    },
    {
      timestamp: "2026-04-02T21:21:11",
      event_type: "promote",
      record_name: "hermes_20260402_212107.json",
      status: "success",
      detail: "Promoted to memory/promotion",
      machine: "Spinetop",
    },
    {
      timestamp: "2026-04-02T21:21:12",
      event_type: "approve",
      record_name: "hermes_20260402_212107.json",
      status: "success",
      detail: "Approved to memory/collective",
      machine: "Spinetop",
    },
    {
      timestamp: "2026-04-02T21:46:13",
      event_type: "honcho_bridge",
      record_name: "hermes_20260402_212107.json",
      status: "success",
      detail: "mirrored to honcho",
      machine: "Spinetop",
    },
  ],
  return_all: {
    ok: true,
    enabled: false,
    issued_by: "operator",
    issued_at: "",
    reason: "",
    allow_custodial_bypass: false,
  },
  nanny: {
    ok: true,
    temperature: "cool",
    burst_score: 0,
    error_score: 0,
    active_agent_warnings: [],
    recommended_actions: [],
    global_cooldown_seconds: 0,
    system_signals: [],
    signal_count: 0,
    learning_summary: {
      stored_path: "workbench/system/operator_learning/nanny_pattern_memory.json",
      updated_at: "",
      counts: {},
      weak_question_count: 0,
    },
    derived_counts: {},
  },
  dispatch_counts: {
    pending: 0,
    approved: 0,
    deferred: 0,
    rejected: 0,
    total: 0,
  },
  support_helper_activity: {
    available: true,
    total: 2,
    lane_counts: {
      orchestration: 1,
      retrieval: 1,
    },
    status_counts: {
      complete: 2,
    },
    source_dirs: {
      orchestration: "logs/support/orchestration",
      retrieval: "logs/support/retrieval",
    },
    items: [
      {
        lane: "orchestration",
        helper_id: "runner_helper_2b_20260404T062124067861Z_e4b094d9",
        helper_type: "runner_helper_2b",
        mandate_id: "stress_mandate_001",
        task_scope: "stress-test-runner_helper_2b",
        status: "complete",
        created_at: "2026-04-04T06:21:24Z",
        expires_at: "2026-04-04T06:31:24Z",
        source_file: "logs/support/orchestration/instances/runner_helper_2b_20260404T062124067861Z_e4b094d9.json",
      },
      {
        lane: "retrieval",
        helper_id: "retrieval_helper_2b_20260404T061154418152Z_8d4f5af9",
        helper_type: "retrieval_helper_2b",
        mandate_id: "mandate_demo_001",
        task_scope: "retrieve references for the retrieval helper contract",
        status: "complete",
        created_at: "2026-04-04T06:11:54Z",
        expires_at: "2026-04-04T06:21:54Z",
        source_file: "logs/support/retrieval/instances/retrieval_helper_2b_20260404T061154418152Z_8d4f5af9.json",
      },
    ],
  },
  helper_2b_runtime: {
    available: true,
    configured: true,
    enabled: false,
    role_id: "spinetop_expeditioner",
    execution_backend: "scripted",
    provider_requirement: "local_only",
    default_model_key: "",
    fallback_model_key: "",
    provider: "",
    model: "",
    mapped_helpers: ["retrieval_helper_2b", "runner_helper_2b"],
    role_description: "Spinetop-Expeditioner is the mission-local task worker for first-pass derived outputs.",
    liveness: "disabled_safe_inactive",
    notes: [
      "Mission work stays bounded to mission-local and workbench lanes.",
      "Spinetop-Expeditioner is not Sentinel, helper_2b, or Mirror.",
      "Spinetop-Expeditioner does not approve, create truth, or bypass governance.",
      "If runtime is inactive, the seam stays disabled-safe and returns structured receipts only.",
    ],
    authority_boundary: {
      derived_outputs_only: true,
      returns_must_remain_structured: true,
    },
  },
  mirror_door_test: {
    available: false,
    script_path: "scripts/test_mirror_door_contracts.py",
    fixture_root: "tests/mirror_door_contracts",
    fixture_categories: [],
    fixture_files: 0,
    total: 0,
    correctly_blocked: 0,
    validly_accepted: 0,
    unexpected_accept: 0,
    unexpected_error: 0,
    recent_failures: [],
  },
  storage_overview: {
    available: false,
    generated_at: "",
    areas: [],
    hotspots: [],
    collective_door: {
      path: "memory/collective",
      total_files: 0,
      total_bytes: 0,
      total_bytes_label: "0 B",
      admitted_count: 0,
      admitted_bytes: 0,
      admitted_bytes_label: "0 B",
      blocked_count: 0,
      blocked_bytes: 0,
      blocked_bytes_label: "0 B",
      malformed_count: 0,
      legacy_count: 0,
      admitted_ratio: 0,
      door_reasons: {},
    },
    footprints: {
      active: {
        group_names: [],
        total_bytes: 0,
        total_bytes_label: "0 B",
        total_files: 0,
        groups: [],
      },
      archive: {
        group_names: [],
        total_bytes: 0,
        total_bytes_label: "0 B",
        total_files: 0,
        groups: [],
      },
      compaction: {
        group_names: [],
        total_bytes: 0,
        total_bytes_label: "0 B",
        total_files: 0,
        groups: [],
      },
      all_observed_bytes: "0 B",
    },
    compactor_last_run: {},
  },
};

const fallbackExpeditions: ExpeditionSummary[] = [];

const gateLabels = ["Inbox", "Promotion", "Collective", "Honcho"];
const gateX = [8, 33, 58, 83];

const styles = {
  page: {
    minHeight: "100vh",
    background: "#020617",
    color: "#e2e8f0",
    padding: "32px 24px",
  } as const,
  container: {
    maxWidth: 1200,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column" as const,
    gap: 24,
  } as const,
  pillRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: 8,
    alignItems: "center",
  } as const,
  pill: {
    borderRadius: 999,
    padding: "6px 12px",
    fontSize: 12,
  } as const,
  badgePrimary: {
    background: "#7c3aed",
    color: "#fff",
    fontWeight: 600,
  } as const,
  badgeOutline: {
    border: "1px solid rgba(192,132,252,0.4)",
    color: "#e9d5ff",
    background: "rgba(88,28,135,0.4)",
  } as const,
  badgeWarn: {
    border: "1px solid rgba(251,191,36,0.4)",
    color: "#fde68a",
    background: "rgba(120,53,15,0.4)",
  } as const,
  headerRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: 16,
    justifyContent: "space-between",
    alignItems: "flex-end",
  } as const,
  headline: {
    fontSize: 32,
    fontWeight: 600,
    color: "#f5d0fe",
    margin: 0,
  } as const,
  subtext: {
    marginTop: 8,
    color: "#cbd5f5",
    maxWidth: 720,
  } as const,
  refreshRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap" as const,
  } as const,
  refreshButton: {
    borderRadius: 12,
    background: "#7c3aed",
    color: "#fff",
    border: "none",
    padding: "8px 16px",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
  } as const,
  alert: {
    borderRadius: 16,
    border: "1px solid rgba(251,191,36,0.4)",
    background: "rgba(120,53,15,0.2)",
    padding: "10px 14px",
    fontSize: 12,
    color: "#fde68a",
  } as const,
  metrics: {
    display: "grid",
    gap: 16,
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  } as const,
  statusStrip: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  } as const,
  statusCard: {
    borderRadius: 18,
    border: "1px solid rgba(192,132,252,0.18)",
    background: "rgba(2,6,23,0.75)",
    padding: 14,
  } as const,
  statusLabel: {
    fontSize: 11,
    letterSpacing: "0.08em",
    textTransform: "uppercase" as const,
    color: "#94a3b8",
  } as const,
  statusValue: {
    marginTop: 8,
    fontSize: 22,
    fontWeight: 600,
    color: "#f5d0fe",
  } as const,
  statusDetail: {
    marginTop: 6,
    fontSize: 12,
    lineHeight: 1.4,
    color: "#cbd5f5",
  } as const,
  metricCard: {
    borderRadius: 16,
    border: "1px solid rgba(192,132,252,0.2)",
    background: "rgba(15,23,42,0.9)",
    padding: 16,
  } as const,
  panel: {
    borderRadius: 24,
    border: "1px solid rgba(192,132,252,0.2)",
    background: "rgba(15,23,42,0.9)",
    padding: 20,
  } as const,
  composerCard: {
    position: "sticky" as const,
    top: 76,
    zIndex: 20,
    borderRadius: 24,
    border: "1px solid rgba(251,191,36,0.28)",
    background: "linear-gradient(180deg, rgba(30,41,59,0.98), rgba(15,23,42,0.96))",
    boxShadow: "0 20px 48px rgba(2, 6, 23, 0.32)",
    padding: 20,
  } as const,
  composerTextarea: {
    width: "100%",
    minHeight: 118,
    maxHeight: 280,
    borderRadius: 18,
    border: "1px solid rgba(251,191,36,0.2)",
    background: "rgba(2,6,23,0.72)",
    color: "#f8fafc",
    padding: "14px 16px",
    fontSize: 16,
    lineHeight: 1.55,
    outline: "none",
    resize: "vertical" as const,
    boxSizing: "border-box" as const,
    fontFamily: "inherit",
  } as const,
  composerResultGood: {
    color: "#bbf7d0",
  } as const,
  composerResultInfo: {
    color: "#e2e8f0",
  } as const,
  composerResultWarn: {
    color: "#fde68a",
  } as const,
  composerResultBad: {
    color: "#fecaca",
  } as const,
  sectionGrid: {
    display: "grid",
    gap: 24,
    gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
  } as const,
  sectionTitleRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 16,
  } as const,
  sectionTitle: {
    fontSize: 20,
    fontWeight: 600,
    color: "#f5d0fe",
    margin: 0,
  } as const,
  sectionSubtitle: {
    marginTop: 4,
    fontSize: 12,
    color: "#94a3b8",
    maxWidth: 640,
  } as const,
  stack: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 12,
  } as const,
  recordCard: {
    borderRadius: 18,
    border: "1px solid rgba(192,132,252,0.2)",
    background: "rgba(2,6,23,0.55)",
    padding: 16,
  } as const,
  recordMetaRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: 8,
    alignItems: "center",
    justifyContent: "space-between",
  } as const,
  badge: {
    borderRadius: 999,
    border: "1px solid rgba(148,163,184,0.3)",
    background: "rgba(15,23,42,0.9)",
    padding: "4px 10px",
    fontSize: 11,
    color: "#cbd5f5",
  } as const,
  badgeGood: {
    border: "1px solid rgba(52,211,153,0.35)",
    background: "rgba(6,78,59,0.35)",
    color: "#bbf7d0",
  } as const,
  badgeBad: {
    border: "1px solid rgba(251,113,133,0.35)",
    background: "rgba(127,29,29,0.35)",
    color: "#fecdd3",
  } as const,
  mono: {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  } as const,
  subtleText: {
    fontSize: 12,
    color: "#94a3b8",
  } as const,
  previewBox: {
    marginTop: 12,
    borderRadius: 14,
    border: "1px solid rgba(148,163,184,0.18)",
    background: "rgba(15,23,42,0.75)",
    padding: 12,
  } as const,
  fieldInput: {
    width: "100%",
    borderRadius: 14,
    border: "1px solid rgba(192,132,252,0.24)",
    background: "rgba(2,6,23,0.65)",
    color: "#e2e8f0",
    padding: "10px 12px",
    fontSize: 14,
    outline: "none",
    boxSizing: "border-box" as const,
  } as const,
  fieldTextarea: {
    width: "100%",
    minHeight: 110,
    borderRadius: 14,
    border: "1px solid rgba(192,132,252,0.24)",
    background: "rgba(2,6,23,0.65)",
    color: "#e2e8f0",
    padding: "12px",
    fontSize: 14,
    outline: "none",
    resize: "vertical" as const,
    boxSizing: "border-box" as const,
    fontFamily: "inherit",
  } as const,
  secondaryButton: {
    borderRadius: 12,
    border: "1px solid rgba(192,132,252,0.3)",
    background: "rgba(15,23,42,0.9)",
    color: "#e9d5ff",
    padding: "8px 14px",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  } as const,
  expeditionList: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 10,
    paddingRight: 2,
  } as const,
  feedCard: {
    borderRadius: 20,
    border: "1px solid rgba(192,132,252,0.18)",
    background: "linear-gradient(180deg, rgba(15,23,42,0.98), rgba(2,6,23,0.92))",
    padding: 16,
    overflow: "hidden" as const,
    touchAction: "pan-y",
  } as const,
  feedHeaderButton: {
    width: "100%",
    border: "none",
    background: "transparent",
    padding: 0,
    textAlign: "left" as const,
    cursor: "pointer",
    color: "inherit",
  } as const,
  feedMetaRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "flex-start",
  } as const,
  feedActionButton: {
    borderRadius: 12,
    border: "1px solid rgba(251,191,36,0.26)",
    background: "rgba(120,53,15,0.22)",
    color: "#fde68a",
    padding: "11px 16px",
    fontSize: 14,
    fontWeight: 800,
    cursor: "pointer",
  } as const,
  feedSecondaryActionRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap" as const,
    justifyContent: "flex-end",
  } as const,
  dismissButton: {
    borderRadius: 12,
    border: "1px solid rgba(248,113,113,0.14)",
    background: "rgba(30,41,59,0.48)",
    color: "#fca5a5",
    padding: "7px 10px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  } as const,
  trayToggle: {
    borderRadius: 999,
    border: "1px solid rgba(148,163,184,0.24)",
    background: "rgba(15,23,42,0.85)",
    color: "#cbd5f5",
    padding: "8px 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  } as const,
  tabRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: 8,
  } as const,
  tabButton: {
    borderRadius: 999,
    border: "1px solid rgba(148,163,184,0.3)",
    background: "rgba(15,23,42,0.8)",
    color: "#cbd5f5",
    padding: "6px 12px",
    fontSize: 12,
    cursor: "pointer",
  } as const,
  tabButtonActive: {
    border: "1px solid rgba(192,132,252,0.4)",
    background: "rgba(124,58,237,0.22)",
    color: "#fff",
  } as const,
  scrollArea: {
    maxHeight: 240,
    overflowY: "auto" as const,
    display: "flex",
    flexDirection: "column" as const,
    gap: 10,
  } as const,
  gridSplit: {
    display: "grid",
    gap: 24,
    gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 0.8fr)",
  } as const,
  portalArea: {
    position: "relative" as const,
    overflow: "hidden",
    borderRadius: 24,
    border: "1px solid rgba(192,132,252,0.2)",
    padding: 24,
    background: "radial-gradient(circle at top, #4c1d95 0%, #0f172a 40%, #020617 100%)",
  } as const,
};

function getPacketStage(events: TopologyEvent[], recordName: string): number {
  const packetEvents = events.filter((e) => e.record_name === recordName);
  if (packetEvents.some((e) => e.event_type === "honcho_bridge" && e.status === "success")) return 3;
  if (packetEvents.some((e) => e.event_type === "approve" && e.status === "success")) return 2;
  if (
    packetEvents.some((e) => e.event_type === "promote" && e.status === "success") ||
    packetEvents.some((e) => e.status === "promotable")
  ) {
    return 1;
  }
  return 0;
}

function groupPackets(events: TopologyEvent[]) {
  const seen = new Map<string, TopologyEvent[]>();
  for (const event of events) {
    if (!seen.has(event.record_name)) seen.set(event.record_name, []);
    seen.get(event.record_name)!.push(event);
  }
  return Array.from(seen.entries()).map(([recordName, packetEvents]) => ({
    recordName,
    events: packetEvents.sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
    stage: getPacketStage(events, recordName),
    failed: packetEvents.some((e) => e.status === "error" || e.status === "skipped"),
  }));
}

function metricCard(
  title: string,
  value: string | number,
  subtitle: string,
  Icon: React.ComponentType<{ className?: string }>
) {
  return (
    <div style={styles.metricCard}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>{title}</div>
          <div style={{ marginTop: 8, fontSize: 28, fontWeight: 600, color: "#f5d0fe" }}>{value}</div>
          <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>{subtitle}</div>
        </div>
        <div
          style={{
            borderRadius: 16,
            border: "1px solid rgba(192,132,252,0.2)",
            background: "rgba(192,132,252,0.1)",
            padding: 10,
            height: 36,
          }}
        >
          <Icon className="" />
        </div>
      </div>
    </div>
  );
}

function statusPill(status: string) {
  const stylesMap: Record<string, string> = {
    success: "#10b981",
    created: "#38bdf8",
    promotable: "#f59e0b",
    error: "#fb7185",
    skipped: "#94a3b8",
    partial: "#f59e0b",
  };
  return stylesMap[status] ?? "#94a3b8";
}

const statusStripToneStyles: Record<StripTone, React.CSSProperties> = {
  good: {
    border: "1px solid rgba(52,211,153,0.38)",
    background: "linear-gradient(180deg, rgba(6,78,59,0.32), rgba(2,6,23,0.78))",
    boxShadow: "inset 0 3px 0 rgba(52,211,153,0.65)",
  },
  watch: {
    border: "1px solid rgba(251,191,36,0.38)",
    background: "linear-gradient(180deg, rgba(120,53,15,0.32), rgba(2,6,23,0.78))",
    boxShadow: "inset 0 3px 0 rgba(251,191,36,0.65)",
  },
  off: {
    border: "1px solid rgba(148,163,184,0.24)",
    background: "linear-gradient(180deg, rgba(15,23,42,0.9), rgba(2,6,23,0.78))",
    boxShadow: "inset 0 3px 0 rgba(148,163,184,0.35)",
  },
};

function statusStripCard(title: string, value: string, detail: string, tone: StripTone = "off") {
  return (
    <div style={{ ...styles.statusCard, ...statusStripToneStyles[tone] }}>
      <div style={styles.statusLabel}>{title}</div>
      <div style={styles.statusValue}>{value}</div>
      <div style={styles.statusDetail}>{detail}</div>
    </div>
  );
}

function formatAgeMinutes(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "unknown";
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)} min ago`;
  const hours = value / 60;
  if (hours < 24) return `${hours.toFixed(hours < 10 ? 1 : 0)} h ago`;
  const days = hours / 24;
  return `${days.toFixed(days < 10 ? 1 : 0)} d ago`;
}

function getRecordNumber(record: unknown, key: string): number | null {
  if (!record || typeof record !== "object") return null;
  const value = (record as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatConfidence(value: number | null | undefined, fallback = "unknown"): string {
  if (value == null || !Number.isFinite(value)) return fallback;
  return value.toFixed(2);
}

void getRecordNumber;
void formatConfidence;

function toneForGauge(value: string): StripTone {
  if (["ACTIVE", "READY", "HIGH", "LIGHT"].includes(value)) return "good";
  if (["CAUTION", "GUARDED", "MEDIUM", "MODERATE", "PARKED", "IDLE"].includes(value)) return "watch";
  return "watch";
}

function assumptionStatusBadgeStyle(status: string): React.CSSProperties {
  if (status === "accepted") return { ...styles.badge, ...styles.badgeGood };
  if (status === "rejected" || status === "invalidated") return { ...styles.badge, ...styles.badgeBad };
  if (status === "resolved") return { ...styles.badge };
  return { ...styles.badge, ...styles.badgeWarn };
}

function assumptionOperatorBadgeStyle(operatorStatus: string): React.CSSProperties {
  if (operatorStatus === "accepted") return { ...styles.badge, ...styles.badgeGood };
  if (operatorStatus === "rejected") return { ...styles.badge, ...styles.badgeBad };
  return { ...styles.badge, ...styles.badgeWarn };
}

export default function Dashboard() {
  const [viewMode, setViewMode] = useState<"missions" | "diagnostics">("missions");
  const [newMissionObjective, setNewMissionObjective] = useState("");
  const [unifiedIntentDrafts, setUnifiedIntentDrafts] = useState<Record<string, string>>({});
  const [missionInputDrafts, setMissionInputDrafts] = useState<Record<string, string>>({});
  const [missionChatDrafts, setMissionChatDrafts] = useState<Record<string, string>>({});
  const [translatorDrafts, setTranslatorDrafts] = useState<Record<string, string>>({});
  const [translatorPreviewByMission, setTranslatorPreviewByMission] = useState<Record<string, PromptTranslation | null>>({});
  const [dismissedTranslationByMission, setDismissedTranslationByMission] = useState<Record<string, string | null>>({});
  const [dismissedMissionBuckets, setDismissedMissionBuckets] = useState<Record<string, DismissBucket>>({});
  const [showDuplicateMissions, setShowDuplicateMissions] = useState(false);
  const [showArchiveCandidates, setShowArchiveCandidates] = useState(false);
  const [showParkedMissions, setShowParkedMissions] = useState(true);
  const [expandedMissionIds, setExpandedMissionIds] = useState<Record<string, boolean>>({});
  const [triageMode, setTriageMode] = useState(false);
  const [workbenchFolder, setWorkbenchFolder] = useState("intake");
  const [selectedDraftPath, setSelectedDraftPath] = useState<string | null>(null);
  const [showAllAssumptions, setShowAllAssumptions] = useState(false);
  const [uiNotice, setUiNotice] = useState<UiNotice | null>(null);
  const [returnToBaseCountdown, setReturnToBaseCountdown] = useState<number | null>(null);
  const [missionSaving, setMissionSaving] = useState(false);
  const [translatorSaving, setTranslatorSaving] = useState(false);
  const [missionActionLabel, setMissionActionLabel] = useState("");
  const missionChatComposerRef = useRef<HTMLTextAreaElement | null>(null);
  const [calibrationAxes, setCalibrationAxes] = useState<CalibrationAxis[]>([
    { key: "exploration", label: "Exploration pressure", value: 72, hint: "how eagerly the mission explores" },
    { key: "boundedness", label: "Boundedness", value: 84, hint: "how tightly the mission follows the ask" },
    { key: "respect", label: "User respect", value: 93, hint: "how carefully the mission handles operator input" },
    { key: "clarity", label: "Clarity", value: 79, hint: "how cleanly the mission reports back" },
    { key: "governance", label: "Governance fidelity", value: 88, hint: "how strictly the mission honors the safe lanes" },
    { key: "uncertainty", label: "Uncertainty tolerance", value: 55, hint: "how boldly the mission handles fuzzy tasks" },
  ]);
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);
  const missionInputInFlightRef = useRef<string | null>(null);
  const missionChatInFlightRef = useRef<string | null>(null);
  const autoTranslatedDraftRef = useRef<Record<string, string>>({});
  const autoReturnToBaseKeyRef = useRef<string | null>(null);
  const {
    data,
    hermesRuns,
    petitionDrafts,
    expeditions,
    expeditionQueueSummary,
    selectedMissionId,
    setSelectedMissionId,
    selectedMission,
    setSelectedMission,
    missionDetailsById,
    loading,
    missionLoading,
    lastRefresh,
    errorText,
    setErrorText,
    load,
    loadMissionDetail,
  } = useDashboardData({
    apiBase: API_BASE,
    fallbackData,
    fallbackExpeditions,
    workbenchFolder,
    setWorkbenchFolder,
  });
  const unifiedDraftKey = selectedMissionId || "__new__";
  const unifiedIntentText = unifiedIntentDrafts[unifiedDraftKey] || "";
  const selectedMissionSummary = selectedMissionId ? expeditions.find((item) => item.mission_id === selectedMissionId) ?? null : null;
  const selectedMissionIsParked = isMissionParked(selectedMission) || isMissionParked(selectedMissionSummary);
  const composerEligibleMissionId =
    (selectedMissionId && selectedMissionSummary && missionFeedState(selectedMissionSummary) === "ACTIVE" ? selectedMissionId : null) ||
    expeditions.find((item) => missionFeedState(item) === "ACTIVE")?.mission_id ||
    null;
  const composerRetargetedFromParkedMission = !!selectedMissionId && selectedMissionIsParked && composerEligibleMissionId !== selectedMissionId;

  useEffect(() => {
    setShowAllAssumptions(false);
  }, [selectedMissionId]);

  useEffect(() => {
    setExpandedMissionIds((prev) => {
      const activeIds = new Set(expeditions.map((item) => item.mission_id));
      let changed = false;
      const next: Record<string, boolean> = {};
      for (const [missionId, expanded] of Object.entries(prev)) {
        if (expanded && activeIds.has(missionId)) {
          next[missionId] = true;
        } else if (expanded) {
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [expeditions]);

  useEffect(() => {
    if (!composerEligibleMissionId) return;
    const content = unifiedIntentText.trim();
    if (!content) {
      autoTranslatedDraftRef.current[composerEligibleMissionId] = "";
      return;
    }
    if (autoTranslatedDraftRef.current[composerEligibleMissionId] === content) {
      return;
    }
    const timer = window.setTimeout(() => {
      setTranslatorDrafts((prev) => ({ ...prev, [composerEligibleMissionId]: content }));
      autoTranslatedDraftRef.current[composerEligibleMissionId] = content;
      void translateMissionPrompt(content, composerEligibleMissionId, true);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [composerEligibleMissionId, unifiedIntentText]);

  const packets = useMemo(() => groupPackets(data.events_recent || []), [data.events_recent]);

  useEffect(() => {
    if (!selectedRecord && packets[0]?.recordName) {
      setSelectedRecord(packets[0].recordName);
    }
  }, [packets, selectedRecord]);

  const selectedPacket = packets.find((p) => p.recordName === selectedRecord) ?? packets[0] ?? null;
  const missionInputText = selectedMissionId ? missionInputDrafts[selectedMissionId] || "" : "";
  const missionChatText = selectedMissionId ? missionChatDrafts[selectedMissionId] || "" : "";
  const translatorDraftText = selectedMissionId ? translatorDrafts[selectedMissionId] || "" : "";

  const setUnifiedIntentDraft = (value: string) => {
    setUnifiedIntentDrafts((prev) => ({ ...prev, [unifiedDraftKey]: value }));
  };

  const clearUnifiedIntentDraft = (draftKey?: string | null) => {
    const key = draftKey || unifiedDraftKey;
    setUnifiedIntentDrafts((prev) => ({ ...prev, [key]: "" }));
  };

  const setMissionInputDraft = (value: string) => {
    if (!selectedMissionId) return;
    setMissionInputDrafts((prev) => ({ ...prev, [selectedMissionId]: value }));
  };

  const setMissionChatDraft = (value: string) => {
    if (!selectedMissionId) return;
    setMissionChatDrafts((prev) => ({ ...prev, [selectedMissionId]: value }));
  };

  const setTranslatorDraft = (value: string) => {
    if (!selectedMissionId) return;
    setTranslatorDrafts((prev) => ({ ...prev, [selectedMissionId]: value }));
  };

  const clearMissionInputDraft = (missionId?: string | null) => {
    if (!missionId) return;
    setMissionInputDrafts((prev) => ({ ...prev, [missionId]: "" }));
  };

  const clearMissionChatDraft = (missionId?: string | null) => {
    if (!missionId) return;
    setMissionChatDrafts((prev) => ({ ...prev, [missionId]: "" }));
  };

  const clearTranslatorDraft = (missionId?: string | null) => {
    if (!missionId) return;
    setTranslatorDrafts((prev) => ({ ...prev, [missionId]: "" }));
  };

  const queueCounts = useMemo(() => deriveQueueCounts(data), [data]);
  const gateOpen = useMemo(() => deriveGateOpen(data), [data]);

  const returnAll = data.return_all ?? fallbackData.return_all;
  const nanny = data.nanny ?? fallbackData.nanny;
  const systemSignals = (nanny.system_signals ?? []).filter(
    (item): item is NannySignal => !!item && typeof item.title === "string" && typeof item.action_label === "string"
  );
  const dispatchCounts = data.dispatch_counts ?? fallbackData.dispatch_counts;
  const supportActivity: SupportHelperActivity = data.support_helper_activity ?? fallbackData.support_helper_activity ?? {
    available: false,
    total: 0,
    lane_counts: {},
    status_counts: {},
    items: [],
    source_dirs: {},
  };
  const helper2bRuntime: Helper2bRuntimeStatus = data.helper_2b_runtime ?? fallbackData.helper_2b_runtime ?? {
    available: false,
    configured: false,
    enabled: false,
    role_id: "spinetop_expeditioner",
  };
  const mirrorDoorTest: MirrorDoorTestStatus = data.mirror_door_test ?? fallbackData.mirror_door_test ?? {
    available: false,
    script_path: "",
    fixture_root: "",
    fixture_categories: [],
    fixture_files: 0,
  };
  const helperLaneSummary = ([
    ["orchestration", supportActivity.lane_counts["orchestration"] ?? 0],
    ["retrieval", supportActivity.lane_counts["retrieval"] ?? 0],
  ] as Array<[string, number]>)
    .filter(([, count]) => count > 0)
    .map(([lane, count]) => `${count} ${lane}`)
    .join(", ") || "no helper records";
  const helperTone: StripTone = !supportActivity.available
    ? "off"
    : (supportActivity.status_counts.blocked ?? 0) > 0
      ? "watch"
      : "good";
  const helper2bTone: StripTone = !helper2bRuntime.available
    ? "off"
    : helper2bRuntime.enabled
      ? "good"
      : "watch";
  const dispatchTone: StripTone = (dispatchCounts.pending ?? 0) === 0 ? "good" : "watch";
  const nannyTone: StripTone =
    nanny.ok && nanny.temperature === "cool" && (nanny.burst_score ?? 0) === 0 && (nanny.error_score ?? 0) === 0 ? "good" : "watch";
  const returnAllTone: StripTone = returnAll.enabled ? "watch" : "off";
  const mirrorDoorBlocked = mirrorDoorTest.correctly_blocked ?? 0;
  const mirrorDoorAccepted = mirrorDoorTest.validly_accepted ?? 0;
  const mirrorDoorUnexpected = (mirrorDoorTest.unexpected_accept ?? 0) + (mirrorDoorTest.unexpected_error ?? 0);
  const mirrorDoorHealth = mirrorDoorTest.available
    ? mirrorDoorUnexpected === 0
      ? "healthy"
      : "attention"
    : "unavailable";
  const storageOverview = (data.storage_overview ?? fallbackData.storage_overview) as StorageOverview;
  const compactorLastRun = (storageOverview.compactor_last_run ?? {}) as CompactorLastRunSummary;
  const storageHotspots = storageOverview.hotspots?.length ? storageOverview.hotspots : (storageOverview.areas || []).slice(0, 6);
  const selectedMissionFolders = selectedMission?.workbench?.folders ?? [];
  const selectedMissionFiles = selectedMission?.workbench?.files ?? [];
  const selectedMissionArtifacts = selectedMission?.artifact_index?.items ?? [];
  const selectedMissionInputs = selectedMission?.mission_inputs ?? [];
  const workbenchFilesForFolder = selectedMissionFiles.filter((file) => file.folder === workbenchFolder);
  const selectedMissionArtifactRefs = (selectedMission?.artifact_refs?.length ? selectedMission.artifact_refs : selectedMissionArtifacts)
    .slice(-12)
    .reverse();
  const latestHermesRun = selectedMission?.latest_hermes_run ?? null;
  const latestDraft = selectedMission?.latest_draft ?? null;
  const latestClarificationPacket = selectedMission?.latest_clarification_packet ?? null;
  const latestRunnerReturn = selectedMission?.latest_runner_return ?? null;
  const latestPromptTranslation = selectedMission?.latest_prompt_translation ?? null;
  const promptTranslationCount = selectedMission?.prompt_translation_count ?? 0;
  const dismissedTranslationId = selectedMissionId ? dismissedTranslationByMission[selectedMissionId] ?? null : null;
  const promptTranslationPreview =
    (selectedMissionId ? translatorPreviewByMission[selectedMissionId] ?? null : null) ||
    (latestPromptTranslation && latestPromptTranslation.translation_id !== dismissedTranslationId ? latestPromptTranslation : null);
  const composerPromptTranslationPreview =
    (composerEligibleMissionId ? translatorPreviewByMission[composerEligibleMissionId] ?? null : null) ||
    (composerEligibleMissionId === selectedMissionId ? promptTranslationPreview : null);
  const missionSummary = selectedMission?.mission_summary ?? null;
  const missionParkingStatus = selectedMission?.parking_status ?? null;
  const missionAutonomyStatus = selectedMission?.autonomy_status ?? null;
  const controlTowerSummary = selectedMission?.control_tower_summary ?? null;
  const latestRoleActivity = controlTowerSummary?.latest_role_activity ?? null;
  const latestRoleActivityText =
    latestRoleActivity?.role && latestRoleActivity?.summary
      ? `${latestRoleActivity.role} -> ${latestRoleActivity.summary}`
      : "No explicit role invocation recorded.";
  const runnerReturnCount = selectedMission?.runner_return_count ?? 0;
  const missionAssumptionEntries = selectedMission?.assumptions ?? [];
  const missionAssumptionCount = selectedMission?.assumption_count ?? missionAssumptionEntries.length;
  const missionActiveAssumptionCount =
    selectedMission?.active_assumption_count ??
    missionAssumptionEntries.filter((item) => ["active", "accepted"].includes(item.status || "")).length;
  const missionAssumptionReviewNeeded =
    selectedMission?.assumption_review_needed ??
    missionAssumptionEntries.some((item) => item.status === "active" && (item.confirmation?.operator_status || "unreviewed") === "unreviewed");
  const missionAssumptionChanges = selectedMission?.latest_assumption_changes ?? [];
  const missionAssumptionsLastUpdated = selectedMission?.assumptions_last_updated ?? "";
  const visibleMissionAssumptions = showAllAssumptions ? missionAssumptionEntries : missionAssumptionEntries.slice(0, 3);
  const hiddenMissionAssumptions = Math.max(0, missionAssumptionEntries.length - visibleMissionAssumptions.length);
  const latestDraftReviewPreview = getRecordObject(latestDraft, "review_preview");
  const latestDraftPreviewPath = getRecordString(latestDraftReviewPreview, "draft_path") || getRecordString(latestDraft, "draft_path");
  const latestDraftSummary =
    getRecordObject(latestDraft, "draft") ? getRecordString(getRecordObject(latestDraft, "draft"), "summary") : "";
  const latestPacketSummary = getRecordString(getRecordObject(latestClarificationPacket, "provisional_answer"), "text");
  const missionSummaryOperatingStatus = missionSummary?.operating_status || missionSummary?.status || selectedMission?.status_badge || selectedMission?.current_state || "unknown";
  const missionSummaryLifecycleState = missionSummary?.life_cycle_state || selectedMission?.current_state || "unknown";
  const missionSummaryOperatorPosture = missionSummary?.operator_posture || selectedMission?.operator_posture || "active";
  const missionSummaryOperatorReason =
    missionSummary?.operator_posture_reason || selectedMission?.operator_posture_reason || missionSummary?.clarification_reason || "";
  const missionSummaryTriageBucket = missionSummary?.triage_bucket || selectedMission?.triage_bucket || "do_now";
  const missionSummaryCanContinue =
    missionSummary?.can_continue_without_input ?? !["needs_operator_answer", "parked"].includes(missionSummaryOperatorPosture);
  const missionSummaryBlockedReason = missionSummary?.blocked_reason || "";
  const missionSummaryCrewStatus = missionSummary?.crew_status || (missionSummaryCanContinue ? "active" : "recalled");
  const missionSummaryExpeditionActivity = missionSummary?.expedition_activity || (missionSummaryCanContinue ? "running" : "paused");
  const missionSummaryParkedAt = missionSummary?.parked_at || "";
  const missionSummaryWakeHintSeed = missionSummary?.wake_hint || "";
  const missionSummaryBeliefs =
    missionSummary?.what_we_believe?.length
      ? missionSummary.what_we_believe
      : [
          getRecordString(latestHermesRun, "summary") ||
            getRecordString(selectedMission?.manifest, "summary") ||
            selectedMission?.objective ||
            "No mission summary has been built yet.",
        ];
  const missionSummaryConfirmedFacts = missionSummary?.confirmed_facts?.length ? missionSummary.confirmed_facts : [];
  const missionSummaryAssumptions =
    missionSummary?.assumptions_active?.length
      ? missionSummary.assumptions_active
      : missionSummary?.active_assumptions?.length
        ? missionSummary.active_assumptions
        : selectedMission?.assumptions_active?.length
          ? selectedMission.assumptions_active
          : [];
  const missionSummaryOpenQuestions = missionSummary?.open_questions?.length ? missionSummary.open_questions : [];
  const missionSummaryDeferredQuestions = missionSummary?.deferred_questions?.length ? missionSummary.deferred_questions : [];
  const missionSummaryBlockingQuestions =
    missionSummary?.blocking_questions?.length
      ? missionSummary.blocking_questions
      : selectedMission?.blocking_questions?.length
        ? selectedMission.blocking_questions
        : [];
  const missionSummaryNeeds =
    missionSummary?.what_we_need_from_you?.length
      ? missionSummary.what_we_need_from_you
      : missionSummaryCanContinue && missionSummaryOpenQuestions.length
        ? missionSummaryOpenQuestions.slice(0, 2).map((question) => `Optional: ${question}`)
        : selectedMission
          ? missionSummaryCanContinue
            ? ["No immediate input is required."]
            : ["A blocking clarification is required."]
        : [];
  const missionSummaryReason =
    missionSummaryOperatorReason ||
    missionSummary?.clarification_reason ||
    (missionSummaryCanContinue ? "Proceeding under explicit assumptions." : missionSummaryBlockedReason || "No clarification block is active.");
  const missionSummaryQuestion = missionSummary?.next_question || missionSummaryOpenQuestions[0] || "";
  const missionSummaryQuickReplies =
    missionSummary?.operator_options?.length
      ? missionSummary.operator_options
      : selectedMission?.operator_options?.length
        ? selectedMission.operator_options
        : missionSummary?.quick_replies?.length
          ? missionSummary.quick_replies
          : missionSummaryOperatorPosture === "parked"
            ? [
                { label: "Resume mission", value: "Resume mission" },
                { label: "Answer blockers", value: "Answer blockers" },
              ]
            : [
                { label: "Proceed with assumptions", value: "Proceed with assumptions" },
                { label: "Answer blockers", value: "Answer blockers" },
                { label: "Park mission", value: "Park mission" },
                ...(latestDraftPreviewPath ? [{ label: "Open review preview", value: "Open review preview" }] : []),
              ];
  const missionSummaryConfidence = missionSummary
    ? `${Math.round((missionSummary.confidence ?? 0) * 100)}% (${missionSummary.confidence_label})${
        (missionSummary.confidence_reduction ?? 0) > 0 ? `, -${Math.round((missionSummary.confidence_reduction ?? 0) * 100)}%` : ""
      }`
    : "unknown";
  const missionSummaryNextStep = missionSummary?.recommended_next_step || "Add context in mission chat or intake.";
  const missionSummaryNextAnswer =
    missionSummary?.next_best_operator_answer ||
    missionSummaryQuestion ||
    (missionSummaryCanContinue ? "No immediate reply is required." : "A blocking clarification is required.");
  const missionSummaryWakeHint = missionSummaryWakeHintSeed || missionSummaryQuestion || missionSummaryBlockedReason;
  const controlTowerAutonomyState = controlTowerSummary?.autonomy_state || missionAutonomyStatus?.autonomy_status || "ready";
  const controlTowerAutonomyTone: StripTone =
    controlTowerAutonomyState === "blocked" ? "watch" : controlTowerAutonomyState === "guarded" ? "watch" : "good";
  const controlTowerRetryBudget = controlTowerSummary?.retry_budget ?? 0;
  const controlTowerRetryUsed = controlTowerSummary?.retry_used ?? 0;
  const controlTowerRetryRemaining = Math.max(0, controlTowerRetryBudget - controlTowerRetryUsed);
  const controlTowerSafeActions = (controlTowerSummary?.safe_operator_actions ?? []).filter(Boolean);
  const recentControlInterventions = (controlTowerSummary?.recent_operator_interventions ?? []).filter(Boolean);
  const supportedControlActions = controlTowerSafeActions.filter((action) =>
    [
      "resume mission",
      "park mission",
      "retry bounded action",
      "refresh assumptions",
      "sync helper returns",
      "clear stale pending handoff",
      "mark archive candidate",
      "answer blocker",
    ].includes(action.toLowerCase())
  );
  const unsupportedControlActions = controlTowerSafeActions.filter(
    (action) => !supportedControlActions.includes(action)
  );
  const repeatedItemCount = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of data.events_recent || []) {
      const key = event.record_name || event.event_type || "";
      if (!key) continue;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return Array.from(counts.values()).filter((count) => count > 1).reduce((sum, count) => sum + count - 1, 0);
  }, [data.events_recent]);
  const attentionItems = useMemo<MissionAttentionItem[]>(
    () => deriveAttentionItems(expeditions, petitionDrafts, repeatedItemCount),
    [expeditions, petitionDrafts, repeatedItemCount]
  );
  const visibleExpeditions = useMemo(() => groupExpeditions(expeditions, selectedMissionId), [expeditions, selectedMissionId]);
  const queueSummary = expeditionQueueSummary;
  const blockedWaitingCount = attentionItems.filter((item) => item.key !== "noisy-signals").length;
  const selectedQueueHygiene = selectedMission?.queue_hygiene;
  const selectedQueueSignals = (selectedQueueHygiene?.signals ?? []).filter(Boolean);
  const latestMeaningfulSummary =
    latestDraftSummary ||
    getRecordString(latestHermesRun, "summary") ||
    getRecordString(selectedMission?.manifest, "summary") ||
    selectedMission?.objective ||
    "No summary recorded yet.";
  const localNewMissionTranslation: PromptTranslation | null = !composerEligibleMissionId && unifiedIntentText.trim()
    ? {
        translation_id: "local-new-mission",
        created_at: new Date().toISOString(),
        source_text: unifiedIntentText,
        target_type: "new_mission",
        target_mission_id: null,
        recommended_role: "expeditioner",
        recommended_mode: "first_pass",
        scope: "mission_local",
        sufficiency: {
          can_proceed: true,
          missing_requirements: [],
        },
        recommended_safe_action: "create new mission from explicit operator intent",
        requires_operator_confirmation: true,
        translated_instruction: unifiedIntentText.trim(),
        notes: [
          selectedMissionIsParked
            ? "The focused mission is parked, so freeform input stays off that mission until you explicitly resume it."
            : "No eligible active mission is focused, so this stays as a local start-mission draft until you confirm.",
        ],
        derived_only: true,
      }
    : null;
  const activeTranslationPreview = composerPromptTranslationPreview || localNewMissionTranslation;
  const unifiedIntentLower = unifiedIntentText.trim().toLowerCase();
  const composerWantsQueueCleanup =
    !!unifiedIntentLower &&
    /(clean|clear|fix|tidy|sort|collapse|dedupe|de-dupe|archive|park).*(queue|feed|missions|duplicates)|queue cleanup|clean the queue/i.test(
      unifiedIntentLower
    );
  const composerWantsNewMission =
    (!selectedMissionId && !!unifiedIntentText.trim()) ||
    /(new mission|start (a )?mission|create (a )?mission|fresh mission|separate mission)/i.test(unifiedIntentLower);
  const composerWantsReview = /(review|inspect|check|audit|look over|look at)/i.test(unifiedIntentLower);
  const composerWantsFix = /(fix|retry|repair|clean|clear|resume|unblock|resolve)/i.test(unifiedIntentLower);
  const composerTargetLabel = composerWantsQueueCleanup
    ? "Existing mission"
    : composerWantsNewMission || activeTranslationPreview?.target_type === "new_mission"
      ? "New mission"
      : composerRetargetedFromParkedMission
        ? "Another active mission"
        : "Existing mission";
  const composerModeLabel = composerWantsQueueCleanup
    ? "Fix"
    : composerWantsNewMission || activeTranslationPreview?.target_type === "new_mission"
      ? "Create"
      : composerWantsReview || activeTranslationPreview?.recommended_mode === "review"
        ? "Review"
        : composerWantsFix || ["retry", "resume"].includes(activeTranslationPreview?.recommended_mode || "")
          ? "Fix"
          : "Continue";
  const composerInterpretation = (() => {
    if (!unifiedIntentText.trim()) return "Add an idea, blocker, or command.";
    if (composerWantsQueueCleanup) return "Clean the queue";
    if (composerWantsNewMission) return compactIntentLabel(unifiedIntentText, "Start a new mission");
    if (composerWantsReview) return compactIntentLabel(unifiedIntentText, "Review the mission");
    if (composerModeLabel === "Fix") return compactIntentLabel(unifiedIntentText, "Fix the mission flow");
    return compactIntentLabel(
      activeTranslationPreview?.recommended_safe_action || unifiedIntentText,
      composerEligibleMissionId ? "Continue the active mission" : "Start a mission"
    );
  })();
  const composerRole = activeTranslationPreview?.recommended_role || (composerModeLabel === "Review" ? "sentinel" : "expeditioner");
  const composerScope = activeTranslationPreview?.scope || "mission_local_only";
  const composerNotes = composerWantsQueueCleanup
    ? ["Queue cleanup stays inside the current mission feed and does not delete anything."]
    : activeTranslationPreview?.notes?.length
      ? activeTranslationPreview.notes
      : [
          composerRetargetedFromParkedMission
            ? "The focused mission is parked, so the composer is routing to another eligible active mission until you explicitly resume it."
            : "The composer is using the current mission focus and bounded local heuristics.",
        ];
  const composerInstruction = composerWantsQueueCleanup
    ? "Apply safe feed cleanup: collapse duplicates, park blocked missions, and mark archive candidates without changing backend triggers."
    : activeTranslationPreview?.translated_instruction || unifiedIntentText.trim();
  const composerPrimaryLabel =
    composerWantsNewMission || (!composerEligibleMissionId && !!unifiedIntentText.trim()) ? "Start mission" : "Do this";
  const composerNeedsText =
    !composerWantsQueueCleanup &&
    !composerWantsNewMission &&
    !selectedMissionIsParked &&
    selectedMission?.status_badge !== "ready_for_review" &&
    !latestDraftReviewPreview;
  const composerCanSubmit =
    !missionSaving &&
    !translatorSaving &&
    !missionLoading &&
    !loading &&
    (!composerNeedsText || !!unifiedIntentText.trim());
  const composerResultToneStyle =
    errorText
      ? styles.composerResultBad
      : uiNotice?.tone === "good"
        ? styles.composerResultGood
        : uiNotice?.tone === "watch"
          ? styles.composerResultWarn
          : styles.composerResultInfo;
  const confidenceGauge = missionSummary?.confidence_label === "high"
    ? "HIGH"
    : missionSummary?.confidence_label === "low"
      ? "LOW"
      : "MEDIUM";
  const confidenceTrend =
    (missionSummary?.confidence_reduction ?? 0) > 0.15 ? "falling" : (missionSummary?.confidence_reduction ?? 0) > 0 ? "softening" : "steady";
  const queuePressure = queuePressureLabel(queueSummary, expeditions.length);
  const systemSignalsVisible = systemSignals.length > 0;
  const blockerType = blockerTypeLabel({
    canContinue: missionSummaryCanContinue,
    operatorPosture: missionSummaryOperatorPosture,
    blockingQuestions: missionSummaryBlockingQuestions,
    queueHygiene: selectedQueueHygiene,
    blockedReason: missionSummaryBlockedReason || missionSummaryReason,
  });
  const missionStateGauge = missionStateGaugeLabel({
    parked: selectedMissionIsParked,
    blocked: !missionSummaryCanContinue || blockerType === "HUMAN",
    caution:
      !!missionAssumptionReviewNeeded ||
      !!selectedQueueSignals.length ||
      selectedMission?.status_badge === "ready_for_review" ||
      (missionSummary?.confidence_label || "") === "moderate",
  });
  const autonomyGauge =
    controlTowerAutonomyState === "blocked"
      ? "BLOCKED"
      : controlTowerAutonomyState === "guarded"
        ? "GUARDED"
        : selectedMission
          ? "READY"
          : "IDLE";
  const shouldShowReturnToBase = !!selectedMission && (missionStateGauge === "BLOCKED" || missionStateGauge === "PARKED");
  const returnToBaseOptions = [
    {
      key: "retry",
      label: "Retry with safe assumptions",
      confidence: "HIGH",
      detail: "Refresh the mission through the bounded retry lane.",
    },
    {
      key: "narrow",
      label: "Narrow scope / partial result",
      confidence: "MEDIUM",
      detail: "Ask the mission to finish with a narrower safe slice.",
    },
    {
      key: "alternate",
      label: "Alternate approach",
      confidence: "LOW",
      detail: "Request a different safe route without broadening authority.",
    },
  ] as const;
  const duplicateTriageGroups = visibleExpeditions.groups.filter((group) => group.duplicate_count > 1);
  const archiveCandidates = expeditions.filter((expedition) => expedition.queue_hygiene?.archive_candidate);
  const blockedQueueItems = expeditions.filter(
    (expedition) =>
      expedition.operator_posture === "needs_operator_answer" ||
      expedition.triage_bucket === "waiting" ||
      expedition.status_badge === "waiting_for_user"
  );
  const activeQueueItems = expeditions.filter(
    (expedition) =>
      missionFeedState(expedition) === "ACTIVE" &&
      !expedition.queue_hygiene?.archive_candidate &&
      !expedition.queue_hygiene?.duplicate_candidate
  );
  const { mainFeedGroups, parkedFeedGroups, archiveFeedGroups, duplicateFeedGroups } = useMemo(
    () => deriveFeedBuckets({ visibleGroups: visibleExpeditions, dismissedMissionBuckets }),
    [visibleExpeditions, dismissedMissionBuckets]
  );
  const dominantAction = useMemo(
    () =>
      derivePrimaryAction({
        queuePressure,
        missionStateGauge,
        blockerType,
        selectedMissionStatusBadge: selectedMission?.status_badge,
        latestDraftReviewPreview,
        composerEligibleMissionId,
        activeTranslationPreview,
        composerRetargetedFromParkedMission,
        unifiedIntentText,
      }),
    [
      queuePressure,
      missionStateGauge,
      blockerType,
      selectedMission?.status_badge,
      latestDraftReviewPreview,
      composerEligibleMissionId,
      activeTranslationPreview,
      composerRetargetedFromParkedMission,
      unifiedIntentText,
    ]
  );
  const shellResultLine = errorText
    ? errorText
    : uiNotice
      ? `${uiNotice.title}. ${uiNotice.detail}`
      : activeTranslationPreview
        ? `${activeTranslationPreview.target_type === "new_mission"
            ? "New mission"
            : `Mission ${activeTranslationPreview.target_mission_id || composerEligibleMissionId || selectedMissionId || "selected"}`
          }: ${activeTranslationPreview.recommended_safe_action || dominantAction.detail}`
        : dominantAction.detail;

  const expeditionStatusTone: Record<ExpeditionStatusBadge, StripTone> = deriveExpeditionStatusTone();

  const openMissionsView = () => {
    setViewMode("missions");
    setUiNotice({
      tone: "info",
      title: "Mission view opened",
      detail: "The active expeditions and focused mission pane are now front and center.",
    });
  };

  const openDiagnosticsView = () => {
    setViewMode("diagnostics");
    setUiNotice({
      tone: "info",
      title: "Diagnostics opened",
      detail: "Telemetry, storage, drafts, and helper lanes are available below.",
    });
  };

  const toggleMissionExpansion = (missionId: string, detail?: string) => {
    const isExpanded = !!expandedMissionIds[missionId];
    setExpandedMissionIds((prev) => {
      if (isExpanded) {
        const next = { ...prev };
        delete next[missionId];
        return next;
      }
      return { ...prev, [missionId]: true };
    });
    if (!isExpanded && !missionDetailsById[missionId]) {
      void loadMissionDetail(missionId);
    }
    setUiNotice({
      tone: "info",
      title: isExpanded ? "Mission collapsed" : "Mission expanded",
      detail: detail || `${isExpanded ? "Collapsed" : "Expanded"} ${missionId} in the feed.`,
    });
  };

  const rememberDismissedMission = (missionId: string, bucket: DismissBucket) => {
    setDismissedMissionBuckets((prev) => ({ ...prev, [missionId]: bucket }));
    setExpandedMissionIds((prev) => {
      if (!prev[missionId]) return prev;
      const next = { ...prev };
      delete next[missionId];
      return next;
    });
    if (selectedMissionId === missionId) {
      setSelectedMissionId(null);
      setSelectedMission(null);
    }
  };

  const restoreDismissedMission = (missionId: string) => {
    setDismissedMissionBuckets((prev) => {
      const next = { ...prev };
      delete next[missionId];
      return next;
    });
    focusMission(missionId, `Returned ${missionId} to the visible mission feed.`);
  };

  const focusMission = (missionId: string, detail?: string) => {
    setExpandedMissionIds((prev) => ({ ...prev, [missionId]: true }));
    setSelectedMissionId(missionId);
    setViewMode("missions");
    if (!missionDetailsById[missionId]) {
      void loadMissionDetail(missionId);
    }
    setUiNotice({
      tone: "good",
      title: "Mission selected",
      detail: detail || `Focused mission ${missionId}.`,
    });
  };

  const handleSystemSignalAction = (signal: NannySignal) => {
    const actionKind = signal.action_kind || "";
    if (actionKind === "clean_queue") {
      setViewMode("missions");
      setShowArchiveCandidates(true);
      setShowParkedMissions(true);
      setShowDuplicateMissions(true);
      setUiNotice({
        tone: "watch",
        title: signal.title,
        detail: "Opened archive, parked, and duplicate trays for operator review. No cleanup was executed.",
      });
      return;
    }
    if (actionKind === "review_system_fix") {
      setViewMode("diagnostics");
      setUiNotice({
        tone: "watch",
        title: signal.title,
        detail: "Switched to diagnostics so you can inspect the system issue without changing state.",
      });
      return;
    }
    if (actionKind === "review_blocked_missions") {
      const blockedMission = expeditions.find((item) =>
        item.queue_hygiene?.blocked_candidate || item.status_badge === "waiting_for_user" || item.triage_bucket === "waiting"
      );
      if (blockedMission) {
        focusMission(blockedMission.mission_id, blockedMission.summary || blockedMission.objective || blockedMission.mission_id);
      } else {
        setViewMode("missions");
      }
      setUiNotice({
        tone: "watch",
        title: signal.title,
        detail: "Focused the blocked queue for review. No retry or mission mutation was triggered.",
      });
      return;
    }
    if (actionKind === "revive_eligible_missions") {
      setViewMode("missions");
      setShowParkedMissions(true);
      const reviveMission = expeditions.find((item) =>
        item.queue_hygiene?.parked_candidate && !item.queue_hygiene?.archive_candidate && !item.queue_hygiene?.junk_pattern
      );
      if (reviveMission) {
        focusMission(reviveMission.mission_id, reviveMission.summary || reviveMission.objective || reviveMission.mission_id);
      }
      setUiNotice({
        tone: "watch",
        title: signal.title,
        detail: "Opened parked missions for review. Nothing was resumed automatically.",
      });
      return;
    }
    if (actionKind === "collapse_duplicates") {
      setViewMode("missions");
      setShowDuplicateMissions(true);
      setUiNotice({
        tone: "watch",
        title: signal.title,
        detail: "Opened duplicate groups for review. No missions were merged or archived.",
      });
      return;
    }
    setUiNotice({
      tone: "watch",
      title: signal.title,
      detail: "This is a recommendation only. No action was executed.",
    });
  };

  const {
    refreshAssumptions,
    reviewAssumption,
    syncRunnerReturns,
    openReviewPreview,
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
    submitMissionComposer,
    runReturnToBaseOption,
  } = useMissionActions({
    apiBase: API_BASE,
    load,
    selectedMissionId,
    setSelectedMissionId,
    selectedMission,
    setSelectedMission,
    selectedMissionSummary,
    setViewMode,
    setSelectedDraftPath,
    workbenchFolder,
    setWorkbenchFolder,
    newMissionObjective,
    setNewMissionObjective,
    unifiedIntentText,
    selectedMissionIsParked,
    composerEligibleMissionId,
    activeTranslationPreview,
    missionInputText,
    translatorDraftText,
    missionSummaryOperatorReason,
    missionSummaryBlockedReason,
    missionSummaryNextAnswer,
    missionSummaryQuestion,
    controlTowerSummary,
    selectedQueueHygiene,
    latestDraftPreviewPath,
    promptTranslationPreview,
    duplicateFeedGroups,
    archiveFeedGroups,
    blockedQueueItems,
    dominantAction,
    blockerType,
    missionSaving,
    setMissionSaving,
    setTranslatorSaving,
    setMissionActionLabel,
    setUiNotice,
    setErrorText,
    clearUnifiedIntentDraft,
    clearMissionInputDraft,
    clearMissionChatDraft,
    clearTranslatorDraft,
    setMissionInputDrafts,
    setMissionChatDrafts,
    setTranslatorPreviewByMission,
    setDismissedTranslationByMission,
    rememberDismissedMission,
    setTriageMode,
    setShowArchiveCandidates,
    setShowParkedMissions,
    setShowDuplicateMissions,
    missionInputInFlightRef,
    missionChatInFlightRef,
    missionChatComposerRef,
  });

  const copyTranslatedInstruction = async () => {
    const translation = promptTranslationPreview;
    if (!translation) {
      setErrorText("No translated instruction is available to copy");
      return;
    }
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard is unavailable in this browser");
      }
      await navigator.clipboard.writeText(translation.translated_instruction || "");
      setUiNotice({
        tone: "good",
        title: "Instruction copied",
        detail: "The translated instruction was copied. It is still proposal-only.",
      });
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Copy failed");
    }
  };

  const stageTranslatedInstructionForMissionInput = () => {
    const translation = promptTranslationPreview;
    const missionId = selectedMissionId;
    if (!translation || !missionId) return;
    setMissionInputDrafts((prev) => ({ ...prev, [missionId]: translation.translated_instruction || "" }));
    setUiNotice({
      tone: "info",
      title: "Mission input draft staged",
      detail: "The translated instruction was copied into the mission input draft. It was not sent.",
    });
  };

  const stageTranslatedInstructionForChat = () => {
    const translation = promptTranslationPreview;
    const missionId = selectedMissionId;
    if (!translation || !missionId) return;
    setMissionChatDrafts((prev) => ({ ...prev, [missionId]: translation.translated_instruction || "" }));
    missionChatComposerRef.current?.focus();
    setUiNotice({
      tone: "info",
      title: "Chat draft staged",
      detail: "The translated instruction was copied into mission chat draft only. It was not sent.",
    });
  };

  const stageProposedMissionDraft = () => {
    const translation = promptTranslationPreview;
    if (!translation) return;
    const objectiveSeed =
      translation.target_type === "new_mission"
        ? translation.source_text || translation.translated_instruction || ""
        : translation.translated_instruction || translation.source_text || "";
    setNewMissionObjective(objectiveSeed);
    setUiNotice({
      tone: "info",
      title: "Proposed mission draft staged",
      detail: "The new mission objective box was prefilled only. No mission was created.",
    });
  };

  const discardPromptTranslation = () => {
    const missionId = selectedMissionId;
    if (!missionId) return;
    const translationId = promptTranslationPreview?.translation_id ?? null;
    clearTranslatorDraft(missionId);
    setTranslatorPreviewByMission((prev) => ({ ...prev, [missionId]: null }));
    setDismissedTranslationByMission((prev) => ({ ...prev, [missionId]: translationId }));
    setUiNotice({
      tone: "info",
      title: "Translator draft cleared",
      detail: "The current proposal was dismissed from view. Nothing was executed.",
    });
  };

  useEffect(() => {
    if (!shouldShowReturnToBase || !selectedMissionId) {
      setReturnToBaseCountdown(null);
      autoReturnToBaseKeyRef.current = null;
      return;
    }
    const autoKey = `${selectedMissionId}:${missionStateGauge}:${missionSummaryBlockedReason}:${missionSummaryQuestion}`;
    if (autoReturnToBaseKeyRef.current === autoKey) {
      return;
    }
    autoReturnToBaseKeyRef.current = autoKey;
    setReturnToBaseCountdown(8);
    const interval = window.setInterval(() => {
      setReturnToBaseCountdown((value) => {
        if (value == null) return null;
        return value > 0 ? value - 1 : 0;
      });
    }, 1000);
    const timeout = window.setTimeout(() => {
      void runReturnToBaseOption("retry", true);
    }, 8000);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(timeout);
    };
  }, [shouldShowReturnToBase, selectedMissionId, missionStateGauge, missionSummaryBlockedReason, missionSummaryQuestion]);

  const renderMissionFeed = () => (
    <div id="expeditions" style={styles.panel}>
      <div style={styles.sectionTitleRow}>
        <div>
          <h2 style={styles.sectionTitle}>Mission Feed</h2>
          <div style={styles.sectionSubtitle}>Collapsed by default, expanded inline, swipe-or-tap dismiss, and less visual noise.</div>
        </div>
        <div style={styles.pillRow}>
          <span style={{ ...styles.badge, ...styles.badgeGood }}>{mainFeedGroups.length} in feed</span>
          <span style={styles.badge}>{queuePressure}</span>
        </div>
      </div>

      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", marginBottom: 16 }}>
        <div style={styles.previewBox}><div style={styles.subtleText}>Active</div><div style={{ marginTop: 4, fontSize: 18, fontWeight: 700, color: "#f8fafc" }}>{mainFeedGroups.filter((group) => missionFeedState(group.primary) === "ACTIVE").length}</div></div>
        <div style={styles.previewBox}><div style={styles.subtleText}>Blocked</div><div style={{ marginTop: 4, fontSize: 18, fontWeight: 700, color: "#f8fafc" }}>{mainFeedGroups.filter((group) => missionFeedState(group.primary) === "BLOCKED").length}</div></div>
        <div style={styles.previewBox}><div style={styles.subtleText}>Returned</div><div style={{ marginTop: 4, fontSize: 18, fontWeight: 700, color: "#f8fafc" }}>{mainFeedGroups.filter((group) => missionFeedState(group.primary) === "RETURNED").length}</div></div>
        <div style={styles.previewBox}><div style={styles.subtleText}>Hidden by default</div><div style={{ marginTop: 4, fontSize: 18, fontWeight: 700, color: "#f8fafc" }}>{archiveFeedGroups.length + parkedFeedGroups.length + duplicateFeedGroups.length}</div></div>
      </div>

      <div style={{ ...styles.recordCard, marginBottom: 16 }}>
        <div style={styles.recordMetaRow}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Queue actions in feed</div>
            <div style={styles.subtleText}>No deletion. No truth-lane writes. Mission-local notes only when needed.</div>
          </div>
        </div>
        <div style={{ marginTop: 12, display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          <div style={styles.previewBox}><div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Duplicates</div><div style={{ marginTop: 6, ...styles.subtleText }}>{duplicateFeedGroups.length} duplicate group{duplicateFeedGroups.length === 1 ? "" : "s"} ready to collapse.</div><button type="button" onClick={() => void collapseDuplicateGroups()} disabled={!duplicateFeedGroups.length} style={{ ...styles.secondaryButton, marginTop: 10 }}>Collapse duplicates</button></div>
          <div style={styles.previewBox}><div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Archive</div><div style={{ marginTop: 6, ...styles.subtleText }}>{archiveFeedGroups.length} mission{archiveFeedGroups.length === 1 ? "" : "s"} can be moved out of the main feed.</div><button type="button" onClick={() => void markArchiveCandidates()} disabled={!archiveFeedGroups.length} style={{ ...styles.secondaryButton, marginTop: 10 }}>Mark archive candidates</button></div>
          <div style={styles.previewBox}><div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Blocked</div><div style={{ marginTop: 6, ...styles.subtleText }}>{blockedQueueItems.length} blocked mission{blockedQueueItems.length === 1 ? "" : "s"} can be parked.</div><button type="button" onClick={() => void parkBlockedMissions()} disabled={!blockedQueueItems.length} style={{ ...styles.secondaryButton, marginTop: 10 }}>Park blocked</button></div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        <button type="button" onClick={() => setShowArchiveCandidates((prev) => !prev)} style={styles.trayToggle}>{showArchiveCandidates ? "Hide archive candidates" : `Archive candidates (${archiveFeedGroups.length})`}</button>
        <button type="button" onClick={() => setShowParkedMissions((prev) => !prev)} style={styles.trayToggle}>{showParkedMissions ? "Hide parked" : `Parked (${parkedFeedGroups.length})`}</button>
        <button type="button" onClick={() => setShowDuplicateMissions((prev) => !prev)} style={styles.trayToggle}>{showDuplicateMissions ? "Hide duplicates" : `Duplicates (${duplicateFeedGroups.length})`}</button>
      </div>

      <div style={styles.expeditionList}>
        {mainFeedGroups.length ? mainFeedGroups.map((group) => {
          const expedition = group.primary;
          const isExpanded = !!expandedMissionIds[expedition.mission_id];
          const isFocused = selectedMissionId === expedition.mission_id;
          const feedState = missionFeedState(expedition);
          const confidence = missionConfidenceLabel(expedition);
          const expandedMission =
            missionDetailsById[expedition.mission_id] ??
            (selectedMission?.mission_id === expedition.mission_id ? selectedMission : null);
          const expandedMissionSummary = expandedMission?.mission_summary ?? expedition.mission_summary ?? null;
          const expandedControlTowerSummary = expandedMission?.control_tower_summary ?? expedition.control_tower_summary ?? null;
          const expandedRunnerReturn = expandedMission?.latest_runner_return ?? null;
          const expandedLatestAgentRun = expandedMission?.latest_agent_run ?? null;
          const expandedLatestRoleActivity = expandedControlTowerSummary?.latest_role_activity ?? null;
          const expandedMissionSummaryReason =
            expandedControlTowerSummary?.operator_attention_reason ||
            expandedMissionSummary?.operator_posture_reason ||
            expandedMission?.operator_posture_reason ||
            expandedMissionSummary?.clarification_reason ||
            expandedMissionSummary?.blocked_reason ||
            expedition.operator_posture_reason ||
            expedition.summary ||
            "No control tower summary yet.";
          const expandedControlTowerAutonomyState =
            expandedControlTowerSummary?.autonomy_state || expandedMission?.autonomy_status?.autonomy_status || "ready";
          const expandedRetryRemaining = Math.max(
            0,
            (expandedControlTowerSummary?.retry_budget ?? 0) - (expandedControlTowerSummary?.retry_used ?? 0)
          );
          const expandedAssumptions = expandedMission?.assumptions ?? [];
          const expandedAssumptionCount = expandedMission?.assumption_count ?? expandedAssumptions.length;
          const expandedActiveAssumptionCount =
            expandedMission?.active_assumption_count ??
            expandedAssumptions.filter((item) => ["active", "accepted"].includes(item.status || "")).length;
          const expandedVisibleAssumptions = showAllAssumptions ? expandedAssumptions : expandedAssumptions.slice(0, 3);
          const dismissLabel = dismissLabelForBucket(dismissBucketForGroup(group));
          return (
            <motion.div
              key={group.group_key}
              style={{ ...styles.feedCard, borderColor: isFocused ? "rgba(251,191,36,0.42)" : isExpanded ? "rgba(244,114,182,0.38)" : "rgba(192,132,252,0.18)" }}
              drag="x"
              dragElastic={0.12}
              dragSnapToOrigin
              onDragEnd={(_, info) => {
                if (Math.abs(info.offset.x) >= 120) void dismissMissionGroup(group);
              }}
            >
              <button type="button" onClick={() => toggleMissionExpansion(expedition.mission_id, missionFeedSummary(expedition))} style={styles.feedHeaderButton}>
                <div style={styles.feedMetaRow}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 17, fontWeight: 800, color: "#f8fafc" }}>{expedition.objective || expedition.mission_id}</div>
                    <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" as const }}>
                      <span style={{ ...styles.badge, ...(feedState === "ACTIVE" ? styles.badgeGood : feedState === "BLOCKED" || feedState === "RETURNED" ? styles.badgeWarn : styles.badgeOutline) }}>{feedState}</span>
                      <span style={styles.badge}>{confidence}</span>
                      {group.duplicate_count > 1 ? <span style={{ ...styles.badge, ...styles.badgeOutline }}>{group.duplicate_count} similar</span> : null}
                    </div>
                    <div style={{ marginTop: 10, fontSize: 13, color: "#cbd5f5", lineHeight: 1.5 }}>{missionFeedSummary(expedition)}</div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column" as const, gap: 8, alignItems: "flex-end", flexShrink: 0 }}>
                    <button type="button" onClick={(event) => { event.stopPropagation(); toggleMissionExpansion(expedition.mission_id, missionFeedSummary(expedition)); }} style={styles.feedActionButton}>{isExpanded ? "Collapse" : "Expand"}</button>
                    <div style={styles.feedSecondaryActionRow}>
                      <button type="button" onClick={(event) => { event.stopPropagation(); focusMission(expedition.mission_id, missionFeedSummary(expedition)); }} style={styles.dismissButton}>{isFocused ? "Focused" : "Focus"}</button>
                      <button type="button" onClick={(event) => { event.stopPropagation(); void dismissMissionGroup(group); }} style={styles.dismissButton}>{dismissLabel}</button>
                    </div>
                  </div>
                </div>
              </button>

              {isExpanded ? (
                <div style={{ marginTop: 14, display: "grid", gap: 12 }}>
                  {expandedMission ? (
                    <>
                      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                        <div style={styles.previewBox}>
                          <div style={styles.subtleText}>Control Tower details</div>
                          <div style={{ marginTop: 6, fontSize: 13, color: "#cbd5f5", lineHeight: 1.55 }}>{expandedMissionSummaryReason}</div>
                          <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" as const }}><span style={styles.badge}>{expandedControlTowerAutonomyState}</span><span style={styles.badge}>{expandedRetryRemaining} retry left</span></div>
                        </div>
                        <div style={styles.previewBox}>
                          <div style={styles.subtleText}>Assumptions</div>
                          <div style={{ marginTop: 6, fontSize: 13, color: "#cbd5f5", lineHeight: 1.55 }}>{expandedActiveAssumptionCount} active of {expandedAssumptionCount} total. Derived only and mission-local.</div>
                          <div style={{ marginTop: 8, display: "grid", gap: 6 }}>{expandedVisibleAssumptions.length ? expandedVisibleAssumptions.map((assumption) => <div key={assumption.assumption_id} style={{ fontSize: 12, color: "#e2e8f0" }}>{assumption.text}</div>) : <div style={styles.subtleText}>No assumptions are visible yet.</div>}</div>
                        </div>
                        <div style={styles.previewBox}>
                          <div style={styles.subtleText}>Mirror / runner</div>
                          <div style={{ marginTop: 6, fontSize: 13, color: "#cbd5f5", lineHeight: 1.55 }}>{getRecordString(expandedRunnerReturn, "summary") || "No helper return is linked to this mission yet."}</div>
                          <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>{mirrorDoorTest.available ? `${mirrorDoorBlocked} blocked, ${mirrorDoorAccepted} accepted, ${mirrorDoorUnexpected} unexpected mirror-door cases` : "Mirror-door summary not available."}</div>
                        </div>
                        <div style={styles.previewBox}>
                          <div style={styles.subtleText}>Latest role activity</div>
                          <div style={{ marginTop: 6, fontSize: 13, color: "#cbd5f5", lineHeight: 1.55 }}>
                            {expandedLatestRoleActivity?.role && expandedLatestRoleActivity?.summary
                              ? `${expandedLatestRoleActivity.role} -> ${expandedLatestRoleActivity.summary}`
                              : getRecordString(expandedLatestAgentRun, "summary") || "No explicit role invocation has been recorded yet."}
                          </div>
                          <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                            {expandedLatestRoleActivity?.created_at || getRecordString(expandedLatestAgentRun, "created_at") || "Awaiting explicit invocation"}
                          </div>
                        </div>
                      </div>
                      {!isFocused ? (
                        <div style={{ ...styles.previewBox, marginTop: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Focused mission tools stay separate</div>
                          <div style={{ marginTop: 6, ...styles.subtleText }}>This card can stay expanded without changing the focused mission. Use Focus if you want the main mission console to follow this card.</div>
                        </div>
                      ) : null}
                      {isFocused && shouldShowReturnToBase ? (
                        <div style={{ ...styles.previewBox, borderColor: "rgba(251,191,36,0.35)", background: "rgba(120,53,15,0.16)", marginTop: 0 }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: "#fde68a" }}>Returned to base options</div>
                          <div style={{ marginTop: 8, display: "grid", gap: 8 }}>{returnToBaseOptions.map((option) => <button key={option.key} type="button" onClick={() => void runReturnToBaseOption(option.key)} style={{ ...styles.secondaryButton, textAlign: "left" }}>{option.label}</button>)}</div>
                          {returnToBaseCountdown != null ? <div style={{ marginTop: 8, ...styles.subtleText }}>Option 1 auto-runs in {returnToBaseCountdown}s.</div> : null}
                        </div>
                      ) : null}
                    </>
                  ) : <div style={styles.previewBox}>Loading mission details...</div>}
                </div>
              ) : null}
            </motion.div>
          );
        }) : <div style={styles.recordCard}>No missions are in the main feed right now. Hidden items remain retrievable below.</div>}
      </div>

      {showArchiveCandidates ? <div style={{ ...styles.recordCard, marginTop: 16 }}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Archive candidates</div><div style={styles.subtleText}>Dismissed or quiet missions stay here with their data intact.</div></div></div><div style={{ marginTop: 12, display: "grid", gap: 8 }}>{archiveFeedGroups.length ? archiveFeedGroups.map((group) => <div key={`archive-${group.group_key}`} style={styles.previewBox}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>{group.primary.objective || group.primary.mission_id}</div><div style={styles.subtleText}>{missionFeedSummary(group.primary)}</div></div><button type="button" onClick={() => restoreDismissedMission(group.primary.mission_id)} style={styles.secondaryButton}>View</button></div></div>) : <div style={styles.subtleText}>No archive candidates are hidden.</div>}</div></div> : null}
      {showParkedMissions ? <div style={{ ...styles.recordCard, marginTop: 16 }}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Parked missions</div><div style={styles.subtleText}>Parked missions are quiet, retrievable, and never deleted.</div></div></div><div style={{ marginTop: 12, display: "grid", gap: 8 }}>{parkedFeedGroups.length ? parkedFeedGroups.map((group) => <div key={`parked-${group.group_key}`} style={styles.previewBox}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>{group.primary.objective || group.primary.mission_id}</div><div style={styles.subtleText}>{group.primary.operator_posture_reason || missionFeedSummary(group.primary)}</div></div><button type="button" onClick={() => void setMissionParking("active", group.primary.mission_id)} style={styles.secondaryButton}>Resume</button></div></div>) : <div style={styles.subtleText}>No parked missions are hidden.</div>}</div></div> : null}
      {showDuplicateMissions ? <div style={{ ...styles.recordCard, marginTop: 16 }}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Duplicates</div><div style={styles.subtleText}>Collapsed duplicates stay grouped here so the main feed stays quiet.</div></div></div><div style={{ marginTop: 12, display: "grid", gap: 8 }}>{duplicateFeedGroups.length ? duplicateFeedGroups.map((group) => <div key={`duplicate-${group.group_key}`} style={styles.previewBox}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>{group.primary.objective || group.primary.mission_id}</div><div style={styles.subtleText}>{group.duplicate_count} related mission{group.duplicate_count === 1 ? "" : "s"}</div></div><button type="button" onClick={() => restoreDismissedMission(group.primary.mission_id)} style={styles.secondaryButton}>View</button></div></div>) : <div style={styles.subtleText}>No duplicate groups are hidden.</div>}</div></div> : null}
    </div>
  );

  const renderMissionShell = () => (
    <>
      <div style={styles.panel}>
        <div style={styles.sectionTitleRow}>
          <div>
            <h2 style={styles.sectionTitle}>Operator Shell</h2>
            <div style={styles.sectionSubtitle}>One input, four gauges, one result line, one next step.</div>
          </div>
        </div>

        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
          {[
            ["Mission State", missionStateGauge, selectedMission?.objective || "No focused mission yet."],
            ["Autonomy State", autonomyGauge, selectedMission ? compactLabel(controlTowerAutonomyState, "Ready") : "Awaiting mission focus."],
            ["Confidence", confidenceGauge, `${missionSummaryConfidence} · ${confidenceTrend}`],
            ["Queue Pressure", queuePressure, `${queueSummary.total_queued ?? expeditions.length} queued across ${expeditions.length} missions`],
          ].map(([label, value, detail]) => (
            <div key={label} style={{ ...styles.statusCard, ...statusStripToneStyles[toneForGauge(String(value))] }}>
              <div style={styles.statusLabel}>{label}</div>
              <div style={styles.statusValue}>{value}</div>
              <div style={styles.statusDetail}>{detail}</div>
            </div>
          ))}
        </div>

        {systemSignalsVisible ? (
          <div style={{ ...styles.recordCard, marginTop: 16, borderColor: "rgba(251,191,36,0.32)", background: "rgba(15,23,42,0.82)" }}>
            <div style={styles.recordMetaRow}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#f8fafc" }}>System Signals</div>
                <div style={styles.subtleText}>Compact nanny recommendations. Visible only when the system needs attention.</div>
              </div>
              <span style={{ ...styles.badge, ...styles.badgeWarn }}>{systemSignals.length} active</span>
            </div>

            <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
              {systemSignals.map((signal) => (
                <div key={signal.id} style={{ ...styles.previewBox, borderColor: signal.severity === "bad" ? "rgba(251,113,133,0.28)" : "rgba(251,191,36,0.28)" }}>
                  <div style={styles.recordMetaRow}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 800, color: signal.severity === "bad" ? "#fecdd3" : "#fde68a" }}>
                        {signal.level === "issue" ? "SYSTEM ISSUE" : "SYSTEM SIGNAL"}
                      </div>
                      <div style={{ marginTop: 4, fontSize: 16, fontWeight: 700, color: "#f8fafc" }}>{signal.title}</div>
                    </div>
                    <span style={{ ...styles.badge, ...(signal.severity === "bad" ? styles.badgeBad : styles.badgeWarn) }}>recommend</span>
                  </div>
                  <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>Cause</div>
                  <div style={{ marginTop: 4, fontSize: 13, color: "#cbd5f5", lineHeight: 1.5 }}>{signal.cause}</div>
                  <div style={{ marginTop: 10 }}>
                    <button type="button" onClick={() => handleSystemSignalAction(signal)} style={styles.secondaryButton}>
                      {signal.action_label}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div style={{ ...styles.composerCard, marginTop: 16 }}>
          <div style={styles.recordMetaRow}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800, color: "#fef3c7" }}>Mission Composer</div>
              <div style={styles.subtleText}>
                {selectedMissionId
                  ? selectedMissionIsParked
                    ? `Focused mission: ${selectedMissionId} (parked). Freeform input will not target it until you explicitly resume it.`
                    : `Focused mission: ${selectedMissionId}`
                  : "No mission selected. New mission drafts start here."}
              </div>
            </div>
            <span style={{ ...styles.badge, ...styles.badgeOutline }}>{composerPrimaryLabel}</span>
          </div>

          <textarea
            id="operator-intent"
            value={unifiedIntentText}
            onChange={(event) => setUnifiedIntentDraft(event.target.value)}
            placeholder="What do you want to try?"
            autoComplete="off"
            style={{ ...styles.composerTextarea, marginTop: 14 }}
          />

          <div style={{ ...styles.previewBox, marginTop: 14 }}>
            <div style={styles.subtleText}>I think you want to:</div>
            <div style={{ marginTop: 6, fontSize: 18, fontWeight: 800, color: "#f8fafc", lineHeight: 1.35 }}>
              {composerInterpretation}
            </div>

            <div style={{ marginTop: 12, display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
              <div>
                <div style={styles.subtleText}>Target</div>
                <div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: "#fde68a" }}>{composerTargetLabel}</div>
              </div>
              <div>
                <div style={styles.subtleText}>Mode</div>
                <div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: "#fde68a" }}>{composerModeLabel}</div>
              </div>
            </div>

            <details style={{ ...styles.recordCard, marginTop: 12, padding: 12 }}>
              <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Details</summary>
              <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
                <div style={styles.subtleText}>role: {composerRole}</div>
                <div style={styles.subtleText}>mode: {activeTranslationPreview?.recommended_mode || composerModeLabel.toLowerCase()}</div>
                <div style={styles.subtleText}>scope: {composerScope}</div>
                <div style={{ ...styles.subtleText, whiteSpace: "pre-wrap" as const }}>
                  notes: {composerNotes.join(" ")}
                </div>
                <div style={{ fontSize: 12, color: "#cbd5f5", lineHeight: 1.55, whiteSpace: "pre-wrap" as const }}>
                  {composerInstruction || "No translated instruction yet."}
                </div>
              </div>
            </details>
          </div>

          <div style={{ ...styles.previewBox, marginTop: 14 }}>
            <div style={styles.subtleText}>Result</div>
            <div style={{ ...composerResultToneStyle, marginTop: 6, fontSize: 14, fontWeight: 700, lineHeight: 1.45 }}>
              {shellResultLine}
            </div>
          </div>

          <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-start" }}>
            <motion.button
              type="button"
              onClick={() => void submitMissionComposer()}
              disabled={!composerCanSubmit}
              style={{ ...styles.refreshButton, padding: "12px 18px", fontSize: 14, opacity: composerCanSubmit ? 1 : 0.6 }}
              whileHover={{ scale: composerCanSubmit ? 1.02 : 1 }}
              whileTap={{ scale: composerCanSubmit ? 0.98 : 1 }}
            >
              {missionSaving ? missionActionLabel || `${composerPrimaryLabel}...` : composerPrimaryLabel}
            </motion.button>
          </div>
        </div>
      </div>
      {renderMissionFeed()}
      {false ? <div id="expeditions" style={styles.gridSplit}>
        <div style={styles.panel}>
          <div style={styles.sectionTitleRow}>
            <div>
              <h2 style={styles.sectionTitle}>Mission Queue</h2>
              <div style={styles.sectionSubtitle}>Compact queue view tuned for rapid mission triage and focus selection.</div>
            </div>
            <div style={styles.pillRow}>
              <span style={{ ...styles.badge, ...styles.badgeGood }}>{visibleExpeditions.groups.length} groups</span>
              <button type="button" onClick={() => setShowDuplicateMissions((prev) => !prev)} style={{ ...styles.badge, border: "1px solid rgba(192,132,252,0.25)", background: showDuplicateMissions ? "rgba(124,58,237,0.24)" : "rgba(15,23,42,0.9)", color: "#e2e8f0", cursor: "pointer" }}>
                {showDuplicateMissions ? "Expanded duplicates" : "Collapse duplicates"}
              </button>
            </div>
          </div>

          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", marginBottom: 16 }}>
            {[["Queued", queueSummary.total_queued ?? expeditions.length], ["Blocked", queueSummary.blocked ?? 0], ["Parked", queueSummary.parked ?? 0], ["Duplicates", queueSummary.duplicate_candidates ?? 0], ["Review", queueSummary.review_ready ?? 0], ["Archive", queueSummary.archive_close_candidates ?? 0]].map(([label, value]) => (
              <div key={label} style={styles.previewBox}>
                <div style={styles.subtleText}>{label}</div>
                <div style={{ marginTop: 4, fontSize: 18, fontWeight: 700, color: "#f8fafc" }}>{value as number}</div>
              </div>
            ))}
          </div>

          <div style={styles.expeditionList}>
            {visibleExpeditions.groups.length ? visibleExpeditions.groups.map((group) => {
              const expedition = group.primary;
              const groupSelected = group.items.some((item) => item.mission_id === selectedMissionId);
              return (
                <div key={group.group_key} style={{ display: "flex", flexDirection: "column" as const, gap: 8 }}>
                  <button type="button" onClick={() => focusMission(expedition.mission_id, expedition.summary || expedition.objective || expedition.mission_id)} style={{ ...styles.recordCard, textAlign: "left", cursor: "pointer", borderColor: groupSelected ? "rgba(251,191,36,0.42)" : "rgba(192,132,252,0.2)", background: groupSelected ? "rgba(76,29,149,0.28)" : "rgba(2,6,23,0.55)" }}>
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>{expedition.objective || expedition.mission_id}</div>
                        <div style={styles.subtleText}>{expedition.mission_id}</div>
                      </div>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const, justifyContent: "flex-end" }}>
                        <span style={styles.badge}>{expedition.status_badge}</span>
                        <span style={styles.badge}>{expedition.triage_bucket || "active"}</span>
                        {group.duplicate_count > 1 ? <span style={{ ...styles.badge, ...styles.badgeOutline }}>{group.duplicate_count} similar</span> : null}
                      </div>
                    </div>
                    <div style={{ marginTop: 8, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>{expedition.summary || expedition.operator_posture_reason || "No compressed mission summary yet."}</div>
                  </button>
                  {showDuplicateMissions && group.items.length > 1 ? (
                    <div style={{ marginLeft: 14, paddingLeft: 12, borderLeft: "1px solid rgba(168,85,247,0.18)", display: "flex", flexDirection: "column" as const, gap: 8 }}>
                      {group.items.slice(1).map((item) => (
                        <button key={item.mission_id} type="button" onClick={() => focusMission(item.mission_id, item.summary || item.objective || item.mission_id)} style={{ ...styles.recordCard, textAlign: "left", cursor: "pointer", padding: 12 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>{item.mission_id}</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{item.objective}</div>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            }) : <div style={styles.recordCard}>No expeditions exist yet. Use the top input and confirm `Start mission`.</div>}
          </div>
        </div>

        <div style={styles.panel}>
          {selectedMission ? (
            <div style={styles.stack}>
              <div style={styles.recordCard}>
                <div style={styles.recordMetaRow}>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: "#f8fafc" }}>{selectedMission!.objective || selectedMission!.mission_id}</div>
                    <div style={styles.subtleText}>{selectedMission!.mission_id} · {missionSummaryLifecycleState}</div>
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const }}>
                    <span style={{ ...styles.badge, ...styles.badgeGood }}>{missionStateGauge}</span>
                    <span style={styles.badge}>{autonomyGauge}</span>
                    <span style={styles.badge}>{confidenceGauge}</span>
                  </div>
                </div>

                <div style={{ marginTop: 12, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                  <div style={styles.previewBox}>
                    <div style={styles.subtleText}>What the system thinks you mean</div>
                    <div style={{ marginTop: 6, fontSize: 13, color: "#cbd5f5", lineHeight: 1.55 }}>{missionSummary?.latest_summary || missionSummary?.summary || latestMeaningfulSummary}</div>
                  </div>
                  <div style={styles.previewBox}>
                    <div style={styles.subtleText}>One next action</div>
                    <div style={{ marginTop: 6, fontSize: 13, color: "#f8fafc", lineHeight: 1.55 }}>{missionSummaryNextStep}</div>
                  </div>
                  <div style={styles.previewBox}>
                    <div style={styles.subtleText}>Blocker classification</div>
                    <div style={{ marginTop: 6, fontSize: 16, fontWeight: 700, color: blockerType === "HUMAN" ? "#fde68a" : blockerType === "SYSTEM" ? "#bfdbfe" : "#f9a8d4" }}>{blockerType}</div>
                    <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>{missionSummaryReason}</div>
                  </div>
                </div>
              </div>

              <div style={styles.recordCard}>
                <div style={styles.recordMetaRow}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: "#f8fafc" }}>Resolve Blocker</div>
                    <div style={styles.subtleText}>Human asks for an answer, system asks for a safe retry, junk gets ignored without deletion.</div>
                  </div>
                  <span style={{ ...styles.badge, ...(blockerType === "HUMAN" ? styles.badgeWarn : blockerType === "JUNK" ? styles.badgeOutline : styles.badgeGood) }}>{blockerType}</span>
                </div>
                <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" as const }}>
                  <motion.button type="button" onClick={() => void sendMissionChat(unifiedIntentText || missionSummaryNextAnswer, "Answer")} style={styles.secondaryButton} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>Answer</motion.button>
                  <motion.button type="button" onClick={() => void runReturnToBaseOption("retry")} style={styles.secondaryButton} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>Assume and continue</motion.button>
                  <motion.button type="button" onClick={() => void runLoggedControlTowerIntervention("mark_archive_candidate", { label: "Ignoring junk", reason: "operator classified blocker as junk" })} style={styles.secondaryButton} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>Ignore (junk)</motion.button>
                </div>
              </div>
              {shouldShowReturnToBase ? (
                <div style={{ ...styles.recordCard, borderColor: "rgba(251,191,36,0.4)", background: "rgba(120,53,15,0.16)" }}>
                  <div style={{ fontSize: 18, fontWeight: 800, color: "#fde68a" }}>MISSION STATUS: RETURNED TO BASE</div>
                  <div style={{ marginTop: 8, fontSize: 13, color: "#fde68a", lineHeight: 1.55 }}>We found 3 ways forward. Default action is Option 1 after a visible delay and an explicit log entry.</div>
                  <div style={{ marginTop: 12, display: "grid", gap: 10 }}>
                    {returnToBaseOptions.map((option) => (
                      <button key={option.key} type="button" onClick={() => void runReturnToBaseOption(option.key)} style={{ ...styles.previewBox, textAlign: "left", cursor: "pointer" }}>
                        <div style={styles.recordMetaRow}>
                          <div style={{ fontSize: 14, fontWeight: 700, color: "#f8fafc" }}>{option.label}</div>
                          <span style={{ ...styles.badge, ...(option.confidence === "HIGH" ? styles.badgeGood : option.confidence === "MEDIUM" ? styles.badgeWarn : styles.badgeOutline) }}>{option.confidence}</span>
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5" }}>{option.detail}</div>
                      </button>
                    ))}
                  </div>
                  <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" as const }}>
                    <motion.button type="button" onClick={() => void runReturnToBaseOption("retry")} style={styles.secondaryButton} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>New solution refresh</motion.button>
                    <motion.button type="button" onClick={() => void setMissionParking("parked")} style={styles.secondaryButton} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>Kill mission (park)</motion.button>
                    <motion.button type="button" onClick={() => document.getElementById("operator-intent")?.focus()} style={styles.secondaryButton} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>Add input (optional)</motion.button>
                    {returnToBaseCountdown != null ? <span style={{ ...styles.badge, ...styles.badgeWarn }}>Option 1 in {returnToBaseCountdown}s</span> : null}
                  </div>
                  <details style={{ marginTop: 12 }}>
                    <summary style={{ cursor: "pointer", color: "#fde68a", fontSize: 13, fontWeight: 600 }}>Why these options</summary>
                    <div style={{ ...styles.previewBox, marginTop: 10, fontSize: 12, color: "#fde68a", lineHeight: 1.55 }}>
                      Missing artifact and blocker patterns pushed the mission back to a bounded retry posture. Assumptions allow a safe refresh, scope can narrow to partial output, and an alternate path is offered because the current route is not progressing.
                    </div>
                  </details>
                </div>
              ) : null}

              {(triageMode || queuePressure === "OVERLOADED") ? (
                <div style={styles.recordCard}>
                  <div style={styles.recordMetaRow}>
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: "#f8fafc" }}>Queue Triage</div>
                      <div style={styles.subtleText}>No deletion. Collapse duplicates, mark archive candidates, park blocked work, and keep active missions visible.</div>
                    </div>
                    <span style={{ ...styles.badge, ...styles.badgeWarn }}>{queuePressure}</span>
                  </div>
                  <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
                    <div style={styles.previewBox}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Duplicates</div>
                      {duplicateTriageGroups.length ? duplicateTriageGroups.slice(0, 3).map((group) => <div key={`dup-${group.group_key}`} style={{ ...styles.recordCard, marginTop: 8 }}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>{group.primary.objective || group.primary.mission_id}</div><div style={styles.subtleText}>{group.duplicate_count} related missions</div></div><button type="button" onClick={() => { setShowDuplicateMissions(false); focusMission(group.primary.mission_id); }} style={styles.secondaryButton}>Collapse duplicates</button></div></div>) : <div style={{ marginTop: 8, ...styles.subtleText }}>No duplicate groups need action.</div>}
                    </div>
                    <div style={styles.previewBox}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Archive candidates</div>
                      {archiveCandidates.length ? archiveCandidates.slice(0, 3).map((mission) => <div key={`archive-${mission.mission_id}`} style={{ ...styles.recordCard, marginTop: 8 }}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>{mission.objective || mission.mission_id}</div><div style={styles.subtleText}>{mission.queue_action_reason || mission.summary}</div></div><button type="button" onClick={() => void runLoggedControlTowerIntervention("mark_archive_candidate", { label: "Marking archive candidate", reason: mission.queue_action_reason || "queue triage archive candidate" }, mission.mission_id)} style={styles.secondaryButton}>Mark archive candidate</button></div></div>) : <div style={{ marginTop: 8, ...styles.subtleText }}>No archive candidates are waiting.</div>}
                    </div>
                    <div style={styles.previewBox}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Blocked</div>
                      {blockedQueueItems.length ? blockedQueueItems.slice(0, 3).map((mission) => <div key={`blocked-${mission.mission_id}`} style={{ ...styles.recordCard, marginTop: 8 }}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>{mission.objective || mission.mission_id}</div><div style={styles.subtleText}>{mission.operator_posture_reason || mission.summary}</div></div><button type="button" onClick={() => void setMissionParking("parked", mission.mission_id)} style={styles.secondaryButton}>Park blocked</button></div></div>) : <div style={{ marginTop: 8, ...styles.subtleText }}>No blocked missions need parking.</div>}
                    </div>
                    <div style={styles.previewBox}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#f8fafc" }}>Active</div>
                      {activeQueueItems.length ? activeQueueItems.slice(0, 3).map((mission) => <div key={`active-${mission.mission_id}`} style={{ ...styles.recordCard, marginTop: 8 }}><div style={styles.recordMetaRow}><div><div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>{mission.objective || mission.mission_id}</div><div style={styles.subtleText}>{mission.summary}</div></div><button type="button" onClick={() => focusMission(mission.mission_id)} style={styles.secondaryButton}>Keep active</button></div></div>) : <div style={{ marginTop: 8, ...styles.subtleText }}>No active missions need attention.</div>}
                    </div>
                  </div>
                </div>
              ) : null}

              <details style={styles.recordCard}><summary style={{ cursor: "pointer", fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Control Tower details</summary><div style={{ marginTop: 12, display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}><div style={styles.previewBox}><div style={styles.subtleText}>Autonomy</div><div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: "#f8fafc" }}>{controlTowerAutonomyState}</div></div><div style={styles.previewBox}><div style={styles.subtleText}>Retry budget</div><div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: "#f8fafc" }}>{controlTowerRetryRemaining} remaining</div></div><div style={styles.previewBox}><div style={styles.subtleText}>Attention reason</div><div style={{ marginTop: 4, fontSize: 12, color: "#cbd5f5" }}>{controlTowerSummary?.operator_attention_reason || missionSummaryReason}</div></div><div style={styles.previewBox}><div style={styles.subtleText}>Latest role activity</div><div style={{ marginTop: 4, fontSize: 12, color: "#cbd5f5" }}>{latestRoleActivityText}</div></div></div></details>
              <details style={styles.recordCard}><summary style={{ cursor: "pointer", fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Assumptions</summary><div style={{ marginTop: 12, display: "grid", gap: 8 }}><div style={{ ...styles.previewBox, fontSize: 12, color: "#cbd5f5" }}>{missionActiveAssumptionCount} active of {missionAssumptionCount} total. Derived only, mission-local only, never canonical truth.</div>{visibleMissionAssumptions.length ? visibleMissionAssumptions.map((assumption) => <div key={assumption.assumption_id} style={styles.recordCard}><div style={styles.recordMetaRow}><div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>{assumption.text}</div><div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const }}><span style={assumptionStatusBadgeStyle(assumption.status)}>{assumption.status}</span><span style={assumptionOperatorBadgeStyle(assumption.confirmation?.operator_status || "unreviewed")}>{assumption.confirmation?.operator_status || "unreviewed"}</span></div></div><div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>{assumption.reason}</div><div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" as const }}><button type="button" onClick={() => void reviewAssumption(assumption.assumption_id, "confirm")} style={styles.secondaryButton}>Accept</button><button type="button" onClick={() => void reviewAssumption(assumption.assumption_id, "reject")} style={styles.secondaryButton}>Reject</button></div></div>) : <div style={styles.subtleText}>No assumptions are visible yet.</div>}</div></details>
              <details style={styles.recordCard}><summary style={{ cursor: "pointer", fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Runner returns</summary><div style={{ marginTop: 12, display: "grid", gap: 10 }}><div style={styles.previewBox}><div style={styles.subtleText}>Latest helper return</div><div style={{ marginTop: 4, fontSize: 13, color: "#cbd5f5" }}>{getRecordString(latestRunnerReturn, "summary") || "No helper return is linked to this mission yet."}</div></div><button type="button" onClick={() => void syncRunnerReturns()} style={styles.secondaryButton}>Sync helper returns</button></div></details>
              <details style={styles.recordCard}><summary style={{ cursor: "pointer", fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Mirror</summary><div style={styles.previewBox}><div style={styles.subtleText}>Mirror-door summary</div><div style={{ marginTop: 4, fontSize: 13, color: "#cbd5f5" }}>{mirrorDoorTest.available ? `${mirrorDoorBlocked} blocked correctly, ${mirrorDoorAccepted} accepted, ${mirrorDoorUnexpected} unexpected` : "Mirror-door summary not available."}</div></div></details>
              <details style={styles.recordCard}><summary style={{ cursor: "pointer", fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Artifacts</summary><div style={{ marginTop: 12, display: "grid", gap: 8 }}>{selectedMissionArtifactRefs.length ? selectedMissionArtifactRefs.map((artifact, index) => <div key={`artifact-${index}`} style={styles.previewBox}><div style={{ fontSize: 12, color: "#cbd5f5", lineHeight: 1.5, whiteSpace: "pre-wrap" as const }}>{JSON.stringify(artifact, null, 2)}</div></div>) : <div style={styles.subtleText}>No mission artifacts have been indexed yet.</div>}</div></details>
              <details style={styles.recordCard}><summary style={{ cursor: "pointer", fontSize: 15, fontWeight: 700, color: "#f8fafc" }}>Workbench</summary><div style={styles.tabRow}>{selectedMissionFolders.map((folder) => <button key={folder.name} type="button" onClick={() => setWorkbenchFolder(folder.name)} style={{ ...styles.tabButton, ...(workbenchFolder === folder.name ? styles.tabButtonActive : null) }}>{folder.name} ({folder.file_count})</button>)}</div><div style={styles.scrollArea}>{workbenchFilesForFolder.length ? workbenchFilesForFolder.map((file) => <div key={file.path} style={styles.previewBox}><div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>{file.name}</div><div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{file.path}</div></div>) : <div style={styles.subtleText}>No files yet in {workbenchFolder}.</div>}</div></details>
            </div>
          ) : <div style={styles.recordCard}>Select a mission from the queue or use the top input to start a new one.</div>}
        </div>
      </div> : null}
    </>
  );

  void [
    Activity,
    Database,
    CircleDot,
    AlertTriangle,
    CheckCircle2,
    FileText,
    viewMode,
    calibrationAxes,
    setCalibrationAxes,
    selectedRecord,
    packets,
    selectedPacket,
    queueCounts,
    gateOpen,
    returnAll,
    nanny,
    dispatchCounts,
    supportActivity,
    mirrorDoorTest,
    storageOverview,
    compactorLastRun,
    storageHotspots,
    helperLaneSummary,
    helperTone,
    dispatchTone,
    nannyTone,
    returnAllTone,
    mirrorDoorBlocked,
    mirrorDoorAccepted,
    mirrorDoorUnexpected,
    mirrorDoorHealth,
    selectedDraftPath,
    missionParkingStatus,
    openMissionsView,
    openDiagnosticsView,
    openReviewPreview,
    setMissionParking,
    repeatedItemCount,
    attentionItems,
    blockedWaitingCount,
    hermesRuns,
    petitionDrafts,
    missionChatText,
    setMissionInputDraft,
    setMissionChatDraft,
    setTranslatorDraft,
    selectedMissionInputs,
    promptTranslationCount,
    runnerReturnCount,
    missionAssumptionChanges,
    missionAssumptionsLastUpdated,
    hiddenMissionAssumptions,
    latestPacketSummary,
    missionSummaryOperatingStatus,
    missionSummaryTriageBucket,
    missionSummaryCrewStatus,
    missionSummaryExpeditionActivity,
    missionSummaryParkedAt,
    missionSummaryBeliefs,
    missionSummaryConfirmedFacts,
    missionSummaryAssumptions,
    missionSummaryDeferredQuestions,
    missionSummaryNeeds,
    missionSummaryQuickReplies,
    missionSummaryWakeHint,
    controlTowerAutonomyTone,
    recentControlInterventions,
    unsupportedControlActions,
    expeditionStatusTone,
    refreshAssumptions,
    copyTranslatedInstruction,
    stageTranslatedInstructionForMissionInput,
    stageTranslatedInstructionForChat,
    stageProposedMissionDraft,
    discardPromptTranslation,
    runMissionQuickReply,
    runControlTowerAction,
  ];

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={styles.pillRow}>
            <span style={{ ...styles.pill, ...styles.badgePrimary }}>Spinetop live dashboard</span>
            <span style={{ ...styles.pill, ...styles.badgeOutline }}>
              workspace: {data.workspace_id || "shared-coordination"}
            </span>
            <span style={{ ...styles.pill, ...styles.badgeWarn }}>refresh: every 5s</span>
          </div>

          <div style={styles.headerRow}>
            <div>
              <h1 style={styles.headline}>Mission Console</h1>
              <p style={styles.subtext}>
                Backup mission view for active expeditions, the focused mission, and the mission-local workbench.
              </p>
            </div>

            <div style={styles.refreshRow}>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Last refresh: {lastRefresh}</div>
              <button onClick={() => void load({ preserveScroll: true })} disabled={loading} style={styles.refreshButton}>
                <RefreshCw size={16} />
                Refresh
              </button>
            </div>
          </div>

          {viewMode === "diagnostics" && errorText ? <div style={styles.alert}>{errorText}</div> : null}
          {viewMode === "diagnostics" && uiNotice ? (
            <motion.div
              key={`${uiNotice.title}-${uiNotice.detail}`}
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              style={{
                ...styles.alert,
                borderColor:
                  uiNotice.tone === "good"
                    ? "rgba(52,211,153,0.38)"
                    : uiNotice.tone === "bad"
                      ? "rgba(251,113,133,0.38)"
                      : uiNotice.tone === "watch"
                        ? "rgba(251,191,36,0.38)"
                        : "rgba(96,165,250,0.38)",
                background:
                  uiNotice.tone === "good"
                    ? "rgba(6,78,59,0.22)"
                    : uiNotice.tone === "bad"
                      ? "rgba(127,29,29,0.22)"
                      : uiNotice.tone === "watch"
                        ? "rgba(120,53,15,0.22)"
                        : "rgba(30,41,59,0.22)",
                color:
                  uiNotice.tone === "good"
                    ? "#bbf7d0"
                    : uiNotice.tone === "bad"
                      ? "#fecdd3"
                      : uiNotice.tone === "watch"
                        ? "#fde68a"
                        : "#bfdbfe",
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 700 }}>{uiNotice.title}</div>
              <div style={{ marginTop: 4 }}>{uiNotice.detail}</div>
            </motion.div>
          ) : null}
        </div>

        {renderMissionShell()}

        {viewMode === "diagnostics" ? (
          <>
            <div style={styles.panel}>
              <div style={styles.sectionTitleRow}>
                <div>
                  <h2 style={styles.sectionTitle}>Diagnostics</h2>
                  <div style={styles.sectionSubtitle}>
                    Secondary telemetry, storage, helper lanes, and mirror-door health stay available here when operators need them.
                  </div>
                </div>
                <span style={{ ...styles.badge, ...styles.badgeGood }}>diagnostics</span>
              </div>
              <div style={styles.statusStrip}>
                {statusStripCard(
                  "Return All",
                  returnAll.enabled ? "ENABLED" : "off",
                  returnAll.enabled
                    ? `issued by ${returnAll.issued_by || "operator"}${returnAll.issued_at ? ` at ${returnAll.issued_at}` : ""}`
                    : "No active return-all gate is recorded.",
                  returnAllTone
                )}
                {statusStripCard(
                  "Nanny",
                  `${nanny.temperature || "unknown"} / cooldown ${nanny.global_cooldown_seconds ?? 0}s`,
                  `burst ${nanny.burst_score ?? 0}, error ${nanny.error_score ?? 0}`,
                  nannyTone
                )}
                {statusStripCard(
                  "Dispatch",
                  `${dispatchCounts.pending ?? 0} pending`,
                  `${dispatchCounts.approved ?? 0} approved, ${dispatchCounts.deferred ?? 0} deferred, ${dispatchCounts.rejected ?? 0} rejected, total ${dispatchCounts.total ?? 0}`,
                  dispatchTone
                )}
                {statusStripCard(
                  "Helpers",
                  `${supportActivity.total ?? 0} helpers`,
                  helperLaneSummary,
                  helperTone
                )}
                {helper2bRuntime.available ? statusStripCard(
                  "Expeditioner",
                  helper2bRuntime.enabled ? "enabled" : "configured",
                  helper2bRuntime.enabled
                    ? `${helper2bRuntime.provider || "local"} ${helper2bRuntime.model || helper2bRuntime.default_model_key || "model"}`
                    : "scripted seam; structured receipts stay operator-visible",
                  helper2bTone
                ) : null}
                {statusStripCard(
                  "Mirror-door",
                  mirrorDoorHealth,
                  mirrorDoorTest.available
                    ? `${mirrorDoorTest.total ?? 0} cases, ${mirrorDoorBlocked} blocked, ${mirrorDoorAccepted} accepted${mirrorDoorUnexpected ? `, ${mirrorDoorUnexpected} unexpected` : ""}`
                    : "Mirror-door summary not available.",
                  mirrorDoorHealth === "healthy" ? "good" : mirrorDoorHealth === "attention" ? "watch" : "off"
                )}
              </div>
            </div>

            <div style={styles.metrics}>
          {metricCard("Events", (data.events_recent || []).length, "live flow", Activity)}
          {metricCard("Sessions", data.honcho_sessions_total ?? "ï¿½", "active memory links", Database)}
          {metricCard("Expeditions", expeditions.length, "mission containers", ClipboardList)}
          {metricCard("Sentinel Runs", hermesRuns.filter((item) => item.ok).length, "saved run JSON artifacts", FileText)}
          {metricCard("Drafts", petitionDrafts.filter((item) => item.ok).length, "memory/drafts records", ClipboardList)}
          {metricCard(
            "Packet Stage",
            selectedPacket ? `${selectedPacket.stage + 1}/4` : "ï¿½",
            selectedPacket?.recordName || "no packet selected",
            CircleDot
          )}
        </div>

        <div style={styles.panel}>
          <div style={styles.sectionTitleRow}>
            <div>
              <h2 style={styles.sectionTitle}>Storage visibility</h2>
              <div style={styles.sectionSubtitle}>
                Read-only disk usage from <span style={styles.mono}>memory/</span> and <span style={styles.mono}>logs/</span>, including governed collective records that made it through the door.
              </div>
            </div>
            <span style={{ ...styles.badge, ...(storageOverview.available ? styles.badgeGood : styles.badgeWarn) }}>
              {storageOverview.available ? "measured" : "unavailable"}
            </span>
          </div>

          <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
            {[
              [
                "Active footprint",
                storageOverview.footprints.active.total_bytes_label,
                `${storageOverview.footprints.active.total_files} files across ${storageOverview.footprints.active.group_names.length} areas`,
              ],
              [
                "Archive footprint",
                storageOverview.footprints.archive.total_bytes_label,
                `${storageOverview.footprints.archive.total_files} files across ${storageOverview.footprints.archive.group_names.length} areas`,
              ],
              [
                "Collective door admitted",
                storageOverview.collective_door.admitted_bytes_label,
                `${storageOverview.collective_door.admitted_count} admitted, ${storageOverview.collective_door.blocked_count} blocked`,
              ],
              [
                "Compactor history",
                storageOverview.footprints.compaction.total_bytes_label,
                `${compactorLastRun.groups_compacted ?? 0} groups compacted in the last run`,
              ],
            ].map(([label, value, detail]) => (
              <div key={label} style={{ ...styles.recordCard, padding: 12 }}>
                <div style={styles.subtleText}>{label}</div>
                <div style={{ marginTop: 6, fontSize: 24, fontWeight: 600, color: "#f5d0fe" }}>{value as string}</div>
                <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8" }}>{detail as string}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10, fontSize: 12, color: "#94a3b8" }}>
            observed total {storageOverview.footprints.all_observed_bytes} across {storageOverview.areas.length} measured areas
          </div>

          <div style={{ marginTop: 16, display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
            <div>
              <div style={{ marginBottom: 10, fontSize: 16, fontWeight: 600, color: "#f5d0fe" }}>Storage hotspots</div>
              <div style={styles.stack}>
                {storageHotspots.length ? (
                  storageHotspots.map((area) => {
                    const pressureTone =
                      area.pressure_label === "high"
                        ? styles.badgeBad
                        : area.pressure_label === "elevated"
                          ? styles.badgeWarn
                          : styles.badgeGood;

                    return (
                      <div key={area.name} style={styles.recordCard}>
                        <div style={styles.recordMetaRow}>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>{area.name}</div>
                            <div style={styles.subtleText}>{area.path}</div>
                          </div>
                          <span style={{ ...styles.badge, ...pressureTone }}>{area.pressure_label}</span>
                        </div>
                        <div style={{ marginTop: 10, display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}>
                          <div>
                            <div style={styles.subtleText}>bytes</div>
                            <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                              {area.total_bytes_label}
                            </div>
                          </div>
                          <div>
                            <div style={styles.subtleText}>files</div>
                            <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                              {area.file_count}
                            </div>
                          </div>
                          <div>
                            <div style={styles.subtleText}>freshness</div>
                            <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                              {formatAgeMinutes(area.newest_age_minutes)}
                            </div>
                          </div>
                        </div>
                        <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                          oldest {area.oldest_modified_at || "unknown"} | newest {area.newest_modified_at || "unknown"}
                        </div>
                        {area.largest_file ? (
                          <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5" }}>
                            largest <span style={styles.mono}>{area.largest_file.name}</span> ({area.largest_file.bytes_label})
                          </div>
                        ) : null}
                        {area.notes.length ? (
                          <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8 }}>
                            {area.notes.map((note) => (
                              <span key={`${area.name}-${note}`} style={styles.badge}>
                                {note}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    );
                  })
                ) : (
                  <div style={styles.recordCard}>No storage areas were measured yet.</div>
                )}
              </div>
            </div>

            <div>
              <div style={{ marginBottom: 10, fontSize: 16, fontWeight: 600, color: "#f5d0fe" }}>
                Governed collective footprint
              </div>
              <div style={styles.recordCard}>
                <div style={styles.recordMetaRow}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>memory/collective</div>
                    <div style={styles.subtleText}>admitted records are measured through the same governance gate used by the mirror door</div>
                  </div>
                  <span style={{ ...styles.badge, ...styles.badgeGood }}>
                    {Math.round((storageOverview.collective_door.admitted_ratio ?? 0) * 100)}% admitted
                  </span>
                </div>

                <div style={{ marginTop: 12, display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}>
                  <div>
                    <div style={styles.subtleText}>total bytes</div>
                    <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                      {storageOverview.collective_door.total_bytes_label}
                    </div>
                  </div>
                  <div>
                    <div style={styles.subtleText}>admitted bytes</div>
                    <div style={{ marginTop: 4, color: "#bbf7d0", fontSize: 13, fontWeight: 600 }}>
                      {storageOverview.collective_door.admitted_bytes_label}
                    </div>
                  </div>
                  <div>
                    <div style={styles.subtleText}>blocked bytes</div>
                    <div style={{ marginTop: 4, color: "#fecdd3", fontSize: 13, fontWeight: 600 }}>
                      {storageOverview.collective_door.blocked_bytes_label}
                    </div>
                  </div>
                  <div>
                    <div style={styles.subtleText}>legacy</div>
                    <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                      {storageOverview.collective_door.legacy_count}
                    </div>
                  </div>
                </div>

                <div style={styles.previewBox}>
                  <div style={styles.subtleText}>door reasons</div>
                  <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {Object.entries(storageOverview.collective_door.door_reasons || {}).length ? (
                      Object.entries(storageOverview.collective_door.door_reasons).map(([reason, count]) => (
                        <span key={reason} style={styles.badge}>
                          {reason}: {count}
                        </span>
                      ))
                    ) : (
                      <span style={styles.subtleText}>No gate rejections recorded.</span>
                    )}
                  </div>
                </div>

                <div style={{ marginTop: 12, fontSize: 12, color: "#94a3b8" }}>
                  path <span style={styles.mono}>{storageOverview.collective_door.path}</span> | files{" "}
                  {storageOverview.collective_door.total_files}
                </div>
              </div>

              <div style={{ ...styles.recordCard, marginTop: 16 }}>
                <div style={styles.recordMetaRow}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>Compactor state</div>
                    <div style={styles.subtleText}>latest run log and compaction pressure signals</div>
                  </div>
                  <span style={{ ...styles.badge, ...(compactorLastRun.ok ? styles.badgeGood : styles.badgeWarn) }}>
                    {compactorLastRun.ok ? "ok" : "unknown"}
                  </span>
                </div>
                <div style={{ marginTop: 10, display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}>
                  <div>
                    <div style={styles.subtleText}>groups scanned</div>
                    <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                      {compactorLastRun.groups_scanned ?? 0}
                    </div>
                  </div>
                  <div>
                    <div style={styles.subtleText}>groups compacted</div>
                    <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                      {compactorLastRun.groups_compacted ?? 0}
                    </div>
                  </div>
                  <div>
                    <div style={styles.subtleText}>records compacted</div>
                    <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                      {compactorLastRun.records_compacted ?? 0}
                    </div>
                  </div>
                  <div>
                    <div style={styles.subtleText}>records skipped</div>
                    <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                      {compactorLastRun.records_skipped ?? 0}
                    </div>
                  </div>
                </div>
                <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                  last run {compactorLastRun.timestamp || "unknown"}
                </div>
                <div style={{ marginTop: 8, fontSize: 12, color: "#cbd5f5" }}>
                  active footprint {storageOverview.footprints.active.total_bytes_label} across {storageOverview.footprints.active.total_files} files
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#cbd5f5" }}>
                  archive footprint {storageOverview.footprints.archive.total_bytes_label} across {storageOverview.footprints.archive.total_files} files
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#cbd5f5" }}>
                  compaction metadata {storageOverview.footprints.compaction.total_bytes_label}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div style={styles.gridSplit}>
          <div style={styles.panel}>
            <div style={{ marginBottom: 16, fontSize: 20, fontWeight: 600, color: "#f5d0fe" }}>
              Memory packet gate run
            </div>

            <div style={styles.portalArea}>
              <div style={{ position: "absolute", right: "4%", top: "34%", display: "none" }} />

              <div style={{ marginBottom: 20, fontSize: 12, color: "#f5d0fe" }}>
                <span style={{ ...styles.pill, ...styles.badgePrimary, marginRight: 8 }}>selected packet</span>
                <span
                  style={{
                    ...styles.pill,
                    border: "1px solid rgba(192,132,252,0.2)",
                    background: "rgba(2,6,23,0.4)",
                  }}
                >
                  {selectedPacket?.recordName || "none"}
                </span>
              </div>

              <div
                style={{
                  position: "relative",
                  height: 280,
                  overflow: "hidden",
                  borderRadius: 16,
                  border: "1px solid rgba(192,132,252,0.1)",
                  background: "rgba(2,6,23,0.2)",
                  marginBottom: 24,
                }}
              >
                {packets.slice(0, 18).map((packet, idx) => {
                  const top = 18 + (idx % 8) * 28;
                  const targetX = gateX[Math.min(packet.stage, 3)];
                  const isSelected = packet.recordName === selectedPacket?.recordName;

                  return (
                    <motion.button
                      key={packet.recordName}
                      type="button"
                      onClick={() => setSelectedRecord(packet.recordName)}
                      style={{
                        position: "absolute",
                        top,
                        left: `${targetX}%`,
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                      }}
                      animate={{
                        scale: isSelected ? [1, 1.12, 1] : [0.9, 1, 0.92],
                        rotate: packet.failed ? [0, -8, 8, -4, 0] : [0, -4, 4, 0],
                        opacity: packet.failed ? [0.7, 1, 0.8] : [0.75, 0.95, 0.8],
                      }}
                      transition={{
                        duration: 4 + (idx % 4) * 0.35,
                        repeat: Infinity,
                        ease: "easeInOut",
                      }}
                    >
                      <div
                        style={{
                          borderRadius: 12,
                          border: `1px solid ${isSelected ? "rgba(252,211,77,0.4)" : "rgba(192,132,252,0.2)"}`,
                          background: isSelected ? "rgba(252,211,77,0.2)" : "rgba(192,132,252,0.1)",
                          padding: "4px 8px",
                          fontSize: 18,
                          boxShadow: "0 8px 18px rgba(15,23,42,0.5)",
                        }}
                      >
                        {packet.failed ? "??" : "??"}
                      </div>
                    </motion.button>
                  );
                })}

                {gateLabels.map((gate, index) => (
                  <div
                    key={gate}
                    style={{
                      position: "absolute",
                      top: 0,
                      bottom: 0,
                      left: `${gateX[index]}%`,
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        top: 0,
                        height: "100%",
                        width: 4,
                        background: gateOpen[index] ? "rgba(52,211,153,0.35)" : "rgba(251,113,133,0.25)",
                      }}
                    />
                  </div>
                ))}
              </div>

              <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(180px,1fr))" }}>
                {gateLabels.map((label, index) => (
                  <div
                    key={label}
                    style={{
                      position: "relative",
                      borderRadius: 20,
                      border: "1px solid rgba(192,132,252,0.3)",
                      background: "rgba(15,23,42,0.8)",
                      padding: 16,
                      boxShadow: `0 0 ${8 + queueCounts[index] * 6}px rgba(217,70,239,${
                        0.08 + Math.min(queueCounts[index], 4) * 0.06
                      })`,
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        right: -8,
                        top: -8,
                        borderRadius: 999,
                        border: "1px solid rgba(252,211,77,0.3)",
                        background: "rgba(252,211,77,0.2)",
                        padding: "4px 10px",
                        fontSize: 10,
                        fontWeight: 600,
                        color: "#fde68a",
                      }}
                    >
                      Q {queueCounts[index]}
                    </div>
                    <div
                      style={{
                        position: "absolute",
                        left: -8,
                        top: -8,
                        borderRadius: 999,
                        border: `1px solid ${gateOpen[index] ? "rgba(52,211,153,0.3)" : "rgba(251,113,133,0.3)"}`,
                        background: gateOpen[index] ? "rgba(52,211,153,0.15)" : "rgba(251,113,133,0.15)",
                        padding: "4px 10px",
                        fontSize: 10,
                        fontWeight: 600,
                        color: gateOpen[index] ? "#bbf7d0" : "#fecdd3",
                      }}
                    >
                      {gateOpen[index] ? "OPEN" : "HOLD"}
                    </div>

                    <div style={{ fontSize: 16, fontWeight: 600, color: "#f5d0fe" }}>{label}</div>
                    <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                      {
                        [
                          "raw memory intake",
                          "review and candidate check",
                          "truth-layer approval",
                          "session-backed mirror",
                        ][index]
                      }
                    </div>

                    {selectedPacket?.stage === index ? (
                      <div
                        style={{
                          marginTop: 12,
                          borderRadius: 12,
                          border: "1px solid rgba(252,211,77,0.3)",
                          background: "rgba(252,211,77,0.1)",
                          padding: 10,
                          fontSize: 12,
                          color: "#fde68a",
                        }}
                      >
                        Selected packet is here.
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div style={styles.panel}>
              <div style={{ marginBottom: 16, fontSize: 20, fontWeight: 600, color: "#f5d0fe" }}>
                Topology Mindspace
              </div>
              <div
                style={{
                  position: "relative",
                  height: 240,
                  overflow: "hidden",
                  borderRadius: 16,
                  border: "1px solid rgba(192,132,252,0.2)",
                  background: "rgba(2,6,23,0.6)",
                }}
              >
                {(data.events_recent || []).slice(0, 16).map((event, index) => {
                  const stageMap = {
                    hermes_write: 0,
                    watcher_scan: 1,
                    promote: 1,
                    approve: 2,
                    honcho_bridge: 3,
                  } as const;
                  const stage = stageMap[event.event_type as keyof typeof stageMap] ?? 0;

                  const xPositions = [12, 38, 62, 86];
                  const y = 18 + (index % 6) * 32;
                  const isFailure = event.status === "error" || event.status === "skipped";

                  return (
                    <motion.div
                      key={`${event.record_name}-${event.timestamp}-${index}`}
                      style={{ position: "absolute", left: `${xPositions[stage]}%`, top: y }}
                      animate={{
                        scale: isFailure ? [0.8, 1.2, 0.8] : [0.8, 1.05, 0.84],
                        opacity: isFailure ? [0.3, 1, 0.3] : [0.25, 0.8, 0.25],
                        y: isFailure ? [0, -10, 8, 0] : [0, -4, 2, 0],
                      }}
                      transition={{ duration: 3 + index * 0.12, repeat: Infinity }}
                    >
                      <div
                        style={{
                          borderRadius: 999,
                          border: `1px solid ${isFailure ? "rgba(251,113,133,0.4)" : "rgba(192,132,252,0.3)"}`,
                          background: isFailure ? "rgba(251,113,133,0.15)" : "rgba(192,132,252,0.15)",
                          padding: "4px 10px",
                          fontSize: 11,
                          fontWeight: 600,
                          color: isFailure ? "#fecdd3" : "#f5d0fe",
                        }}
                      >
                        {event.event_type}
                      </div>
                    </motion.div>
                  );
                })}

                <div style={{ position: "absolute", left: 0, right: 0, bottom: 12, textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                  Hermes write spawns left ï¿½ watcher pulls inward ï¿½ bridge gets vacuumed into the portal ï¿½ failures flicker
                </div>
              </div>
            </div>

            <div style={styles.panel}>
              <div style={{ marginBottom: 16, fontSize: 20, fontWeight: 600, color: "#f5d0fe" }}>
                Packet timeline
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {["hermes_write", "promote", "approve", "honcho_bridge"].map((step, idx) => {
                  const matched =
                    selectedPacket?.events.find((e) => e.event_type === step) ??
                    (step === "promote"
                      ? selectedPacket?.events.find((e) => e.event_type === "watcher_scan")
                      : undefined);

                  const failed = matched?.status === "error" || matched?.status === "skipped";
                  const complete = !!matched && !failed;

                  return (
                    <div
                      key={step}
                      style={{
                        borderRadius: 16,
                        border: "1px solid rgba(192,132,252,0.2)",
                        background: "rgba(2,6,23,0.5)",
                        padding: 14,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          {failed ? (
                            <AlertTriangle size={16} color="#fda4af" />
                          ) : complete ? (
                            <CheckCircle2 size={16} color="#86efac" />
                          ) : (
                            <CircleDot size={16} color="#64748b" />
                          )}
                          <span style={{ fontWeight: 600, color: "#e2e8f0" }}>
                            {idx + 1}. {step === "hermes_write" ? "write" : step}
                          </span>
                        </div>
                        {matched ? (
                          <span
                            style={{
                              borderRadius: 999,
                              border: `1px solid ${statusPill(matched.status)}`,
                              padding: "4px 10px",
                              fontSize: 11,
                              color: statusPill(matched.status),
                            }}
                          >
                            {matched.status}
                          </span>
                        ) : (
                          <span
                            style={{
                              borderRadius: 999,
                              border: "1px solid rgba(148,163,184,0.3)",
                              padding: "4px 10px",
                              fontSize: 11,
                              color: "#94a3b8",
                            }}
                          >
                            pending
                          </span>
                        )}
                      </div>
                      <div style={{ marginTop: 8, fontSize: 11, color: "#64748b" }}>{matched?.timestamp || "No event yet"}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#cbd5f5" }}>{matched?.detail || "Waiting for this stage."}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        <div style={styles.sectionGrid}>
          <div style={styles.panel}>
            <div style={styles.sectionTitleRow}>
              <div>
                <h2 style={styles.sectionTitle}>Recent Sentinel Runs</h2>
                <div style={styles.sectionSubtitle}>
                  Read-only run JSON artifacts from <span style={styles.mono}>logs/hermes/runs/</span>. This surface presents the internal reviewer role as Sentinel while continuing to read legacy hermes-named records.
                </div>
              </div>
              <span style={{ ...styles.badge, ...styles.badgeWarn }}>preview-only source</span>
            </div>

            <div style={styles.stack}>
              {hermesRuns.length ? (
                hermesRuns.map((run, index) => {
                  const tone =
                    run.error || !run.ok
                      ? styles.badgeBad
                      : run.status === "petition_recommended"
                        ? styles.badgeWarn
                        : styles.badgeGood;

                  return (
                    <div key={`${run.run_id || run.source_path || "hermes-run"}-${index}`} style={styles.recordCard}>
                      <div style={styles.recordMetaRow}>
                        <div>
                          <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>
                            {run.run_id || "unknown run"}
                          </div>
                          <div style={styles.subtleText}>
                            {run.source_path || "unknown source"} {run.captured_at ? ` - ${run.captured_at}` : ""}
                          </div>
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          <span style={{ ...styles.badge, ...tone }}>{run.status || (run.error ? "error" : "unknown")}</span>
                          <span style={{ ...styles.badge, ...styles.badgeGood }}>{run.mode || "unknown mode"}</span>
                          <span style={styles.badge}>confidence {(run.confidence ?? 0).toFixed(2)}</span>
                        </div>
                      </div>

                      <div style={{ marginTop: 10, color: "#cbd5f5", fontSize: 13, lineHeight: 1.5 }}>
                        {run.summary || "No summary available."}
                      </div>

                      <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 8 }}>
                        {(run.evidence_refs || []).length ? (
                          run.evidence_refs!.map((ref, refIndex) => (
                            <span key={`${run.run_id || "hermes"}-ref-${refIndex}`} style={styles.badge}>
                              {ref}
                            </span>
                          ))
                        ) : (
                          <span style={styles.subtleText}>No evidence refs recorded.</span>
                        )}
                      </div>

                        <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Recommended action</div>
                        <div style={{ marginTop: 4, fontSize: 14, fontWeight: 600, color: "#f5d0fe" }}>
                          {run.recommended_action || "-"}
                        </div>
                        <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 8 }}>
                          {run.petition_kind ? (
                            <span style={styles.badge}>
                              petition_kind: {run.petition_kind}
                            </span>
                          ) : null}
                          {run.classification?.title ? (
                            <span style={styles.badge}>
                              classification: {run.classification.title}
                            </span>
                          ) : null}
                        </div>
                      </div>

                      {run.error ? (
                        <div style={{ ...styles.previewBox, borderColor: "rgba(251,113,133,0.3)", color: "#fecdd3" }}>
                          {run.error}
                        </div>
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <div style={styles.recordCard}>
                  No Sentinel run JSON artifacts were found in <span style={styles.mono}>logs/hermes/runs/</span> yet.
                </div>
              )}
            </div>
          </div>

          <div style={styles.panel}>
            <div style={styles.sectionTitleRow}>
              <div>
                <h2 style={styles.sectionTitle}>Petition Drafts</h2>
                <div style={styles.sectionSubtitle}>
                  Read-only draft records from <span style={styles.mono}>memory/drafts/</span>, with a preview-only review view built from the existing review helper logic.
                </div>
              </div>
              <span style={{ ...styles.badge, ...styles.badgeGood }}>preview only</span>
            </div>

            {selectedDraftPath ? (
              <div style={styles.previewBox}>
                <div style={styles.subtleText}>Focused review preview</div>
                <div style={{ marginTop: 4, fontSize: 14, fontWeight: 600, color: "#f5d0fe" }}>{selectedDraftPath}</div>
                <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                  This is the currently selected review preview path. Use it to keep the draft focus visible while browsing diagnostics.
                </div>
              </div>
            ) : null}

            <div style={styles.stack}>
              {petitionDrafts.length ? (
                petitionDrafts.map((item, index) => {
                  if (!item.ok || !item.draft || !item.review_preview) {
                    return (
                      <div key={`${item.source_path || "draft-error"}-${index}`} style={styles.recordCard}>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#fecdd3" }}>Draft load error</div>
                        <div style={{ marginTop: 8, ...styles.subtleText }}>{item.source_path || "unknown source"}</div>
                        <div style={{ marginTop: 10, color: "#fecdd3", fontSize: 13, lineHeight: 1.5 }}>
                          {item.error || "Unknown draft error"}
                        </div>
                      </div>
                    );
                  }

                  const draft = item.draft;
                  const preview = item.review_preview;
                  const allowed = preview.submission_allowed;
                  const gateTone = allowed ? styles.badgeGood : styles.badgeBad;
                  const draftPath = preview.draft_path || item.source_path || draft.petition_id;
                  const isSelectedDraft = selectedDraftPath === draftPath || selectedDraftPath === item.source_path;

                  return (
                    <div
                      key={`${draft.petition_id}-${index}`}
                      style={{
                        ...styles.recordCard,
                        borderColor: isSelectedDraft ? "rgba(252,211,77,0.45)" : "rgba(192,132,252,0.2)",
                        background: isSelectedDraft ? "rgba(124,58,237,0.18)" : "rgba(2,6,23,0.55)",
                      }}
                    >
                      <div style={styles.recordMetaRow}>
                        <div>
                          <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>
                            {draft.petition_id}
                          </div>
                          <div style={styles.subtleText}>
                            {item.source_path || "unknown source"} {preview.draft_path ? ` - ${preview.draft_path}` : ""}
                          </div>
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          <span style={{ ...styles.badge, ...styles.badgeGood }}>{draft.mode}</span>
                          <span style={{ ...styles.badge, ...styles.badgeWarn }}>
                            {draft.petition_kind} / {draft.petition_type}
                          </span>
                          <span style={styles.badge}>confidence {draft.confidence.toFixed(2)}</span>
                        </div>
                      </div>

                      <div style={{ marginTop: 10, color: "#cbd5f5", fontSize: 13, lineHeight: 1.5 }}>
                        {draft.summary}
                      </div>

                      <div style={{ marginTop: 12, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
                        <div>
                          <div style={styles.subtleText}>requested action</div>
                          <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600 }}>
                            {draft.requested_action}
                          </div>
                        </div>
                        <div>
                          <div style={styles.subtleText}>source run ID</div>
                          <div style={{ marginTop: 4, color: "#f5d0fe", fontSize: 13, fontWeight: 600, ...styles.mono }}>
                            {draft.source_run_id}
                          </div>
                        </div>
                        <div>
                          <div style={styles.subtleText}>review gate</div>
                          <div style={{ marginTop: 4, color: allowed ? "#bbf7d0" : "#fecdd3", fontSize: 13, fontWeight: 600 }}>
                            {allowed ? "would submit" : "blocked"}
                          </div>
                        </div>
                      </div>

                      <div style={styles.previewBox}>
                        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                          <div>
                            <div style={styles.subtleText}>Preview-only would submit</div>
                            <div style={{ marginTop: 4, fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>
                              {preview.submission_gate.status}
                            </div>
                          </div>
                          <span style={{ ...styles.badge, ...gateTone }}>{allowed ? "allowed" : "blocked"}</span>
                        </div>
                        <div style={{ marginTop: 8, color: "#cbd5f5", fontSize: 13, lineHeight: 1.5 }}>
                          {preview.submission_gate.reason}
                        </div>
                        <div style={{ marginTop: 8, ...styles.subtleText }}>
                          dispatch path: <span style={styles.mono}>{preview.dispatch_path}</span>
                        </div>
                        <div style={{ marginTop: 4, ...styles.subtleText }}>
                          dispatch petition ID: <span style={styles.mono}>{preview.dispatch_petition_id}</span>
                        </div>
                        <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" as const }}>
                          <button
                            type="button"
                            onClick={() => openReviewPreview(draftPath)}
                            style={styles.secondaryButton}
                          >
                            Focus review preview
                          </button>
                          <button
                            type="button"
                            onClick={() => setViewMode("missions")}
                            style={styles.secondaryButton}
                          >
                            Back to missions
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div style={styles.recordCard}>
                  No petition draft JSON files were found in <span style={styles.mono}>memory/drafts/</span> yet.
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={styles.sectionGrid}>
          <div style={styles.panel}>
            <div style={styles.sectionTitleRow}>
              <div>
                <h2 style={styles.sectionTitle}>Support helper activity</h2>
                <div style={styles.sectionSubtitle}>
                  Read-only helper instances from `logs/support/orchestration/instances/` and `logs/support/retrieval/instances/`.
                </div>
              </div>
              <span style={{ ...styles.badge, ...styles.badgeGood }}>
                {supportActivity.available ? `${supportActivity.total} helpers` : "no helpers"}
              </span>
            </div>

            <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", marginBottom: 16 }}>
              {helper2bRuntime.available ? (
                <div style={{ ...styles.recordCard, padding: 12, gridColumn: "1 / -1" }}>
                  <div style={styles.recordMetaRow}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: "#f5d0fe" }}>Spinetop-Expeditioner runtime</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                        {helper2bRuntime.role_description || "Mission-local task worker."}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      <span style={{ ...styles.badge, ...styles.badgeGood }}>
                        {helper2bRuntime.configured ? "configured" : "not configured"}
                      </span>
                      <span style={{ ...styles.badge, ...(helper2bRuntime.enabled ? styles.badgeGood : styles.badgeWarn) }}>
                        {helper2bRuntime.enabled ? "enabled" : "disabled"}
                      </span>
                      <span style={styles.badge}>{helper2bRuntime.execution_backend || "unknown backend"}</span>
                    </div>
                  </div>
                  <div style={{ marginTop: 10, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                    {helper2bRuntime.enabled
                      ? `Bound to ${helper2bRuntime.provider || helper2bRuntime.provider_requirement || "local"} ${helper2bRuntime.model || helper2bRuntime.default_model_key || "model"}.`
                      : "Currently configured as a disabled-safe scripted seam rather than a live model-invoked mission worker. Retrieval and runner outputs remain bounded support paths."}
                  </div>
                  <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                    Derived mission-local worker only. It does not approve, create truth, or bypass governance. External visible returns remain structured receipts.
                  </div>
                  <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8", lineHeight: 1.5 }}>
                    Mapped helpers: {(helper2bRuntime.mapped_helpers || []).join(", ") || "none"}.
                  </div>
                </div>
              ) : null}
              {Object.entries(supportActivity.lane_counts || {}).map(([lane, count]) => (
                <div key={lane} style={{ ...styles.recordCard, padding: 12 }}>
                  <div style={styles.subtleText}>{lane}</div>
                  <div style={{ marginTop: 6, fontSize: 24, fontWeight: 600, color: "#f5d0fe" }}>{count}</div>
                </div>
              ))}
            </div>

            <div style={styles.stack}>
              {(supportActivity.items || []).length ? (
                supportActivity.items.map((item) => {
                  const expiresText = item.expires_at ? `expires ${item.expires_at}` : "expires unavailable";
                  return (
                    <div key={`${item.lane}-${item.helper_id}`} style={styles.recordCard}>
                      <div style={styles.recordMetaRow}>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: "#f5d0fe" }}>
                            {item.helper_type}
                          </div>
                          <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                            {item.helper_id}
                          </div>
                        </div>
                        <span
                          style={{
                            ...styles.badge,
                            ...(item.status === "complete" ? styles.badgeGood : item.status === "blocked" ? styles.badgeBad : styles.badgeWarn),
                          }}
                        >
                          {item.status}
                        </span>
                      </div>
                      <div style={{ marginTop: 10, fontSize: 12, color: "#cbd5f5" }}>
                        mandate <span style={styles.mono}>{item.mandate_id || "unknown"}</span>
                      </div>
                      <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5" }}>
                        task <span style={styles.mono}>{item.task_scope || "unknown"}</span>
                      </div>
                      <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 12, fontSize: 11, color: "#94a3b8" }}>
                        <span>lane {item.lane}</span>
                        <span>{item.created_at ? `created ${item.created_at}` : "created unavailable"}</span>
                        <span>{expiresText}</span>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div style={styles.recordCard}>No support helper instances found in the logs yet.</div>
              )}
            </div>
          </div>

          <div style={styles.panel}>
            <div style={styles.sectionTitleRow}>
              <div>
                <h2 style={styles.sectionTitle}>Mirror-door test summary</h2>
                <div style={styles.sectionSubtitle}>
                  Read-only summary from `scripts/test_mirror_door_contracts.py` and `tests/mirror_door_contracts/`.
                </div>
              </div>
              <span style={{ ...styles.badge, ...(mirrorDoorTest.available ? styles.badgeGood : styles.badgeWarn) }}>
                {mirrorDoorTest.available ? "available" : "unavailable"}
              </span>
            </div>

            <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", marginBottom: 16 }}>
              {[
                ["total", mirrorDoorTest.total ?? 0],
                ["correctly_blocked", mirrorDoorTest.correctly_blocked ?? 0],
                ["validly_accepted", mirrorDoorTest.validly_accepted ?? 0],
                ["unexpected_accept", mirrorDoorTest.unexpected_accept ?? 0],
                ["unexpected_error", mirrorDoorTest.unexpected_error ?? 0],
              ].map(([label, value]) => (
                <div key={label} style={{ ...styles.recordCard, padding: 12 }}>
                  <div style={styles.subtleText}>{label}</div>
                  <div style={{ marginTop: 6, fontSize: 24, fontWeight: 600, color: "#f5d0fe" }}>{value as number}</div>
                </div>
              ))}
            </div>

            <div style={styles.stack}>
              {(mirrorDoorTest.recent_failures || []).length ? (
                mirrorDoorTest.recent_failures!.map((failure) => (
                  <div key={`${failure.category}-${failure.case_id}`} style={styles.recordCard}>
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: "#f5d0fe" }}>
                          {failure.case_id}
                        </div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{failure.category}</div>
                      </div>
                      <span style={{ ...styles.badge, ...styles.badgeBad }}>{failure.actual}</span>
                    </div>
                    <div style={{ marginTop: 8, fontSize: 12, color: "#cbd5f5" }}>{failure.reason}</div>
                    <div style={{ marginTop: 6, fontSize: 11, color: "#94a3b8" }}>
                      expected {failure.expected} â€¢ surface {failure.attack_surface}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 11, color: "#64748b", wordBreak: "break-all" }}>
                      {failure.source_file}
                    </div>
                  </div>
                ))
              ) : (
                <div style={styles.recordCard}>No recent failures recorded.</div>
              )}
            </div>
          </div>
        </div>
          </>
        ) : null}
      </div>
    </div>
  );
}




