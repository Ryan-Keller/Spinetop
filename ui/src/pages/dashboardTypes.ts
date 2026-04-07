export type EventStatus = "created" | "promotable" | "success" | "error" | "skipped";

export type TopologyEvent = {
  timestamp: string;
  event_type: string;
  record_name: string;
  status: EventStatus | string;
  detail?: string;
  machine?: string;
};

export type HonchoSession = {
  id: string;
  is_active?: boolean;
  metadata?: {
    agent_id?: string;
    workspace?: string;
    created_by?: string;
  };
  created_at?: string;
};

export type HonchoPeer = {
  id: string;
  metadata?: {
    created_by?: string;
  };
};

export type ReturnAllState = {
  ok: boolean;
  enabled: boolean;
  issued_by: string;
  issued_at: string;
  reason: string;
  allow_custodial_bypass: boolean;
};

export type NannySignal = {
  id: string;
  level: "signal" | "issue" | string;
  title: string;
  cause: string;
  action_label: string;
  action_kind: string;
  severity?: "watch" | "bad" | string;
};

export type NannyLearningSummary = {
  stored_path?: string;
  updated_at?: string;
  counts?: Record<string, number>;
  weak_question_count?: number;
};

export type NannyWarning = string | { agent_id?: string; reason?: string };

export type NannyState = {
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

export type DispatchCounts = {
  pending: number;
  approved: number;
  deferred: number;
  rejected: number;
  total: number;
};

export type SupportHelperItem = {
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

export type SupportHelperActivity = {
  available: boolean;
  total: number;
  lane_counts: Record<string, number>;
  status_counts: Record<string, number>;
  items: SupportHelperItem[];
  source_dirs: Record<string, string>;
};

export type MirrorDoorFailure = {
  category: string;
  case_id: string;
  expected: string;
  actual: string;
  reason: string;
  attack_surface: string;
  source_file: string;
};

export type MirrorDoorTestStatus = {
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

export type Helper2bRuntimeStatus = {
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

export type StripTone = "good" | "watch" | "off";

export type StorageAreaSummary = {
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

export type StorageFootprint = {
  group_names: string[];
  total_bytes: number;
  total_bytes_label: string;
  total_files: number;
  groups: StorageAreaSummary[];
};

export type CollectiveDoorFootprint = {
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

export type StorageOverview = {
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

export type CompactorLastRunSummary = {
  ok?: boolean;
  timestamp?: string;
  groups_scanned?: number;
  groups_compacted?: number;
  records_compacted?: number;
  records_skipped?: number;
};

export type HermesRun = {
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

export type ReviewPreview = {
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

export type DraftRecord = {
  ok?: boolean;
  source_path?: string;
  draft?: ReviewPreview["draft"];
  review_preview?: ReviewPreview;
  error?: string;
};

export type RunnerReturn = {
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

export type ExpeditionStatusBadge = "waiting_for_user" | "researching" | "ready_for_review" | "idle";

export type ExpeditionSummary = {
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

export type ExpeditionGroup = {
  group_key: string;
  primary: ExpeditionSummary;
  items: ExpeditionSummary[];
  duplicate_count: number;
  hidden_duplicate_count: number;
};

export type FeedState = "ACTIVE" | "BLOCKED" | "RETURNED" | "PARKED";

export type DismissBucket = "archive" | "parked" | "duplicates";

export type ExpeditionGroupedCounts = {
  total_missions?: number;
  total_groups?: number;
  duplicate_groups?: number;
  duplicate_candidates?: number;
  hidden_duplicate_count?: number;
  queue_summary?: QueueSummary;
};

export type QueueSummary = {
  total_queued?: number;
  active?: number;
  parked?: number;
  blocked?: number;
  duplicate_candidates?: number;
  stale_candidates?: number;
  review_ready?: number;
  archive_close_candidates?: number;
};

export type MissionAttentionItem = {
  key: string;
  mission_id?: string;
  title: string;
  detail: string;
  badge: string;
  tone: StripTone;
};

export type CalibrationAxis = {
  key: string;
  label: string;
  value: number;
  hint: string;
};

export type MissionInputRecord = {
  input_id: string;
  mission_id: string;
  source_type: string;
  status: string;
  content: string;
  created_at: string;
  path: string;
};

export type WorkbenchFile = {
  path: string;
  folder: string;
  name: string;
  modified_at: string;
  bytes: number;
  bytes_label: string;
};

export type WorkbenchFolder = {
  name: string;
  path: string;
  available: boolean;
  file_count: number;
  newest_modified_at: string;
};

export type AssumptionConfirmation = {
  operator_status: string;
  operator_note: string;
  operator_updated_at: string;
};

export type AssumptionEntry = {
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

export type AssumptionChange = {
  assumption_id: string;
  text: string;
  status: string;
  updated_at: string;
  operator_status: string;
};

export type ControlTowerActivity = {
  role?: string;
  kind?: string;
  summary?: string;
  created_at?: string;
  source_ref?: string;
};

export type ControlTowerHandoff = {
  target_role?: string;
  allowed_action?: string;
  status?: string;
  reason?: string;
  updated_at?: string;
};

export type ControlTowerTrigger = {
  trigger_kind?: string;
  status?: string;
  created_at?: string;
  reason?: string;
};

export type ControlTowerIntervention = {
  intervention_id?: string;
  action?: string;
  status?: string;
  reason?: string;
  note?: string;
  blocked_reason?: string;
  created_at?: string;
  changed_paths?: string[];
};

export type ControlTowerExecutionRun = {
  run_id?: string;
  role?: string;
  status?: string;
  summary?: string;
  created_at?: string;
  source_ref?: string;
  origin?: string;
  origin_label?: string;
  trigger_reason?: string;
};

export type ControlTowerExecutionVisibility = {
  active_execution_now?: boolean;
  active_execution_status?: string;
  active_execution_role?: string;
  active_execution_action?: string;
  recent_runs_window?: number;
  recent_successful_run_count?: number;
  recent_successful_manual_run_count?: number;
  latest_successful_run?: ControlTowerExecutionRun | null;
  latest_successful_manual_run?: ControlTowerExecutionRun | null;
  autonomy_governance_blocked?: boolean;
  governance_block_reason?: string;
  summary_lines?: string[];
};

export type ControlTowerSummary = {
  autonomy_state?: string;
  last_trigger?: ControlTowerTrigger | null;
  last_trigger_outcome?: string;
  retry_budget?: number;
  retry_used?: number;
  last_retry_reason?: string;
  last_blocked_reason?: string;
  active_role_handoff?: ControlTowerHandoff | null;
  latest_role_activity?: ControlTowerActivity | null;
  execution_visibility?: ControlTowerExecutionVisibility | null;
  operator_attention_reason?: string;
  recent_operator_interventions?: ControlTowerIntervention[];
  safe_operator_actions?: string[];
};

export type WorkbenchSummary = {
  root: string;
  folders: WorkbenchFolder[];
  files: WorkbenchFile[];
};

export type PromptTranslation = {
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

export type ExpeditionDetail = {
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

export type MissionChatMessage = {
  message_id: string;
  mission_id: string;
  sender: "user" | "assistant";
  role: string;
  message: string;
  tone: "good" | "watch" | "info" | "bad";
  created_at: string;
  kind: string;
};

export type StatusResponse = {
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

export type ExpeditionsResponse = {
  ok: boolean;
  source_root?: string;
  items: ExpeditionSummary[];
  grouped_counts?: ExpeditionGroupedCounts;
  queue_summary?: QueueSummary;
};

export type ExpeditionDetailResponse = {
  ok: boolean;
  available: boolean;
  item: ExpeditionDetail | null;
  error?: string;
};

export type NoticeTone = "good" | "watch" | "bad" | "info";

export type UiNotice = {
  tone: NoticeTone;
  title: string;
  detail: string;
};
