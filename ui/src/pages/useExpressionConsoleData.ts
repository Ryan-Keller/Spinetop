import { useEffect, useState } from "react";

import type {
  ExpeditionDetail,
  ExpeditionDetailResponse,
  ExpeditionsResponse,
  ExpeditionSummary,
  MissionChatMessage,
} from "./dashboardTypes";

const API_BASE = (import.meta.env.VITE_SPINETOP_API_BASE as string | undefined)?.trim() || "/api";

type ExpeditionStateItem = {
  mission_id: string;
  objective: string;
  current_state: string;
  operator_posture: string;
  autonomy_state: string;
  blocked_reason?: string | null;
  latest_meaningful_activity?: {
    kind?: string;
    role?: string;
    summary?: string;
    created_at?: string;
    artifact_ref?: string;
  } | null;
  recommended_next_step: string;
};

type TimelineAgentRun = {
  run_id: string;
  role: string;
  status: string;
  summary: string;
  trigger_reason: string;
  created_at: string;
  artifact_ref: string;
};

type TimelineTrigger = {
  trigger_id: string;
  trigger_kind: string;
  status: string;
  reason: string;
  target_role: string;
  allowed_action: string;
  created_at: string;
  blocked_reason?: string | null;
  artifact_ref: string;
};

type TimelineIntervention = {
  intervention_id: string;
  action: string;
  status: string;
  reason: string;
  blocked_reason?: string | null;
  created_at: string;
  artifact_refs: string[];
};

type ExpeditionTimelineItem = {
  mission_id: string;
  recent_agent_runs: TimelineAgentRun[];
  recent_triggers: TimelineTrigger[];
  recent_interventions: TimelineIntervention[];
};

type ExpeditionInterpretationItem = {
  summary: string;
  patterns: string[];
  contradictions: string[];
  suggested_focus: string[];
};

type ExpeditionSignalsItem = {
  mission_id: string;
  activity?: {
    status?: string;
    kind?: string;
    role?: string;
    summary?: string;
    created_at?: string;
  } | null;
  blocked?: {
    present?: boolean;
    reason?: string;
    operator_posture?: string;
    autonomy_state?: string;
  } | null;
  contradiction?: {
    present?: boolean;
    count?: number;
    summary?: string;
  } | null;
  stall?: {
    present?: boolean;
    summary?: string;
    last_activity_at?: string;
    last_activity_age_days?: number | null;
  } | null;
  handoff?: {
    present?: boolean;
    status?: string;
    target_role?: string;
    allowed_action?: string;
    reason?: string;
    updated_at?: string;
  } | null;
};

type BasicResponse<T> = {
  ok: boolean;
  item: T;
  available?: boolean;
  reason?: string;
  error?: string;
};

type ChatResponse = {
  ok: boolean;
  item?: ExpeditionDetail | null;
  messages?: MissionChatMessage[];
  error?: string;
};

type ExtendedExpeditionDetail = ExpeditionDetail & {
  working_memory?: Record<string, unknown>;
  mirror_notes?: Array<{
    summary?: string;
    role?: string;
    kind?: string;
    created_at?: string;
    path?: string;
  }>;
  mission_agent?: Record<string, unknown>;
  latest_trigger?: Record<string, unknown> | null;
};

type RequestState<T> = {
  item: T | null;
  available: boolean;
  reason?: string;
};

const emptyTimeline: ExpeditionTimelineItem = {
  mission_id: "",
  recent_agent_runs: [],
  recent_triggers: [],
  recent_interventions: [],
};

const isVisible = () => typeof document === "undefined" || document.visibilityState !== "hidden";

export function useExpressionConsoleData() {
  const [expeditions, setExpeditions] = useState<ExpeditionSummary[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string>("");
  const [mission, setMission] = useState<ExtendedExpeditionDetail | null>(null);
  const [state, setState] = useState<RequestState<ExpeditionStateItem>>({ item: null, available: false });
  const [timeline, setTimeline] = useState<RequestState<ExpeditionTimelineItem>>({ item: emptyTimeline, available: false });
  const [interpretation, setInterpretation] = useState<RequestState<ExpeditionInterpretationItem>>({ item: null, available: false });
  const [signals, setSignals] = useState<RequestState<ExpeditionSignalsItem>>({ item: null, available: false });
  const [messages, setMessages] = useState<MissionChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [refreshTick, setRefreshTick] = useState(Date.now());

  const loadJson = async <T,>(url: string, init?: RequestInit): Promise<T> => {
    const res = await fetch(url, init);
    const payload = (await res.json().catch(() => ({}))) as T & { error?: string };
    if (!res.ok) {
      const detail = typeof (payload as { error?: string }).error === "string" ? (payload as { error?: string }).error : `HTTP ${res.status}`;
      throw new Error(detail);
    }
    return payload;
  };

  const loadExpeditions = async () => {
    const response = await loadJson<ExpeditionsResponse>(`${API_BASE}/expeditions`);
    const items = Array.isArray(response.items) ? response.items : [];
    setExpeditions(items);
    setSelectedMissionId((current) => {
      if (current && items.some((item) => item.mission_id === current)) return current;
      return items[0]?.mission_id || "";
    });
  };

  const loadMissionBundle = async (missionId: string) => {
    const [detailResponse, stateResponse, timelineResponse, interpretationResponse, signalsResponse, chatResponse] = await Promise.all([
      loadJson<ExpeditionDetailResponse>(`${API_BASE}/expeditions/${missionId}`),
      loadJson<BasicResponse<ExpeditionStateItem>>(`${API_BASE}/expeditions/${missionId}/state`),
      loadJson<BasicResponse<ExpeditionTimelineItem>>(`${API_BASE}/expeditions/${missionId}/timeline`),
      loadJson<BasicResponse<ExpeditionInterpretationItem | null>>(`${API_BASE}/expeditions/${missionId}/interpretation`),
      loadJson<BasicResponse<ExpeditionSignalsItem>>(`${API_BASE}/expeditions/${missionId}/signals`),
      loadJson<ChatResponse>(`${API_BASE}/expeditions/${missionId}/chat`),
    ]);

    setMission(detailResponse.ok && detailResponse.item ? (detailResponse.item as ExtendedExpeditionDetail) : null);
    setState({
      item: stateResponse.item,
      available: stateResponse.ok,
      reason: stateResponse.reason,
    });
    setTimeline({
      item: timelineResponse.item || emptyTimeline,
      available: timelineResponse.ok,
      reason: timelineResponse.reason,
    });
    setInterpretation({
      item: interpretationResponse.item || null,
      available: Boolean(interpretationResponse.available ?? interpretationResponse.item),
      reason: interpretationResponse.reason,
    });
    setSignals({
      item: signalsResponse.item,
      available: signalsResponse.ok,
      reason: signalsResponse.reason,
    });
    setMessages(Array.isArray(chatResponse.messages) ? chatResponse.messages : []);
  };

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      if (!isVisible()) return;
      setLoading(true);
      try {
        await loadExpeditions();
        if (!cancelled) setError("");
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load expeditions.");
          setExpeditions([]);
          setSelectedMissionId("");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();
    const interval = window.setInterval(() => {
      if (!isVisible()) return;
      void loadExpeditions().catch(() => {});
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!selectedMissionId) {
      setMission(null);
      setState({ item: null, available: false });
      setTimeline({ item: emptyTimeline, available: false });
      setInterpretation({ item: null, available: false });
      setSignals({ item: null, available: false });
      setMessages([]);
      return;
    }

    let cancelled = false;

    const run = async () => {
      if (!isVisible()) return;
      try {
        await loadMissionBundle(selectedMissionId);
        if (!cancelled) {
          setError("");
          setRefreshTick(Date.now());
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load console state.");
        }
      }
    };

    void run();
    const interval = window.setInterval(() => {
      if (!isVisible()) return;
      void run();
    }, 8000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [selectedMissionId]);

  const sendMessage = async (content: string) => {
    if (!selectedMissionId || !content.trim()) return false;
    setSending(true);
    try {
      const response = await loadJson<ChatResponse>(`${API_BASE}/expeditions/${selectedMissionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (response.item) setMission(response.item as ExtendedExpeditionDetail);
      if (Array.isArray(response.messages)) setMessages(response.messages);
      setRefreshTick(Date.now());
      setError("");
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to send message.");
      return false;
    } finally {
      setSending(false);
    }
  };

  return {
    expeditions,
    selectedMissionId,
    setSelectedMissionId,
    mission,
    state,
    timeline,
    interpretation,
    signals,
    messages,
    loading,
    sending,
    error,
    refreshTick,
    sendMessage,
  };
}
