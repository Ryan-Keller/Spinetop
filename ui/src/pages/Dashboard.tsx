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

type NannyState = {
  ok: boolean;
  temperature: string;
  burst_score: number;
  error_score: number;
  active_agent_warnings: string[];
  recommended_actions: string[];
  global_cooldown_seconds: number;
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

type ExpeditionStatusBadge = "waiting_for_user" | "researching" | "ready_for_review" | "idle";

type ExpeditionSummary = {
  mission_id: string;
  objective: string;
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
  path: string;
};

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

type WorkbenchSummary = {
  root: string;
  folders: WorkbenchFolder[];
  files: WorkbenchFile[];
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
  parking_status?: {
    mission_id: string;
    status: "active" | "parked";
    reason?: string;
    parked_at?: string;
    parked_by?: string;
    resume_hint?: string;
    updated_at?: string;
  };
  operator_posture?: string;
  operator_posture_reason?: string;
  assumptions_active?: string[];
  blocking_questions?: string[];
  operator_options?: { label: string; value: string; kind?: string }[];
  triage_bucket?: string;
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
  mission_inputs: MissionInputRecord[];
  mission_chat: MissionChatMessage[];
  workbench: WorkbenchSummary;
  artifact_count: number;
  input_count: number;
  chat_count: number;
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
  mirror_door_test: MirrorDoorTestStatus;
  storage_overview?: StorageOverview;
};

type ExpeditionsResponse = {
  ok: boolean;
  source_root?: string;
  items: ExpeditionSummary[];
};

type ExpeditionDetailResponse = {
  ok: boolean;
  available: boolean;
  item: ExpeditionDetail | null;
  error?: string;
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
    maxHeight: 420,
    overflowY: "auto" as const,
    paddingRight: 2,
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

function getRecordString(record: unknown, key: string): string {
  if (!record || typeof record !== "object") return "";
  const value = (record as Record<string, unknown>)[key];
  return typeof value === "string" ? value : "";
}

function getRecordObject(record: unknown, key: string): Record<string, unknown> | null {
  if (!record || typeof record !== "object") return null;
  const value = (record as Record<string, unknown>)[key];
  if (!value || typeof value !== "object") return null;
  return value as Record<string, unknown>;
}

export default function Dashboard() {
  const [viewMode, setViewMode] = useState<"missions" | "diagnostics">("missions");
  const [data, setData] = useState<StatusResponse>(fallbackData);
  const [hermesRuns, setHermesRuns] = useState<HermesRun[]>([]);
  const [petitionDrafts, setPetitionDrafts] = useState<DraftRecord[]>([]);
  const [expeditions, setExpeditions] = useState<ExpeditionSummary[]>(fallbackExpeditions);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [selectedMission, setSelectedMission] = useState<ExpeditionDetail | null>(null);
  const [newMissionObjective, setNewMissionObjective] = useState("");
  const [missionInputDrafts, setMissionInputDrafts] = useState<Record<string, string>>({});
  const [missionChatDrafts, setMissionChatDrafts] = useState<Record<string, string>>({});
  const [workbenchFolder, setWorkbenchFolder] = useState("intake");
  const [selectedDraftPath, setSelectedDraftPath] = useState<string | null>(null);
  const [uiNotice, setUiNotice] = useState<UiNotice | null>(null);
  const [missionLoading, setMissionLoading] = useState(false);
  const [missionSaving, setMissionSaving] = useState(false);
  const [missionActionLabel, setMissionActionLabel] = useState("");
  const [calibrationAxes, setCalibrationAxes] = useState<CalibrationAxis[]>([
    { key: "exploration", label: "Exploration pressure", value: 72, hint: "how eagerly the mission explores" },
    { key: "boundedness", label: "Boundedness", value: 84, hint: "how tightly the mission follows the ask" },
    { key: "respect", label: "User respect", value: 93, hint: "how carefully the mission handles operator input" },
    { key: "clarity", label: "Clarity", value: 79, hint: "how cleanly the mission reports back" },
    { key: "governance", label: "Governance fidelity", value: 88, hint: "how strictly the mission honors the safe lanes" },
    { key: "uncertainty", label: "Uncertainty tolerance", value: 55, hint: "how boldly the mission handles fuzzy tasks" },
  ]);
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState("demo data");
  const [errorText, setErrorText] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);
  const missionInputInFlightRef = useRef<string | null>(null);
  const missionChatInFlightRef = useRef<string | null>(null);

  const loadJson = async <T,>(url: string): Promise<T> => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  };

  const load = async () => {
    setLoading(true);
    try {
      const [statusResult, runsResult, draftsResult, expeditionsResult] = await Promise.all([
        loadJson<StatusResponse>(`${API_BASE}/status`)
          .then((value) => ({ ok: true as const, value }))
          .catch((error) => ({ ok: false as const, error })),
        loadJson<{ ok: boolean; items: HermesRun[] }>(`${API_BASE}/hermes/runs?limit=6`)
          .then((value) => ({ ok: true as const, value }))
          .catch((error) => ({ ok: false as const, error })),
        loadJson<{ ok: boolean; items: DraftRecord[] }>(`${API_BASE}/petition-drafts?limit=6`)
          .then((value) => ({ ok: true as const, value }))
          .catch((error) => ({ ok: false as const, error })),
        loadJson<ExpeditionsResponse>(`${API_BASE}/expeditions`)
          .then((value) => ({ ok: true as const, value }))
          .catch((error) => ({ ok: false as const, error })),
      ]);

      const errors: string[] = [];

      if (statusResult.ok) {
        setData(statusResult.value);
      } else {
        setData(fallbackData);
        errors.push(`status: ${statusResult.error instanceof Error ? statusResult.error.message : "request failed"}`);
      }

      if (runsResult.ok) {
        setHermesRuns(Array.isArray(runsResult.value.items) ? runsResult.value.items : []);
      } else {
        setHermesRuns([]);
        errors.push(`hermes runs: ${runsResult.error instanceof Error ? runsResult.error.message : "request failed"}`);
      }

      if (draftsResult.ok) {
        setPetitionDrafts(Array.isArray(draftsResult.value.items) ? draftsResult.value.items : []);
      } else {
        setPetitionDrafts([]);
        errors.push(`drafts: ${draftsResult.error instanceof Error ? draftsResult.error.message : "request failed"}`);
      }

      if (expeditionsResult.ok) {
        const items = Array.isArray(expeditionsResult.value.items) ? expeditionsResult.value.items : [];
        setExpeditions(items);
      } else {
        setExpeditions([]);
        errors.push(`expeditions: ${expeditionsResult.error instanceof Error ? expeditionsResult.error.message : "request failed"}`);
      }

      setErrorText(errors.length ? `Using fallback data - ${errors.join(" | ")}` : "");
      setLastRefresh(new Date().toLocaleTimeString());
    } catch (err) {
      setData(fallbackData);
      setErrorText(`Using fallback data - ${err instanceof Error ? err.message : "request failed"}`);
      setLastRefresh("fallback mode");
      setHermesRuns([]);
      setPetitionDrafts([]);
      setExpeditions([]);
      setSelectedMission(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedMissionId && expeditions[0]?.mission_id) {
      setSelectedMissionId(expeditions[0].mission_id);
    }
  }, [expeditions, selectedMissionId]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedMissionId) {
      setSelectedMission(null);
      return () => {
        cancelled = true;
      };
    }

    setMissionLoading(true);
    loadJson<ExpeditionDetailResponse>(`${API_BASE}/expeditions/${selectedMissionId}`)
      .then((response) => {
        if (cancelled) return;
        setSelectedMission(response.ok && response.item ? response.item : null);
        const folders = response.ok && response.item?.workbench?.folders ? response.item.workbench.folders : [];
        if (folders.length && !folders.some((folder) => folder.name === workbenchFolder)) {
          setWorkbenchFolder(folders[0].name);
        }
      })
      .catch(() => {
        if (!cancelled) setSelectedMission(null);
      })
      .finally(() => {
        if (!cancelled) {
          setMissionLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedMissionId, lastRefresh]);

  const packets = useMemo(() => groupPackets(data.events_recent || []), [data.events_recent]);

  useEffect(() => {
    if (!selectedRecord && packets[0]?.recordName) {
      setSelectedRecord(packets[0].recordName);
    }
  }, [packets, selectedRecord]);

  const selectedPacket = packets.find((p) => p.recordName === selectedRecord) ?? packets[0] ?? null;
  const missionInputText = selectedMissionId ? missionInputDrafts[selectedMissionId] || "" : "";
  const missionChatText = selectedMissionId ? missionChatDrafts[selectedMissionId] || "" : "";

  const setMissionInputDraft = (value: string) => {
    if (!selectedMissionId) return;
    setMissionInputDrafts((prev) => ({ ...prev, [selectedMissionId]: value }));
  };

  const setMissionChatDraft = (value: string) => {
    if (!selectedMissionId) return;
    setMissionChatDrafts((prev) => ({ ...prev, [selectedMissionId]: value }));
  };

  const clearMissionInputDraft = (missionId?: string | null) => {
    if (!missionId) return;
    setMissionInputDrafts((prev) => ({ ...prev, [missionId]: "" }));
  };

  const clearMissionChatDraft = (missionId?: string | null) => {
    if (!missionId) return;
    setMissionChatDrafts((prev) => ({ ...prev, [missionId]: "" }));
  };

  const queueCounts = useMemo(() => {
    const events = data.events_recent || [];
    const inbox = events.filter((e) => e.event_type === "hermes_write").length;
    const promotion = events.filter((e) => e.event_type === "watcher_scan" || e.event_type === "promote").length;
    const collective = events.filter((e) => e.event_type === "approve").length;
    const honcho = data.honcho_sessions_total || 0;
    return [inbox, promotion, collective, honcho];
  }, [data.events_recent, data.honcho_sessions_total]);

  const gateOpen = useMemo(() => {
    const events = data.events_recent || [];
    return [
      true,
      events.some((e) => e.event_type === "watcher_scan"),
      events.some((e) => e.event_type === "approve" && e.status === "success"),
      events.some((e) => e.event_type === "honcho_bridge" && e.status === "success"),
    ];
  }, [data.events_recent]);

  const returnAll = data.return_all ?? fallbackData.return_all;
  const nanny = data.nanny ?? fallbackData.nanny;
  const dispatchCounts = data.dispatch_counts ?? fallbackData.dispatch_counts;
  const supportActivity: SupportHelperActivity = data.support_helper_activity ?? fallbackData.support_helper_activity ?? {
    available: false,
    total: 0,
    lane_counts: {},
    status_counts: {},
    items: [],
    source_dirs: {},
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
  const missionSummary = selectedMission?.mission_summary ?? null;
  const missionParkingStatus = selectedMission?.parking_status ?? null;
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
  const repeatedItemCount = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of data.events_recent || []) {
      const key = event.record_name || event.event_type || "";
      if (!key) continue;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return Array.from(counts.values()).filter((count) => count > 1).reduce((sum, count) => sum + count - 1, 0);
  }, [data.events_recent]);
  const attentionItems = useMemo<MissionAttentionItem[]>(() => {
    const items: MissionAttentionItem[] = [];

    for (const expedition of expeditions) {
      if (expedition.triage_bucket === "parked" || expedition.operator_posture === "parked") {
        items.push({
          key: `parked-${expedition.mission_id}`,
          mission_id: expedition.mission_id,
          title: expedition.objective || expedition.mission_id,
          detail: expedition.operator_posture_reason || expedition.summary || expedition.current_state,
          badge: "Parked",
          tone: "watch",
        });
      } else if (expedition.triage_bucket === "waiting" || expedition.operator_posture === "needs_operator_answer" || expedition.status_badge === "waiting_for_user") {
        items.push({
          key: `wait-${expedition.mission_id}`,
          mission_id: expedition.mission_id,
          title: expedition.objective || expedition.mission_id,
          detail: expedition.operator_posture_reason || expedition.summary || expedition.current_state,
          badge: "Needs operator",
          tone: "watch",
        });
      } else if (expedition.triage_bucket === "do_now" && expedition.operator_posture === "proceed_with_assumptions") {
        items.push({
          key: `assume-${expedition.mission_id}`,
          mission_id: expedition.mission_id,
          title: expedition.objective || expedition.mission_id,
          detail: expedition.operator_posture_reason || expedition.summary || "Can continue under assumptions",
          badge: "Assumption-capable",
          tone: "good",
        });
      } else if (expedition.status_badge === "ready_for_review" || expedition.current_state === "PACKAGE_READY") {
        items.push({
          key: `review-${expedition.mission_id}`,
          mission_id: expedition.mission_id,
          title: expedition.objective || expedition.mission_id,
          detail: expedition.summary || "ready for review",
          badge: "Ready for review",
          tone: "good",
        });
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
  }, [expeditions, petitionDrafts, repeatedItemCount]);
  const blockedWaitingCount = attentionItems.filter((item) => item.key !== "noisy-signals").length;
  const latestMeaningfulSummary =
    latestDraftSummary ||
    getRecordString(latestHermesRun, "summary") ||
    getRecordString(selectedMission?.manifest, "summary") ||
    selectedMission?.objective ||
    "No summary recorded yet.";

  const expeditionStatusTone: Record<ExpeditionStatusBadge, StripTone> = {
    waiting_for_user: "watch",
    researching: "good",
    ready_for_review: "good",
    idle: "off",
  };

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

  const focusMission = (missionId: string, detail?: string) => {
    setSelectedMissionId(missionId);
    setViewMode("missions");
    setUiNotice({
      tone: "good",
      title: "Mission selected",
      detail: detail || `Focused mission ${missionId}.`,
    });
  };

  const refreshMissionDetail = async () => {
    if (!selectedMissionId) {
      setErrorText("Select an expedition first");
      return;
    }
    setMissionActionLabel("Refreshing mission detail");
    await load();
    setUiNotice({
      tone: "good",
      title: "Mission detail refreshed",
      detail: `Latest files and state were reloaded for ${selectedMissionId}.`,
    });
    setMissionActionLabel("");
  };

  const openReviewPreview = (previewPath?: string | null) => {
    if (previewPath) {
      setSelectedDraftPath(previewPath);
    }
    setViewMode("diagnostics");
    setUiNotice({
      tone: "info",
      title: "Review preview opened",
      detail: previewPath ? `Draft preview focus set to ${previewPath}.` : "Draft previews are visible in diagnostics.",
    });
  };

  const createMission = async () => {
    const objective = newMissionObjective.trim();
    if (!objective) {
      setErrorText("Objective is required to create an expedition");
      return;
    }
    try {
      setMissionSaving(true);
      setMissionActionLabel("Creating expedition");
      const res = await fetch(`${API_BASE}/expeditions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ objective }),
      });
      const payload = (await res.json()) as { ok?: boolean; item?: ExpeditionDetail; error?: string };
      if (!res.ok || !payload.ok || !payload.item) {
        throw new Error(payload.error || `HTTP ${res.status}`);
      }
      setNewMissionObjective("");
      setSelectedMissionId(payload.item.mission_id);
      setSelectedMission(payload.item);
      setWorkbenchFolder(payload.item.workbench.folders[0]?.name || "intake");
      clearMissionInputDraft(payload.item.mission_id);
      clearMissionChatDraft(payload.item.mission_id);
      setUiNotice({
        tone: "good",
        title: "Expedition created",
        detail: `${payload.item.mission_id} is active and ready for operator input.`,
      });
      setViewMode("missions");
      await load();
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Mission creation failed");
    } finally {
      setMissionSaving(false);
      setMissionActionLabel("");
    }
  };

  const sendMissionInput = async () => {
    const missionId = selectedMissionId;
    if (!missionId) {
      setErrorText("Select an expedition first");
      return;
    }
    const content = missionInputText.trim();
    if (!content) {
      setErrorText("Mission input cannot be empty");
      return;
    }
    const submissionKey = `${missionId}:${content}`;
    if (missionInputInFlightRef.current === submissionKey) {
      return;
    }
    try {
      missionInputInFlightRef.current = submissionKey;
      setMissionSaving(true);
      setMissionActionLabel("Sending mission input");
      const res = await fetch(`${API_BASE}/expeditions/${missionId}/input`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const payload = (await res.json()) as {
        ok?: boolean;
        item?: MissionInputRecord;
        mission?: ExpeditionDetail;
        error?: string;
      };
      if (!res.ok || !payload.ok) {
        throw new Error(payload.error || `HTTP ${res.status}`);
      }
      clearMissionInputDraft(missionId);
      if (payload.mission) {
        setSelectedMission(payload.mission);
      }
      setUiNotice({
        tone: "good",
        title: "Mission intake saved",
        detail: "The input landed once in the workbench intake folder as unreviewed mission input.",
      });
      await load();
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Mission input failed");
    } finally {
      missionInputInFlightRef.current = null;
      setMissionSaving(false);
      setMissionActionLabel("");
    }
  };

  const sendMissionChat = async (content: string, quickReply?: string) => {
    const missionId = selectedMissionId;
    if (!missionId) {
      setErrorText("Select an expedition first");
      return;
    }
    const message = content.trim();
    if (!message) {
      setErrorText("Chat message cannot be empty");
      return;
    }
    const submissionKey = `${missionId}:${quickReply || ""}:${message}`;
    if (missionChatInFlightRef.current === submissionKey) {
      return;
    }
    try {
      missionChatInFlightRef.current = submissionKey;
      setMissionSaving(true);
      setMissionActionLabel("Sending mission chat");
      const res = await fetch(`${API_BASE}/expeditions/${missionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: message, quick_reply: quickReply || undefined }),
      });
      const payload = (await res.json()) as {
        ok?: boolean;
        item?: ExpeditionDetail;
        messages?: MissionChatMessage[];
        exchange?: Record<string, unknown>;
        error?: string;
      };
      if (!res.ok || !payload.ok) {
        throw new Error(payload.error || `HTTP ${res.status}`);
      }
      clearMissionChatDraft(missionId);
      if (payload.item) {
        setSelectedMission(payload.item);
      }
      setUiNotice({
        tone: "good",
        title: "Mission chat updated",
        detail: quickReply ? `Quick reply sent once: ${quickReply}` : "Your message was accepted and added once to the mission chat.",
      });
      await load();
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Mission chat failed");
    } finally {
      missionChatInFlightRef.current = null;
      setMissionSaving(false);
      setMissionActionLabel("");
    }
  };

  const runMissionQuickReply = async (reply: { label: string; value: string }) => {
    if (reply.value === "Open review preview") {
      openReviewPreview(latestDraftPreviewPath);
      return;
    }
    await sendMissionChat(reply.value, reply.value);
  };

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
                Operator-first mission workspace for active expeditions, safe intake, draft review, and secondary diagnostics.
              </p>
            </div>

            <div style={styles.refreshRow}>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Last refresh: {lastRefresh}</div>
              <button onClick={load} disabled={loading} style={styles.refreshButton}>
                <RefreshCw size={16} />
                Refresh
              </button>
            </div>
          </div>

          <div style={styles.tabRow}>
            <button
              type="button"
              onClick={openMissionsView}
              style={{
                ...styles.tabButton,
                ...(viewMode === "missions" ? styles.tabButtonActive : null),
              }}
            >
              Missions
            </button>
            <button
              type="button"
              onClick={openDiagnosticsView}
              style={{
                ...styles.tabButton,
                ...(viewMode === "diagnostics" ? styles.tabButtonActive : null),
              }}
            >
              Diagnostics
            </button>
          </div>

          {errorText ? <div style={styles.alert}>{errorText}</div> : null}
          {uiNotice ? (
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

        <div style={styles.panel}>
          <div style={styles.sectionTitleRow}>
            <div>
              <h2 style={styles.sectionTitle}>Mission control strip</h2>
              <div style={styles.sectionSubtitle}>
                The main view stays centered on expeditions. Diagnostics move to the secondary tab.
              </div>
            </div>
            <span style={{ ...styles.badge, ...styles.badgeGood }}>
              {missionSaving ? missionActionLabel || "working" : missionLoading ? "loading mission" : "read-only"}
            </span>
          </div>
          <div style={styles.statusStrip}>
            {statusStripCard(
              "Backend health",
              data.ok ? "healthy" : "attention",
              data.ok ? "Status API and mission loaders are responding." : "One or more read-model loaders fell back."
            )}
            {statusStripCard(
              "Frontend/live",
              loading ? "refreshing" : "live",
              loading ? "Refreshing dashboard data and mission detail." : `Last refresh ${lastRefresh}.`,
              loading ? "watch" : "good"
            )}
            {statusStripCard(
              "Active expeditions",
              String(expeditions.length),
              expeditions.length ? "Operator-managed missions are available to open." : "Create an expedition to start a mission.",
              expeditions.length ? "good" : "off"
            )}
            {statusStripCard(
              "Drafts pending review",
              String(petitionDrafts.filter((item) => item.ok).length),
              "Preview-only petitions remain in memory/drafts.",
              petitionDrafts.length ? "watch" : "off"
            )}
            {statusStripCard(
              "Blocked / waiting",
              String(blockedWaitingCount),
              "Clarification-needed, reconsideration, and blocked drafts need operator attention.",
              blockedWaitingCount ? "watch" : "good"
            )}
            {statusStripCard(
              "Noisy / repeated",
              String(repeatedItemCount),
              repeatedItemCount
                ? "Repeated telemetry is visible in diagnostics."
                : "No repeated signals were detected in recent events.",
              repeatedItemCount ? "watch" : "good"
            )}
          </div>
        </div>

        <div id="expeditions" style={styles.panel}>
          <div style={styles.sectionTitleRow}>
            <div>
              <h2 style={styles.sectionTitle}>Expeditions</h2>
              <div style={styles.sectionSubtitle}>
                Operator-managed mission containers with a focused readout, safe intake, and a workbench that stays outside governed memory.
              </div>
            </div>
            <div style={styles.pillRow}>
              <span style={{ ...styles.badge, ...styles.badgeGood }}>Workbench Only</span>
              <span style={{ ...styles.badge, ...styles.badgeWarn }}>Unreviewed</span>
              <span style={{ ...styles.badge, ...styles.badgeOutline }}>Preview Only</span>
            </div>
          </div>

          <div style={styles.gridSplit}>
            <div style={styles.stack}>
              <div style={styles.recordCard}>
                <div style={styles.recordMetaRow}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Create Expedition</div>
                    <div style={styles.subtleText}>
                      Generates a new mission_id, creates the mission brief, and opens the focused view.
                    </div>
                  </div>
                  <span style={{ ...styles.badge, ...styles.badgeGood }}>safe zone</span>
                </div>
                <div style={{ marginTop: 12, display: "flex", flexDirection: "column" as const, gap: 10 }}>
                  <input
                    type="text"
                    value={newMissionObjective}
                    onChange={(event) => setNewMissionObjective(event.target.value)}
                    placeholder="Objective, for example: review recent anomalies and suggest action"
                    style={styles.fieldInput}
                  />
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const }}>
                    <motion.button
                      type="button"
                      onClick={createMission}
                      disabled={missionSaving}
                      style={styles.refreshButton}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      {missionSaving && missionActionLabel === "Creating expedition" ? "Creating..." : "Create Expedition"}
                    </motion.button>
                    <motion.button
                      type="button"
                      onClick={() => setNewMissionObjective("")}
                      style={styles.secondaryButton}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                    >
                      Clear
                    </motion.button>
                  </div>
                </div>
              </div>

              <div style={styles.recordCard}>
                <div style={styles.recordMetaRow}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Needs Attention</div>
                    <div style={styles.subtleText}>
                      Waiting-for-user, clarification-needed, reconsideration, blocked drafts, and noisy repeats.
                    </div>
                  </div>
                  <span style={{ ...styles.badge, ...(blockedWaitingCount ? styles.badgeWarn : styles.badgeGood) }}>
                    {blockedWaitingCount} items
                  </span>
                </div>
                <div style={{ marginTop: 12, ...styles.scrollArea, maxHeight: 240 }}>
                  {attentionItems.length ? (
                    attentionItems.map((item) => (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => item.mission_id ? focusMission(item.mission_id, item.detail) : openDiagnosticsView()}
                        style={{
                          ...styles.recordCard,
                          cursor: item.mission_id ? "pointer" : "default",
                          textAlign: "left" as const,
                          borderColor: item.tone === "good" ? "rgba(52,211,153,0.3)" : "rgba(251,191,36,0.3)",
                          background: "rgba(2,6,23,0.55)",
                        }}
                      >
                        <div style={styles.recordMetaRow}>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>{item.title}</div>
                            <div style={styles.subtleText}>{item.detail}</div>
                          </div>
                          <span style={{ ...styles.badge, ...(item.tone === "good" ? styles.badgeGood : styles.badgeWarn) }}>
                            {item.badge}
                          </span>
                        </div>
                        {item.mission_id ? (
                          <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>mission {item.mission_id}</div>
                        ) : null}
                      </button>
                    ))
                  ) : (
                    <div style={styles.recordCard}>No active attention items right now.</div>
                  )}
                </div>
              </div>

              <div style={styles.recordCard}>
                <div style={styles.recordMetaRow}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Agent Calibration</div>
                    <div style={styles.subtleText}>
                      The soul editors stay as a visible tuning panel for exploration, boundedness, clarity, and governance fidelity.
                    </div>
                  </div>
                  <span style={{ ...styles.badge, ...styles.badgeOutline }}>calibration</span>
                </div>
                <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
                  {calibrationAxes.map((axis) => (
                    <div key={axis.label} style={styles.previewBox}>
                      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0" }}>{axis.label}</div>
                          <div style={styles.subtleText}>{axis.hint}</div>
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#f5d0fe" }}>{axis.value}</div>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={axis.value}
                        onChange={(event) => {
                          const nextValue = Number(event.target.value);
                          setCalibrationAxes((prev) =>
                            prev.map((item) => (item.key === axis.key ? { ...item, value: nextValue } : item))
                          );
                        }}
                        style={{ marginTop: 10, width: "100%" }}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div style={styles.recordCard}>
                <div style={styles.recordMetaRow}>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Expedition List</div>
                    <div style={styles.subtleText}>Click one to focus the mission details.</div>
                  </div>
                  <span style={{ ...styles.badge, ...styles.badgeGood }}>{expeditions.length} active</span>
                </div>

                <div style={styles.expeditionList}>
                  {expeditions.length ? (
                    expeditions.map((expedition) => {
                      const isSelected = selectedMissionId === expedition.mission_id;
                      const tone =
                        expedition.status_badge === "researching"
                          ? styles.badgeGood
                          : expedition.status_badge === "ready_for_review"
                            ? styles.badgeOutline
                            : expedition.status_badge === "waiting_for_user"
                              ? styles.badgeWarn
                              : styles.badge;

                      return (
                        <motion.button
                          key={expedition.mission_id}
                          type="button"
                          onClick={() => focusMission(expedition.mission_id, expedition.summary || expedition.objective || expedition.mission_id)}
                          style={{
                            ...styles.recordCard,
                            cursor: "pointer",
                            textAlign: "left" as const,
                            borderColor: isSelected ? "rgba(252,211,77,0.45)" : "rgba(192,132,252,0.2)",
                            background: isSelected ? "rgba(124,58,237,0.18)" : "rgba(2,6,23,0.55)",
                          }}
                          whileHover={{ scale: 1.01 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          <div style={styles.recordMetaRow}>
                            <div>
                              <div style={{ fontSize: 15, fontWeight: 600, color: "#e2e8f0" }}>{expedition.mission_id}</div>
                              <div style={styles.subtleText}>{expedition.objective || "No objective recorded yet."}</div>
                            </div>
                            <span style={{ ...styles.badge, ...tone }}>{expedition.status_badge}</span>
                          </div>
                          <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
                            <span style={styles.badge}>{expedition.current_state}</span>
                            {expedition.operator_posture ? <span style={styles.badge}>{expedition.operator_posture}</span> : null}
                            {expedition.triage_bucket ? <span style={styles.badge}>{expedition.triage_bucket}</span> : null}
                            <span style={styles.badge}>{expedition.latest_run_id || "no run yet"}</span>
                            <span style={styles.badge}>{expedition.last_updated || "no updates"}</span>
                          </div>
                          {expedition.summary ? (
                            <div style={{ marginTop: 10, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                              {expedition.summary}
                            </div>
                          ) : null}
                          {expedition.operator_posture_reason ? (
                            <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8", lineHeight: 1.5 }}>
                              {expedition.operator_posture_reason}
                            </div>
                          ) : null}
                        </motion.button>
                      );
                    })
                  ) : (
                    <div style={styles.recordCard}>No expeditions exist yet. Create one above to open the focused view.</div>
                  )}
                </div>
              </div>
            </div>

            <div style={styles.stack}>
              {selectedMission ? (
                <>
                  <motion.div
                    key={`${selectedMission.mission_id}-summary`}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.22 }}
                    style={styles.recordCard}
                  >
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Mission Summary</div>
                        <div style={styles.subtleText}>Plain-language summary to keep the operator out of artifact archaeology.</div>
                      </div>
                      <span style={{ ...styles.badge, ...statusStripToneStyles[expeditionStatusTone[selectedMission.status_badge]] }}>
                        {missionSummaryOperatingStatus}
                      </span>
                    </div>

                    <div style={{ marginTop: 12, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Status</div>
                        <div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: "#f5d0fe" }}>{missionSummaryOperatingStatus}</div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5" }}>Lifecycle state: {missionSummaryLifecycleState}</div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5" }}>
                          Operator posture: {missionSummaryOperatorPosture} · Triage: {missionSummaryTriageBucket}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                          {missionSummary?.latest_summary || missionSummary?.summary || "No structured summary is available yet."}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Confidence</div>
                        <div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: "#f5d0fe" }}>{missionSummaryConfidence}</div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5" }}>
                          Derived from Hermes, drafts, clarification packets, manifest, mission inputs, and current assumptions.
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5" }}>
                          Confidence reduction is explicit when assumptions are being carried forward.
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Crew status</div>
                        <div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: missionSummaryCrewStatus === "recalled" ? "#fde68a" : "#bbf7d0" }}>
                          {missionSummaryCrewStatus}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                          Expedition activity is currently {missionSummaryExpeditionActivity}.
                          {missionSummaryParkedAt ? ` Parked at ${missionSummaryParkedAt}.` : ""}
                        </div>
                        {missionParkingStatus?.status === "parked" ? (
                          <div style={{ marginTop: 6, fontSize: 12, color: "#fde68a", lineHeight: 1.5 }}>
                            Parked because: {missionParkingStatus.reason || missionSummaryReason}
                          </div>
                        ) : null}
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Can continue without input</div>
                        <div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: missionSummaryCanContinue ? "#bbf7d0" : "#fecaca" }}>
                          {missionSummaryCanContinue ? "Yes" : "No"}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                          {missionSummaryCanContinue
                            ? "The mission can continue under explicit assumptions while the remaining question stays deferred."
                            : "The mission is truly blocked because the missing answer changes the safe path or review path."}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Recommended next step</div>
                        <div style={{ marginTop: 4, fontSize: 14, fontWeight: 700, color: "#f5d0fe", lineHeight: 1.5 }}>
                          {missionSummaryNextStep}
                        </div>
                      </div>
                    </div>

                    <div style={{ marginTop: 12, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>{missionSummaryCanContinue ? "Why it is continuing" : "Why it is blocked"}</div>
                        <div style={{ marginTop: 8, fontSize: 13, color: "#fde68a", lineHeight: 1.55 }}>
                          {missionSummaryReason}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Next question</div>
                        <div style={{ marginTop: 8, fontSize: 13, color: "#bbf7d0", lineHeight: 1.55 }}>
                          {missionSummaryQuestion || "No clarification question is needed right now."}
                        </div>
                        <div style={{ marginTop: 8, fontSize: 12, color: "#cbd5f5", lineHeight: 1.55 }}>
                          Next best operator answer: {missionSummaryNextAnswer}
                        </div>
                        {!missionSummaryCanContinue ? (
                          <div style={{ marginTop: 8, fontSize: 12, color: "#fde68a", lineHeight: 1.55 }}>
                            Waking input: {missionSummaryWakeHint || "Send the missing detail to resume expedition activity."}
                          </div>
                        ) : null}
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>What we believe</div>
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column" as const, gap: 8 }}>
                          {missionSummaryBeliefs.map((belief, index) => (
                            <div
                              key={`${belief}-${index}`}
                              style={{
                                borderRadius: 12,
                                border: "1px solid rgba(192,132,252,0.18)",
                                background: "rgba(2,6,23,0.45)",
                                padding: "8px 10px",
                                fontSize: 12,
                                color: "#cbd5f5",
                                lineHeight: 1.45,
                              }}
                            >
                              • {belief}
                            </div>
                          ))}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Confirmed facts</div>
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column" as const, gap: 8 }}>
                          {missionSummaryConfirmedFacts.length ? (
                            missionSummaryConfirmedFacts.map((fact, index) => (
                              <div
                                key={`${fact}-${index}`}
                                style={{
                                  borderRadius: 12,
                                  border: "1px solid rgba(52,211,153,0.2)",
                                  background: "rgba(6,78,59,0.16)",
                                  padding: "8px 10px",
                                  fontSize: 12,
                                  color: "#bbf7d0",
                                  lineHeight: 1.45,
                                }}
                              >
                                • {fact}
                              </div>
                            ))
                          ) : (
                            <div style={styles.subtleText}>No operator-confirmed facts have been captured yet.</div>
                          )}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Assumptions in use</div>
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column" as const, gap: 8 }}>
                          {missionSummaryAssumptions.length ? (
                            missionSummaryAssumptions.map((assumption, index) => (
                              <div
                                key={`${assumption}-${index}`}
                                style={{
                                  borderRadius: 12,
                                  border: "1px solid rgba(192,132,252,0.18)",
                                  background: "rgba(2,6,23,0.45)",
                                  padding: "8px 10px",
                                  fontSize: 12,
                                  color: "#cbd5f5",
                                  lineHeight: 1.45,
                                }}
                              >
                                • {assumption}
                              </div>
                            ))
                          ) : (
                            <div style={styles.subtleText}>No active assumptions are needed right now.</div>
                          )}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Open questions</div>
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column" as const, gap: 8 }}>
                          {missionSummaryOpenQuestions.length ? (
                            missionSummaryOpenQuestions.map((question, index) => (
                              <div
                                key={`${question}-${index}`}
                                style={{
                                  borderRadius: 12,
                                  border: "1px solid rgba(251,191,36,0.2)",
                                  background: "rgba(120,53,15,0.18)",
                                  padding: "8px 10px",
                                  fontSize: 12,
                                  color: "#fde68a",
                                  lineHeight: 1.45,
                                }}
                              >
                                • {question}
                              </div>
                            ))
                          ) : (
                            <div style={styles.subtleText}>No unanswered questions are queued right now.</div>
                          )}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Blocking questions</div>
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column" as const, gap: 8 }}>
                          {missionSummaryBlockingQuestions.length ? (
                            missionSummaryBlockingQuestions.map((question, index) => (
                              <div
                                key={`${question}-${index}`}
                                style={{
                                  borderRadius: 12,
                                  border: "1px solid rgba(251,113,133,0.22)",
                                  background: "rgba(127,29,29,0.2)",
                                  padding: "8px 10px",
                                  fontSize: 12,
                                  color: "#fecaca",
                                  lineHeight: 1.45,
                                }}
                              >
                                • {question}
                              </div>
                            ))
                          ) : (
                            <div style={styles.subtleText}>No hard blockers are active right now.</div>
                          )}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Deferred questions</div>
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column" as const, gap: 8 }}>
                          {missionSummaryDeferredQuestions.length ? (
                            missionSummaryDeferredQuestions.map((question, index) => (
                              <div
                                key={`${question}-${index}`}
                                style={{
                                  borderRadius: 12,
                                  border: "1px solid rgba(148,163,184,0.2)",
                                  background: "rgba(15,23,42,0.5)",
                                  padding: "8px 10px",
                                  fontSize: 12,
                                  color: "#cbd5f5",
                                  lineHeight: 1.45,
                                }}
                              >
                                • {question}
                              </div>
                            ))
                          ) : (
                            <div style={styles.subtleText}>No deferred questions are queued right now.</div>
                          )}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>What we need from you</div>
                        <div style={{ marginTop: 8, display: "flex", flexDirection: "column" as const, gap: 8 }}>
                          {missionSummaryNeeds.length ? (
                            missionSummaryNeeds.map((need, index) => (
                              <div
                                key={`${need}-${index}`}
                                style={{
                                  borderRadius: 12,
                                  border: "1px solid rgba(251,191,36,0.2)",
                                  background: "rgba(120,53,15,0.18)",
                                  padding: "8px 10px",
                                  fontSize: 12,
                                  color: "#fde68a",
                                  lineHeight: 1.45,
                                }}
                              >
                                • {need}
                              </div>
                            ))
                          ) : (
                            <div style={styles.subtleText}>No missing inputs are currently flagged.</div>
                          )}
                        </div>
                      </div>
                    </div>

                    {missionSummaryQuickReplies.length ? (
                      <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
                        {missionSummaryQuickReplies.map((reply) => (
                          <motion.button
                            key={reply.label}
                            type="button"
                            onClick={() => runMissionQuickReply(reply)}
                            disabled={missionSaving}
                            style={styles.secondaryButton}
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                          >
                            {reply.label}
                          </motion.button>
                        ))}
                      </div>
                    ) : null}
                  </motion.div>

                  <div style={styles.recordCard}>
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>{selectedMission.mission_id}</div>
                        <div style={styles.subtleText}>{selectedMission.objective || "No objective recorded yet."}</div>
                      </div>
                      <span style={{ ...styles.badge, ...statusStripToneStyles[expeditionStatusTone[selectedMission.status_badge]] }}>
                        {selectedMission.status_badge}
                      </span>
                    </div>
                    <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
                      <span style={styles.badge}>{selectedMission.current_state}</span>
                      <span style={styles.badge}>{missionSummaryOperatorPosture}</span>
                      <span style={styles.badge}>{missionSummaryTriageBucket}</span>
                      <span style={styles.badge}>latest run {selectedMission.latest_run_id || "none"}</span>
                      <span style={styles.badge}>updated {selectedMission.last_updated || "unknown"}</span>
                      <span style={{ ...styles.badge, ...styles.badgeGood }}>Workbench Only</span>
                      <span style={{ ...styles.badge, ...styles.badgeWarn }}>Unreviewed</span>
                      <span style={{ ...styles.badge, ...styles.badgeOutline }}>Preview Only</span>
                    </div>
                    <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
                      <motion.button
                        type="button"
                        onClick={() => refreshMissionDetail()}
                        style={styles.refreshButton}
                        disabled={missionLoading || missionSaving || loading}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        {missionActionLabel === "Refreshing mission detail" ? "Refreshing..." : "Refresh mission detail"}
                      </motion.button>
                      <motion.button
                        type="button"
                        onClick={openDiagnosticsView}
                        style={styles.secondaryButton}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        Open diagnostics
                      </motion.button>
                      {latestDraftPreviewPath ? (
                        <motion.button
                          type="button"
                          onClick={() => openReviewPreview(latestDraftPreviewPath)}
                          style={styles.secondaryButton}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          Open review preview
                        </motion.button>
                      ) : null}
                    </div>
                    <div style={styles.previewBox}>
                      <div style={styles.subtleText}>Latest meaningful update</div>
                      <div style={{ marginTop: 4, fontSize: 14, fontWeight: 600, color: "#f5d0fe" }}>{latestMeaningfulSummary}</div>
                      <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                        {latestDraftPreviewPath
                          ? `Latest review preview: ${latestDraftPreviewPath}`
                          : latestPacketSummary
                            ? `Clarification packet: ${latestPacketSummary}`
                            : "No review preview has been opened yet."}
                      </div>
                      {missionLoading ? <div style={{ marginTop: 8, ...styles.subtleText }}>Loading mission detail...</div> : null}
                    </div>
                  </div>

                  <div style={styles.recordCard}>
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Mission Activity</div>
                        <div style={styles.subtleText}>
                          Latest Hermes run, draft, clarification packet, and manifest summary.
                        </div>
                      </div>
                      <span style={{ ...styles.badge, ...styles.badgeGood }}>focused view</span>
                    </div>
                    <div style={{ marginTop: 12, display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Latest Hermes run</div>
                        <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600, color: "#f5d0fe" }}>
                          {getRecordString(latestHermesRun, "run_id") || selectedMission.latest_run_id || "none"}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                          {getRecordString(latestHermesRun, "summary") || "No Hermes run recorded yet."}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Latest draft</div>
                        <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600, color: "#f5d0fe" }}>
                          {getRecordString(getRecordObject(latestDraft, "draft"), "petition_id") ||
                            getRecordString(latestDraft, "petition_id") ||
                            "none"}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                          {latestDraftSummary || getRecordString(latestDraft, "summary") || "No draft exists yet for this mission."}
                        </div>
                        {latestDraftPreviewPath ? (
                          <button
                            type="button"
                            onClick={() => openReviewPreview(latestDraftPreviewPath)}
                            style={{ ...styles.secondaryButton, marginTop: 10 }}
                          >
                            Open review preview
                          </button>
                        ) : null}
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Clarification packet</div>
                        <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600, color: "#f5d0fe" }}>
                          {getRecordString(latestClarificationPacket, "packet_id") || "none"}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                          {latestPacketSummary ||
                            getRecordString(getRecordObject(latestClarificationPacket, "provisional_answer"), "text") ||
                            "No clarification packet exists yet."}
                        </div>
                      </div>
                      <div style={styles.previewBox}>
                        <div style={styles.subtleText}>Manifest</div>
                        <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600, color: "#f5d0fe" }}>
                          {getRecordString(selectedMission.manifest, "status") || "not yet written"}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>
                          {getRecordString(selectedMission.manifest, "summary") || "No manifest summary yet."}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={styles.recordCard}>
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Mission Chat</div>
                        <div style={styles.subtleText}>
                          Back-and-forth operator chat. Quick replies stay explicit and write only to mission notes.
                        </div>
                      </div>
                      <span style={{ ...styles.badge, ...styles.badgeGood }}>{selectedMission.chat_count} messages</span>
                    </div>

                    <div style={{ marginTop: 12, ...styles.scrollArea, maxHeight: 260 }}>
                      {selectedMission.mission_chat.length ? (
                        selectedMission.mission_chat.map((message) => {
                          const isAssistant = message.sender === "assistant";
                          return (
                            <motion.div
                              key={message.message_id}
                              initial={{ opacity: 0, y: 6 }}
                              animate={{ opacity: 1, y: 0 }}
                              style={{
                                alignSelf: isAssistant ? "flex-start" : "flex-end",
                                maxWidth: "92%",
                                borderRadius: 16,
                                border: isAssistant
                                  ? "1px solid rgba(52,211,153,0.22)"
                                  : "1px solid rgba(192,132,252,0.22)",
                                background: isAssistant ? "rgba(6,78,59,0.22)" : "rgba(15,23,42,0.8)",
                                padding: 12,
                              }}
                            >
                              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                                <span style={{ ...styles.badge, ...(isAssistant ? styles.badgeGood : styles.badgeOutline) }}>
                                  {isAssistant ? "Mission agent" : "Operator"}
                                </span>
                                <span style={styles.subtleText}>{message.created_at || "just now"}</span>
                              </div>
                              <div style={{ fontSize: 13, color: "#e2e8f0", lineHeight: 1.55 }}>{message.message}</div>
                            </motion.div>
                          );
                        })
                      ) : (
                        <div style={styles.recordCard}>No mission chat yet. Send a message or pick a quick reply.</div>
                      )}
                    </div>

                    <div style={styles.previewBox}>
                      <textarea
                        value={missionChatText}
                        onChange={(event) => setMissionChatDraft(event.target.value)}
                        placeholder="Ask a question, add more context, or give the mission a direct instruction."
                        autoComplete="off"
                        style={{ ...styles.fieldTextarea, minHeight: 96 }}
                      />
                      <div style={{ marginTop: 8, ...styles.subtleText }}>
                        {missionChatText.trim()
                          ? "Draft only. This text stays local until you explicitly send it."
                          : "No unsent chat draft."}
                      </div>
                      <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
                        {missionSummaryQuickReplies.map((quickReply) => (
                          <motion.button
                            key={quickReply.label}
                            type="button"
                            onClick={() => runMissionQuickReply(quickReply)}
                            disabled={missionSaving}
                            style={styles.secondaryButton}
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                          >
                            {quickReply.label}
                          </motion.button>
                        ))}
                      </div>
                      <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
                        <motion.button
                          type="button"
                          onClick={() => sendMissionChat(missionChatText)}
                          disabled={missionSaving || !missionChatText.trim()}
                          style={styles.refreshButton}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          {missionSaving && missionActionLabel === "Sending mission chat" ? "Sending..." : "Send chat"}
                        </motion.button>
                        <motion.button
                          type="button"
                          onClick={() => clearMissionChatDraft(selectedMissionId)}
                          style={styles.secondaryButton}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          Clear
                        </motion.button>
                      </div>
                      <div style={{ marginTop: 10, ...styles.subtleText }}>
                        Chat stays in <span style={styles.mono}>workbench/missions/{selectedMission.mission_id}/notes/chat.jsonl</span> and never writes to
                        governed memory or dispatch.
                      </div>
                    </div>
                  </div>

                  <div style={styles.recordCard}>
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Mission Artifacts</div>
                        <div style={styles.subtleText}>Recent artifact records from the mission-local manifest or artifact index.</div>
                      </div>
                      <span style={{ ...styles.badge, ...styles.badgeOutline }}>{selectedMission.artifact_count} records</span>
                    </div>
                    <div style={{ marginTop: 12, display: "flex", flexDirection: "column" as const, gap: 10, maxHeight: 260, overflowY: "auto" }}>
                      {selectedMissionArtifactRefs.length ? (
                        selectedMissionArtifactRefs.map((item, index) => {
                          const kind = getRecordString(item, "artifact_kind") || getRecordString(item, "kind") || "artifact";
                          const stage = getRecordString(item, "artifact_stage") || "n/a";
                          const role = getRecordString(item, "problem_role") || "";
                          const quality = getRecordString(item, "quality_signal") || "";
                          const reusable = getRecordString(item, "reusability_class") || "";
                          const path = getRecordString(item, "path");
                          const createdAt = getRecordString(item, "created_at");

                          return (
                            <div key={`${kind}-${path}-${index}`} style={styles.recordCard}>
                              <div style={styles.recordMetaRow}>
                                <div>
                                  <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>{kind}</div>
                                  <div style={styles.subtleText}>{path}</div>
                                </div>
                                <span style={styles.badge}>{stage}</span>
                              </div>
                              <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
                                {role ? <span style={styles.badge}>{role}</span> : null}
                                {quality ? <span style={styles.badge}>{quality}</span> : null}
                                {reusable ? <span style={styles.badge}>{reusable}</span> : null}
                                {createdAt ? <span style={styles.badge}>{createdAt}</span> : null}
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div style={styles.recordCard}>No mission artifacts have been indexed yet.</div>
                      )}
                    </div>
                  </div>

                  <div style={styles.recordCard}>
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Mission Inputs</div>
                        <div style={styles.subtleText}>
                          Send to Mission (Unreviewed Input) writes into the workbench intake folder only.
                        </div>
                      </div>
                      <span style={{ ...styles.badge, ...styles.badgeWarn }}>Unreviewed</span>
                    </div>
                    <div style={{ marginTop: 12, display: "flex", flexDirection: "column" as const, gap: 10 }}>
                      <textarea
                        value={missionInputText}
                        onChange={(event) => setMissionInputDraft(event.target.value)}
                        placeholder="Add safe mission input for intake, review, or follow-up."
                        autoComplete="off"
                        style={styles.fieldTextarea}
                      />
                      <div style={styles.subtleText}>
                        {missionInputText.trim()
                          ? "Draft only. This input stays local until you explicitly send it."
                          : "No unsent mission input draft."}
                      </div>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const }}>
                        <motion.button
                          type="button"
                          onClick={sendMissionInput}
                          disabled={missionSaving || !missionInputText.trim()}
                          style={styles.refreshButton}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          {missionSaving && missionActionLabel === "Sending mission input" ? "Sending..." : "Send to Mission"}
                        </motion.button>
                        <motion.button
                          type="button"
                          onClick={() => clearMissionInputDraft(selectedMissionId)}
                          style={styles.secondaryButton}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                        >
                          Clear
                        </motion.button>
                      </div>
                      <div style={styles.subtleText}>
                        This lands in <span style={styles.mono}>workbench/missions/{selectedMission.mission_id}/intake/</span> as{" "}
                        <span style={styles.mono}>user_provided</span> and remains unreviewed until an operator acts.
                      </div>
                    </div>
                    <div style={{ marginTop: 12, ...styles.scrollArea }}>
                      {selectedMissionInputs.length ? (
                        selectedMissionInputs.map((input) => (
                          <div key={input.input_id} style={styles.recordCard}>
                            <div style={styles.recordMetaRow}>
                              <div>
                                <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>{input.input_id}</div>
                                <div style={styles.subtleText}>{input.created_at}</div>
                              </div>
                              <span style={{ ...styles.badge, ...styles.badgeWarn }}>{input.status}</span>
                            </div>
                            <div style={{ marginTop: 8, fontSize: 12, color: "#cbd5f5", lineHeight: 1.5 }}>{input.content}</div>
                            <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap" as const, gap: 8 }}>
                              <span style={styles.badge}>{input.source_type}</span>
                              <span style={styles.badge}>{input.path}</span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div style={styles.recordCard}>No mission inputs have been sent to this expedition yet.</div>
                      )}
                    </div>
                  </div>

                  <div style={styles.recordCard}>
                    <div style={styles.recordMetaRow}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#e2e8f0" }}>Workbench (Not Governed Memory)</div>
                        <div style={styles.subtleText}>
                          Messy sandbox for code, experiments, notes, and raw outputs. It is not bridge-submittable directly.
                        </div>
                      </div>
                      <span style={{ ...styles.badge, ...styles.badgeGood }}>Workbench Only</span>
                    </div>
                    <div style={{ marginTop: 12, ...styles.tabRow }}>
                      {selectedMissionFolders.length ? (
                        selectedMissionFolders.map((folder) => (
                          <button
                            key={folder.name}
                            type="button"
                            onClick={() => setWorkbenchFolder(folder.name)}
                            style={{
                              ...styles.tabButton,
                              ...(workbenchFolder === folder.name ? styles.tabButtonActive : null),
                            }}
                          >
                            {folder.name} ({folder.file_count})
                          </button>
                        ))
                      ) : (
                        <span style={styles.subtleText}>Workbench folders will appear after the first mission is created.</span>
                      )}
                    </div>
                    <div style={{ marginTop: 12, fontSize: 12, color: "#94a3b8" }}>
                      root <span style={styles.mono}>{selectedMission.workbench.root}</span>
                    </div>
                    <div style={{ marginTop: 12, ...styles.scrollArea }}>
                      {workbenchFilesForFolder.length ? (
                        workbenchFilesForFolder.map((file) => (
                          <div key={file.path} style={styles.recordCard}>
                            <div style={styles.recordMetaRow}>
                              <div>
                                <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0" }}>{file.name}</div>
                                <div style={styles.subtleText}>{file.path}</div>
                              </div>
                              <span style={styles.badge}>{file.bytes_label}</span>
                            </div>
                            <div style={{ marginTop: 8, fontSize: 12, color: "#94a3b8" }}>
                              modified {file.modified_at}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div style={styles.recordCard}>
                          No files yet in <span style={styles.mono}>{workbenchFolder}</span>.
                        </div>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div style={styles.recordCard}>
                  Select an expedition to inspect its mission brief, run summary, intake files, and workbench.
                </div>
              )}
            </div>
          </div>
        </div>

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
          {metricCard("Hermes Runs", hermesRuns.filter((item) => item.ok).length, "saved run JSON artifacts", FileText)}
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
                <h2 style={styles.sectionTitle}>Recent Hermes Runs</h2>
                <div style={styles.sectionSubtitle}>
                  Read-only run JSON artifacts from <span style={styles.mono}>logs/hermes/runs/</span>. This surface never executes Hermes and only mirrors saved run records.
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
                  No Hermes run JSON artifacts were found in <span style={styles.mono}>logs/hermes/runs/</span> yet.
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

