import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { isMissionParked, missionFeedState } from "./dashboardSelectors";
import type {
  DraftRecord,
  ExpeditionDetail,
  ExpeditionDetailResponse,
  ExpeditionSummary,
  ExpeditionsResponse,
  HermesRun,
  QueueSummary,
  StatusResponse,
} from "./dashboardTypes";

type LoadOptions = { preserveScroll?: boolean };

type ScrollSnapshot = {
  left: number;
  top: number;
};

type UseDashboardDataArgs = {
  apiBase: string;
  fallbackData: StatusResponse;
  fallbackExpeditions: ExpeditionSummary[];
  workbenchFolder: string;
  setWorkbenchFolder: Dispatch<SetStateAction<string>>;
};

export function useDashboardData(args: UseDashboardDataArgs) {
  const [data, setData] = useState<StatusResponse>(args.fallbackData);
  const [hermesRuns, setHermesRuns] = useState<HermesRun[]>([]);
  const [petitionDrafts, setPetitionDrafts] = useState<DraftRecord[]>([]);
  const [expeditions, setExpeditions] = useState<ExpeditionSummary[]>(args.fallbackExpeditions);
  const [expeditionQueueSummary, setExpeditionQueueSummary] = useState<QueueSummary>({});
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [selectedMission, setSelectedMission] = useState<ExpeditionDetail | null>(null);
  const [missionDetailsById, setMissionDetailsById] = useState<Record<string, ExpeditionDetail>>({});
  const [loading, setLoading] = useState(false);
  const [missionLoading, setMissionLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState("demo data");
  const [errorText, setErrorText] = useState("");

  const hasInitializedMissionSelectionRef = useRef(false);
  const selectedMissionIdRef = useRef<string | null>(null);
  const pendingScrollRestoreRef = useRef<ScrollSnapshot | null>(null);
  const loadPromiseRef = useRef<Promise<void> | null>(null);
  const lastAppliedLoadIdRef = useRef(0);
  const committedLoadIdRef = useRef(0);

  const loadJson = async <T,>(url: string): Promise<T> => {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  };

  useEffect(() => {
    selectedMissionIdRef.current = selectedMissionId;
  }, [selectedMissionId]);

  const getScrollElement = () =>
    document.scrollingElement instanceof HTMLElement ? document.scrollingElement : document.documentElement;

  const captureScrollSnapshot = (): ScrollSnapshot => {
    const scrollElement = getScrollElement();
    return {
      left: scrollElement.scrollLeft,
      top: scrollElement.scrollTop,
    };
  };

  const mergeMissionDetail = (detail: ExpeditionDetail) => {
    setMissionDetailsById((prev) => ({ ...prev, [detail.mission_id]: detail }));
    if (selectedMissionIdRef.current === detail.mission_id) {
      setSelectedMission(detail);
      const folders = detail.workbench?.folders || [];
      if (folders.length && !folders.some((folder) => folder.name === args.workbenchFolder)) {
        args.setWorkbenchFolder(folders[0].name);
      }
    }
  };

  const loadMissionDetail = async (missionId: string) => {
    const response = await loadJson<ExpeditionDetailResponse>(`${args.apiBase}/expeditions/${missionId}`);
    if (response.ok && response.item) {
      mergeMissionDetail(response.item);
      return response.item;
    }
    return null;
  };

  const load = async (options?: LoadOptions) => {
    if (loadPromiseRef.current) return loadPromiseRef.current;
    if (options?.preserveScroll) {
      pendingScrollRestoreRef.current = captureScrollSnapshot();
    }
    const loadId = lastAppliedLoadIdRef.current + 1;
    lastAppliedLoadIdRef.current = loadId;
    const promise = (async () => {
      setLoading(true);
      try {
        const missionIdAtLoadStart = selectedMissionIdRef.current;
        const [statusResult, runsResult, draftsResult, expeditionsResult, selectedMissionResult] = await Promise.all([
          loadJson<StatusResponse>(`${args.apiBase}/status`).then((value) => ({ ok: true as const, value })).catch((error) => ({ ok: false as const, error })),
          loadJson<{ ok: boolean; items: HermesRun[] }>(`${args.apiBase}/hermes/runs?limit=6`).then((value) => ({ ok: true as const, value })).catch((error) => ({ ok: false as const, error })),
          loadJson<{ ok: boolean; items: DraftRecord[] }>(`${args.apiBase}/petition-drafts?limit=6`).then((value) => ({ ok: true as const, value })).catch((error) => ({ ok: false as const, error })),
          loadJson<ExpeditionsResponse>(`${args.apiBase}/expeditions`).then((value) => ({ ok: true as const, value })).catch((error) => ({ ok: false as const, error })),
          missionIdAtLoadStart
            ? loadJson<ExpeditionDetailResponse>(`${args.apiBase}/expeditions/${missionIdAtLoadStart}`).then((value) => ({ ok: true as const, value, missionId: missionIdAtLoadStart })).catch((error) => ({ ok: false as const, error, missionId: missionIdAtLoadStart }))
            : Promise.resolve({ ok: true as const, value: null, missionId: null }),
        ]);

        if (loadId !== lastAppliedLoadIdRef.current) return;

        const errors: string[] = [];

        if (statusResult.ok) {
          setData(statusResult.value);
        } else {
          setData(args.fallbackData);
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
          setExpeditionQueueSummary(expeditionsResult.value.queue_summary || expeditionsResult.value.grouped_counts?.queue_summary || {});
          setMissionDetailsById((prev) => {
            const next: Record<string, ExpeditionDetail> = {};
            const activeIds = new Set(items.map((item) => item.mission_id));
            for (const [missionId, detail] of Object.entries(prev)) {
              if (activeIds.has(missionId)) next[missionId] = detail;
            }
            return next;
          });
          if (missionIdAtLoadStart && !items.some((item) => item.mission_id === missionIdAtLoadStart)) {
            setSelectedMissionId((current) => (current === missionIdAtLoadStart ? null : current));
            setSelectedMission((current) => (current?.mission_id === missionIdAtLoadStart ? null : current));
          }
        } else {
          setExpeditions([]);
          setExpeditionQueueSummary({});
          errors.push(`expeditions: ${expeditionsResult.error instanceof Error ? expeditionsResult.error.message : "request failed"}`);
        }

        if (selectedMissionResult.ok && selectedMissionResult.value?.ok && selectedMissionResult.value.item && selectedMissionResult.missionId) {
          mergeMissionDetail(selectedMissionResult.value.item);
        }

        setErrorText(errors.length ? `Using fallback data - ${errors.join(" | ")}` : "");
        setLastRefresh(new Date().toLocaleTimeString());
        committedLoadIdRef.current = loadId;
      } catch (err) {
        if (loadId !== lastAppliedLoadIdRef.current) return;
        setData(args.fallbackData);
        setErrorText(`Using fallback data - ${err instanceof Error ? err.message : "request failed"}`);
        setLastRefresh("fallback mode");
        setHermesRuns([]);
        setPetitionDrafts([]);
        setExpeditions([]);
        setExpeditionQueueSummary({});
        setSelectedMission(null);
        committedLoadIdRef.current = loadId;
      } finally {
        if (loadId === lastAppliedLoadIdRef.current) {
          setLoading(false);
        }
        loadPromiseRef.current = null;
      }
    })();
    loadPromiseRef.current = promise;
    return promise;
  };

  useLayoutEffect(() => {
    const pending = pendingScrollRestoreRef.current;
    if (!pending || loading) return;
    if (committedLoadIdRef.current === 0) return;
    pendingScrollRestoreRef.current = null;

    const scrollElement = getScrollElement();
    const apply = () => {
      const currentTop = scrollElement.scrollTop;
      const currentLeft = scrollElement.scrollLeft;
      if (Math.abs(currentTop - pending.top) <= 1 && Math.abs(currentLeft - pending.left) <= 1) return;
      scrollElement.scrollTo({ top: pending.top, left: pending.left, behavior: "auto" });
    };

    apply();
    const frame = window.requestAnimationFrame(apply);
    return () => window.cancelAnimationFrame(frame);
  }, [loading, expeditions, selectedMission]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load({ preserveScroll: true });
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (selectedMissionId && expeditions.some((item) => item.mission_id === selectedMissionId)) {
      hasInitializedMissionSelectionRef.current = true;
      return;
    }
    if (selectedMissionId && !expeditions.some((item) => item.mission_id === selectedMissionId)) {
      setSelectedMissionId(null);
      setSelectedMission(null);
      return;
    }
    if (!selectedMissionId && !hasInitializedMissionSelectionRef.current) {
      const defaultMissionId =
        expeditions.find((item) => missionFeedState(item) === "ACTIVE")?.mission_id ||
        expeditions.find((item) => !isMissionParked(item))?.mission_id ||
        null;
      if (defaultMissionId) {
        hasInitializedMissionSelectionRef.current = true;
        setSelectedMissionId(defaultMissionId);
      }
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
    loadMissionDetail(selectedMissionId)
      .then((item) => {
        if (cancelled) return;
        if (!item) setSelectedMission(null);
      })
      .catch(() => {
        if (!cancelled) setSelectedMission(null);
      })
      .finally(() => {
        if (!cancelled) setMissionLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedMissionId]);

  return {
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
  };
}
