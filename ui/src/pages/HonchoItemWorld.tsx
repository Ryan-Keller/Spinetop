
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Gem,
  Layers3,
  Orbit,
  Pickaxe,
  Sparkles,
  Users,
} from "lucide-react";

type TopologyEvent = {
  timestamp: string;
  event_type: string;
  record_name: string;
  status: string;
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

type StatusResponse = {
  ok: boolean;
  workspace_id: string;
  honcho_sessions_total: number;
  honcho_peers_total: number;
  honcho_sessions: HonchoSession[];
  honcho_peers: HonchoPeer[];
  events_recent: TopologyEvent[];
};

type GemSpec = {
  name: string;
  glow: string;
  fill: string;
  border: string;
};

const GEM_MAP: Record<string, GemSpec> = {
  hermes_write: {
    name: "Topaz",
    glow: "0 0 18px rgba(251,191,36,0.35)",
    fill: "rgba(251,191,36,0.2)",
    border: "rgba(251,191,36,0.4)",
  },
  promote: {
    name: "Emerald",
    glow: "0 0 18px rgba(16,185,129,0.35)",
    fill: "rgba(16,185,129,0.15)",
    border: "rgba(16,185,129,0.4)",
  },
  watcher_scan: {
    name: "Emerald",
    glow: "0 0 18px rgba(16,185,129,0.35)",
    fill: "rgba(16,185,129,0.15)",
    border: "rgba(16,185,129,0.4)",
  },
  approve: {
    name: "Sapphire",
    glow: "0 0 18px rgba(96,165,250,0.35)",
    fill: "rgba(96,165,250,0.15)",
    border: "rgba(96,165,250,0.4)",
  },
  honcho_bridge: {
    name: "Amethyst",
    glow: "0 0 18px rgba(192,132,252,0.35)",
    fill: "rgba(192,132,252,0.15)",
    border: "rgba(192,132,252,0.4)",
  },
  error: {
    name: "Obsidian",
    glow: "0 0 18px rgba(15,23,42,0.55)",
    fill: "rgba(100,116,139,0.25)",
    border: "rgba(148,163,184,0.3)",
  },
  skipped: {
    name: "Obsidian",
    glow: "0 0 18px rgba(15,23,42,0.55)",
    fill: "rgba(100,116,139,0.25)",
    border: "rgba(148,163,184,0.3)",
  },
};

const STAGE_X = [10, 36, 58, 82];
const GEM_COLORS: Record<string, string> = {
  hermes_write: "#fbbf24",
  promote: "#10b981",
  watcher_scan: "#10b981",
  approve: "#60a5fa",
  honcho_bridge: "#c084fc",
  error: "#475569",
  skipped: "#475569",
};

const API_BASE = (import.meta.env.VITE_SPINETOP_API_BASE as string | undefined)?.trim() || "/api";

const styles = {
  page: {
    minHeight: "100vh",
    background: "#0b1220",
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
  headerRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    alignItems: "center",
    gap: 8,
  } as const,
  pill: {
    borderRadius: 999,
    padding: "6px 12px",
    fontSize: 12,
  } as const,
  panel: {
    borderRadius: 24,
    border: "1px solid rgba(168,85,247,0.2)",
    background: "rgba(15,23,42,0.9)",
    padding: 20,
  } as const,
  split: {
    display: "grid",
    gap: 24,
    gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 0.8fr)",
  } as const,
};

function stageFromEvents(events: TopologyEvent[]) {
  if (events.some((e) => e.event_type === "honcho_bridge" && e.status === "success")) return 3;
  if (events.some((e) => e.event_type === "approve" && e.status === "success")) return 2;
  if (
    events.some((e) => e.event_type === "promote" && e.status === "success") ||
    events.some((e) => e.event_type === "watcher_scan")
  ) {
    return 1;
  }
  return 0;
}

function groupByRecord(events: TopologyEvent[]) {
  const map = new Map<string, TopologyEvent[]>();
  for (const event of events) {
    if (!map.has(event.record_name)) map.set(event.record_name, []);
    map.get(event.record_name)!.push(event);
  }
  return Array.from(map.entries()).map(([recordName, recordEvents]) => {
    const sorted = [...recordEvents].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const latest = sorted[sorted.length - 1];
    const failed = sorted.some((e) => e.status === "error" || e.status === "skipped");
    const stage = stageFromEvents(sorted);
    const gemKey = failed ? "error" : latest.event_type;
    const gem = GEM_MAP[gemKey] ?? GEM_MAP.hermes_write;
    return {
      recordName,
      events: sorted,
      latest,
      failed,
      stage,
      gem,
      intensity: Math.min(1, 0.35 + sorted.length * 0.12),
    };
  });
}

function countByEventType(events: TopologyEvent[]) {
  return events.reduce<Record<string, number>>((acc, event) => {
    acc[event.event_type] = (acc[event.event_type] ?? 0) + 1;
    return acc;
  }, {});
}

function buildPatternCandidates(records: ReturnType<typeof groupByRecord>) {
  return records
    .filter((rec) => rec.events.length > 1)
    .map((rec) => {
      const types = rec.events.map((e) => e.event_type);
      const repeated = types.filter((t) => t === types[types.length - 1]).length;
      const sequence = rec.events.map((e) => `${e.event_type}:${e.status}`);
      const pattern =
        repeated >= 2
          ? `Repeated ${types[types.length - 1]} x${repeated}`
          : `Sequence: ${types.slice(0, 3).join(" ? ")}${types.length > 3 ? " …" : ""}`;
      return {
        recordName: rec.recordName,
        sequence,
        pattern,
        eventCount: rec.events.length,
      };
    })
    .slice(0, 6);
}

function tileStyleForTypes(types: string[]) {
  const unique = Array.from(new Set(types));
  if (unique.length === 0) {
    return { background: "rgba(15,23,42,0.6)" };
  }
  if (unique.length === 1) {
    const color = GEM_COLORS[unique[0]] ?? "#fbbf24";
    return { background: `rgba(${hexToRgb(color)}, 0.18)` };
  }
  const first = GEM_COLORS[unique[0]] ?? "#fbbf24";
  const second = GEM_COLORS[unique[1]] ?? "#60a5fa";
  return {
    background: `linear-gradient(120deg, rgba(${hexToRgb(first)},0.22), rgba(${hexToRgb(second)},0.22))`,
  };
}

function hexToRgb(hex: string) {
  const cleaned = hex.replace("#", "");
  const value = parseInt(cleaned, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `${r},${g},${b}`;
}

export default function HonchoItemWorld() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [errorText, setErrorText] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);
  const [hovered, setHovered] = useState<TopologyEvent | null>(null);
  const [selectedGem, setSelectedGem] = useState<string | null>(null);
  const [openInsight, setOpenInsight] = useState<{
    recordName: string;
    sequence: string[];
    pattern: string;
  } | null>(null);

  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as StatusResponse;
      setData(json);
      setErrorText("");
    } catch (err) {
      setErrorText(`Unable to reach /api/status — ${err instanceof Error ? err.message : "request failed"}`);
      setData(null);
    }
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 6000);
    return () => window.clearInterval(timer);
  }, []);

  const events = data?.events_recent ?? [];
  const records = useMemo(() => groupByRecord(events), [events]);
  const eventCounts = useMemo(() => countByEventType(events), [events]);
  const insights = useMemo(() => buildPatternCandidates(records), [records]);
  const bridgeSuccess = events.filter((e) => e.event_type === "honcho_bridge" && e.status === "success").length;
  const bridgeFailures = events.filter((e) => e.event_type === "honcho_bridge" && e.status !== "success").length;
  const selected = records.find((rec) => rec.recordName === selectedRecord) ?? records[0];
  const eventCountLabel = data ? events.length : "—";

  useEffect(() => {
    if (!selectedRecord && records[0]) {
      setSelectedRecord(records[0].recordName);
    }
  }, [records, selectedRecord]);

  const selectedStages = useMemo(() => {
    if (!selected) return [false, false, false, false];
    const hasWrite = selected.events.some((e) => e.event_type === "hermes_write");
    const hasPromote =
      selected.events.some((e) => e.event_type === "promote" && e.status === "success") ||
      selected.events.some((e) => e.event_type === "watcher_scan");
    const hasApprove = selected.events.some((e) => e.event_type === "approve" && e.status === "success");
    const hasBridge = selected.events.some((e) => e.event_type === "honcho_bridge" && e.status === "success");
    return [hasWrite, hasPromote, hasApprove, hasBridge];
  }, [selected]);

  const gemEntries = useMemo(
    () => [
      { label: "Topaz", key: "hermes_write", count: eventCounts.hermes_write ?? 0 },
      {
        label: "Emerald",
        key: "promote",
        count: (eventCounts.promote ?? 0) + (eventCounts.watcher_scan ?? 0),
      },
      { label: "Sapphire", key: "approve", count: eventCounts.approve ?? 0 },
      { label: "Amethyst", key: "honcho_bridge", count: eventCounts.honcho_bridge ?? 0 },
      {
        label: "Obsidian",
        key: "obsidian",
        count: events.filter((e) => e.status === "error" || e.status === "skipped").length,
      },
    ],
    [eventCounts, events]
  );

  const miningTiles = useMemo(() => {
    const buckets = records.map((rec) => ({
      id: rec.recordName,
      count: rec.events.length,
      types: rec.events.map((e) => e.event_type),
    }));
    return buckets.slice(0, 16);
  }, [records]);

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <header style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={styles.headerRow}>
            <span
              style={{
                ...styles.pill,
                background: "#7c3aed",
                color: "#fff",
                fontWeight: 600,
              }}
            >
              Honcho Item World
            </span>
            <span
              style={{
                ...styles.pill,
                border: "1px solid rgba(168,85,247,0.4)",
                background: "rgba(88,28,135,0.4)",
                color: "#e9d5ff",
              }}
            >
              workspace: {data?.workspace_id ?? "—"}
            </span>
            <span
              style={{
                ...styles.pill,
                border: "1px solid rgba(148,163,184,0.4)",
                background: "rgba(15,23,42,0.6)",
                color: "#cbd5f5",
              }}
            >
              sessions: {data?.honcho_sessions_total ?? "—"}
            </span>
            <span
              style={{
                ...styles.pill,
                border: "1px solid rgba(148,163,184,0.4)",
                background: "rgba(15,23,42,0.6)",
                color: "#cbd5f5",
              }}
            >
              peers: {data?.honcho_peers_total ?? "—"}
            </span>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 16 }}>
            <div>
              <h1 style={{ fontSize: 32, fontWeight: 600, color: "#e9d5ff", margin: 0 }}>
                Memory Mine Explorer
              </h1>
              <p style={{ marginTop: 8, color: "#cbd5f5", maxWidth: 720 }}>
                Underground, torchlit visualization of Honcho memory signals. Everything here is exploratory and never writes to collective.
              </p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#94a3b8" }}>
              <Pickaxe size={16} color="#fbbf24" />
              Live from /api/status
            </div>
          </div>

          {errorText ? (
            <div
              style={{
                borderRadius: 16,
                border: "1px solid rgba(251,191,36,0.4)",
                background: "rgba(120,53,15,0.2)",
                padding: "10px 14px",
                fontSize: 12,
                color: "#fde68a",
              }}
            >
              {errorText}
            </div>
          ) : null}
        </header>

        <section style={styles.split}>
          <div style={styles.panel}>
            <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ fontSize: 20, fontWeight: 600, color: "#e9d5ff" }}>Mine Overview</div>
                <div style={{ fontSize: 12, color: "#94a3b8" }}>
                  Nodes spawn at the entrance and drift toward the Honcho portal as events progress.
                </div>
              </div>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  borderRadius: 999,
                  border: "1px solid rgba(168,85,247,0.3)",
                  background: "rgba(88,28,135,0.4)",
                  padding: "4px 10px",
                  fontSize: 11,
                  color: "#e9d5ff",
                }}
              >
                <Activity size={14} />
                {eventCountLabel} events
              </div>
            </div>

            <div
              style={{
                position: "relative",
                height: 360,
                overflow: "hidden",
                borderRadius: 24,
                border: "1px solid rgba(168,85,247,0.2)",
                background: "radial-gradient(circle at top, #2d1b3f 0%, #0f172a 48%, #020617 100%)",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 40,
                  left: 0,
                  right: 0,
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "0 40px",
                  fontSize: 10,
                  letterSpacing: "0.3em",
                  textTransform: "uppercase",
                  color: "#64748b",
                }}
              >
                <span>Entrance</span>
                <span>Inner Gate</span>
                <span>Truth Cluster</span>
                <span>Portal</span>
              </div>

              {records.length === 0 ? (
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: "#94a3b8" }}>
                  Waiting for live events from /api/status
                </div>
              ) : null}

              {records.map((rec, idx) => {
                const y = 72 + (idx % 8) * 28;
                const x = STAGE_X[Math.min(rec.stage, 3)];
                const isSelected = rec.recordName === selected?.recordName;
                const flicker = rec.failed;

                return (
                  <motion.button
                    key={rec.recordName}
                    type="button"
                    onClick={() => setSelectedRecord(rec.recordName)}
                    onMouseEnter={() => setHovered(rec.latest)}
                    onMouseLeave={() => setHovered(null)}
                    style={{
                      position: "absolute",
                      top: y,
                      left: `${x}%`,
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                    }}
                    animate={
                      records.length
                        ? {
                            scale: isSelected ? [1, 1.08, 1] : [0.9, 1, 0.92],
                            opacity: flicker ? [0.4, 1, 0.6] : [0.6, 0.95, 0.7],
                          }
                        : undefined
                    }
                    transition={{ duration: 3 + (idx % 3) * 0.3, repeat: Infinity }}
                  >
                    <div
                      style={{
                        borderRadius: 16,
                        border: `1px solid ${rec.gem.border}`,
                        background: rec.gem.fill,
                        padding: "4px 10px",
                        fontSize: 11,
                        fontWeight: 600,
                        color: "#f5f3ff",
                        boxShadow: rec.gem.glow,
                      }}
                    >
                      {rec.gem.name}
                    </div>
                  </motion.button>
                );
              })}

              <div style={{ position: "absolute", top: 0, bottom: 0, right: 32, display: "flex", alignItems: "center" }}>
                <motion.div
                  style={{
                    position: "relative",
                    height: 160,
                    width: 160,
                    borderRadius: "50%",
                    border: "1px solid rgba(192,132,252,0.4)",
                    background: "rgba(192,132,252,0.1)",
                    boxShadow: `0 0 ${22 + bridgeSuccess * 6}px rgba(192,132,252,0.35)`,
                  }}
                  animate={
                    bridgeSuccess > 0
                      ? { scale: [0.94, 1.06, 0.98], opacity: [0.7, 1, 0.85] }
                      : { opacity: 0.5 }
                  }
                  transition={{ duration: 3.6, repeat: Infinity }}
                >
                  <div style={{ position: "absolute", inset: "18%", borderRadius: "50%", border: "1px solid rgba(96,165,250,0.3)" }} />
                  <div style={{ position: "absolute", inset: "34%", borderRadius: "50%", border: "1px solid rgba(251,191,36,0.3)" }} />
                  <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32 }}>
                    ??
                  </div>
                  {bridgeFailures > 0 ? (
                    <div style={{ position: "absolute", inset: -10, borderRadius: "50%", border: "1px solid rgba(251,113,133,0.4)" }} />
                  ) : null}
                </motion.div>
              </div>

              {selected ? (
                <div style={{ position: "absolute", left: 40, right: 40, bottom: 32 }}>
                  <div style={{ position: "relative", height: 32 }}>
                    <div style={{ position: "absolute", left: 0, right: 0, top: "50%", height: 1, background: "rgba(71,85,105,0.6)" }} />
                    {["Entrance", "Inner Gate", "Truth", "Portal"].map((label, index) => (
                      <div
                        key={label}
                        style={{ position: "absolute", transform: "translateX(-50%)", left: `${STAGE_X[index]}%`, top: "50%" }}
                      >
                        <div
                          style={{
                            height: 10,
                            width: 10,
                            borderRadius: "50%",
                            border: selectedStages[index]
                              ? "1px solid rgba(251,191,36,0.7)"
                              : "1px solid rgba(100,116,139,0.6)",
                            background: selectedStages[index]
                              ? "rgba(251,191,36,0.6)"
                              : "rgba(30,41,59,0.6)",
                          }}
                        />
                        <div style={{ marginTop: 6, fontSize: 10, color: "#94a3b8" }}>{label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {hovered ? (
                <div
                  style={{
                    position: "absolute",
                    left: 24,
                    bottom: 24,
                    maxWidth: 280,
                    borderRadius: 16,
                    border: "1px solid rgba(168,85,247,0.3)",
                    background: "rgba(2,6,23,0.8)",
                    padding: 12,
                    fontSize: 11,
                    color: "#e2e8f0",
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#e9d5ff" }}>{hovered.event_type}</div>
                  <div style={{ marginTop: 4, color: "#cbd5f5", wordBreak: "break-all" }}>{hovered.record_name}</div>
                  <div style={{ marginTop: 4, color: "#94a3b8" }}>{hovered.status}</div>
                  <div style={{ marginTop: 4, color: "#64748b" }}>{hovered.timestamp}</div>
                </div>
              ) : null}
            </div>

            <div style={{ marginTop: 20, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
              {gemEntries.map((entry) => (
                <button
                  key={entry.label}
                  type="button"
                  onClick={() => setSelectedGem(entry.key)}
                  style={{
                    borderRadius: 16,
                    border: selectedGem === entry.key ? "1px solid rgba(251,191,36,0.6)" : "1px solid rgba(168,85,247,0.2)",
                    background: selectedGem === entry.key ? "rgba(251,191,36,0.1)" : "rgba(15,23,42,0.8)",
                    padding: 12,
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12, color: "#94a3b8" }}>
                    <span>{entry.label}</span>
                    <Gem size={16} color="#e9d5ff" />
                  </div>
                  <div style={{ marginTop: 8, fontSize: 22, fontWeight: 600, color: "#e9d5ff" }}>{entry.count}</div>
                </button>
              ))}
            </div>

            {selectedGem ? (
              <div style={{ marginTop: 16, borderRadius: 16, border: "1px solid rgba(168,85,247,0.2)", background: "rgba(2,6,23,0.6)", padding: 16 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#e9d5ff" }}>Gemstone Cluster</div>
                  <button
                    type="button"
                    onClick={() => setSelectedGem(null)}
                    style={{ fontSize: 11, color: "#94a3b8", background: "transparent", border: "none", cursor: "pointer" }}
                  >
                    Clear
                  </button>
                </div>
                <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8, fontSize: 11, color: "#cbd5f5" }}>
                  {events
                    .filter((event) => {
                      if (selectedGem === "obsidian") {
                        return event.status === "error" || event.status === "skipped";
                      }
                      if (selectedGem === "promote") {
                        return event.event_type === "promote" || event.event_type === "watcher_scan";
                      }
                      return event.event_type === selectedGem;
                    })
                    .slice(0, 6)
                    .map((event, idx) => (
                      <div key={`${event.record_name}-${event.timestamp}-${idx}`} style={{ borderRadius: 12, border: "1px solid rgba(71,85,105,0.4)", background: "rgba(15,23,42,0.6)", padding: 8 }}>
                        <div style={{ fontWeight: 600, color: "#e2e8f0" }}>{event.record_name}</div>
                        <div style={{ marginTop: 4, color: "#94a3b8" }}>{event.event_type} • {event.status}</div>
                      </div>
                    ))}
                  {events.filter((event) => {
                    if (selectedGem === "obsidian") {
                      return event.status === "error" || event.status === "skipped";
                    }
                    if (selectedGem === "promote") {
                      return event.event_type === "promote" || event.event_type === "watcher_scan";
                    }
                    return event.event_type === selectedGem;
                  }).length === 0 ? (
                    <div style={{ fontSize: 11, color: "#64748b" }}>No matching events in recent history.</div>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div style={styles.panel}>
              <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 600, color: "#e9d5ff" }}>Emissary Pedestal</div>
                  <div style={{ fontSize: 12, color: "#94a3b8" }}>Candidate insights emerge where records repeat or cluster in the Item World.</div>
                </div>
                <Sparkles size={16} color="#fbbf24" />
              </div>

              <div style={{ display: "grid", gap: 12 }}>
                {insights.length === 0 ? (
                  <div style={{ borderRadius: 16, border: "1px solid rgba(71,85,105,0.3)", background: "rgba(2,6,23,0.5)", padding: 14, fontSize: 12, color: "#94a3b8" }}>
                    No repeated patterns yet. Awaiting richer event trails.
                  </div>
                ) : (
                  insights.map((insight) => (
                    <button
                      key={insight.recordName}
                      type="button"
                      onClick={() => setOpenInsight(insight)}
                      style={{
                        borderRadius: 16,
                        border: "1px solid rgba(168,85,247,0.2)",
                        background: "rgba(2,6,23,0.5)",
                        padding: 14,
                        textAlign: "left",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: "#e9d5ff" }}>{insight.recordName}</div>
                        <span style={{ fontSize: 10, color: "#94a3b8" }}>{insight.eventCount} events</span>
                      </div>
                      <div style={{ marginTop: 8, fontSize: 11, color: "#94a3b8" }}>{insight.pattern}</div>
                    </button>
                  ))
                )}
              </div>
            </div>

            <div style={styles.panel}>
              <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ fontSize: 20, fontWeight: 600, color: "#e9d5ff" }}>Selected Trail</div>
                <Orbit size={16} color="#e9d5ff" />
              </div>
              {selected ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {["hermes_write", "promote", "approve", "honcho_bridge"].map((step) => {
                    const match =
                      selected.events.find((e) => e.event_type === step) ??
                      (step === "promote"
                        ? selected.events.find((e) => e.event_type === "watcher_scan")
                        : undefined);
                    const failed = match?.status === "error" || match?.status === "skipped";

                    return (
                      <div key={step} style={{ borderRadius: 16, border: "1px solid rgba(168,85,247,0.2)", background: "rgba(2,6,23,0.4)", padding: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12 }}>
                          <span style={{ color: "#e2e8f0" }}>{step}</span>
                          <span style={{ fontSize: 11, color: failed ? "#fda4af" : "#86efac" }}>
                            {match ? match.status : "pending"}
                          </span>
                        </div>
                        <div style={{ marginTop: 8, fontSize: 11, color: "#64748b" }}>{match?.timestamp ?? "No event yet"}</div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "#94a3b8" }}>Select a node to see its path.</div>
              )}
            </div>
          </div>
        </section>

        <section style={styles.panel}>
          <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 20, fontWeight: 600, color: "#e9d5ff" }}>Overhead Mining Grid</div>
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Pattern density mapped from live event clusters.</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#94a3b8" }}>
              <Layers3 size={14} />
              {records.length} clusters
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px,1fr))", gap: 12 }}>
            {miningTiles.length === 0 ? (
              <div style={{ gridColumn: "1 / -1", borderRadius: 16, border: "1px solid rgba(71,85,105,0.3)", background: "rgba(2,6,23,0.4)", padding: 14, fontSize: 12, color: "#94a3b8" }}>
                No cluster density yet. Feed events into the system to illuminate the grid.
              </div>
            ) : (
              miningTiles.map((tile) => {
                const brightness = Math.min(1, 0.2 + tile.count * 0.1);
                const style = tileStyleForTypes(tile.types);
                return (
                  <div
                    key={tile.id}
                    style={{
                      borderRadius: 16,
                      border: "1px solid rgba(168,85,247,0.2)",
                      padding: 14,
                      ...style,
                      boxShadow: `0 0 ${10 + tile.count * 4}px rgba(147,51,234,${brightness})`,
                    }}
                  >
                    <div style={{ fontSize: 11, color: "#e2e8f0", wordBreak: "break-all" }}>{tile.id}</div>
                    <div style={{ marginTop: 8, fontSize: 18, fontWeight: 600, color: "#e9d5ff" }}>{tile.count}</div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        <section style={styles.panel}>
          <div style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#94a3b8" }}>
            <Users size={14} color="#e9d5ff" />
            Honcho sessions are mirrors only. No collective writes occur here.
          </div>
          <div style={{ fontSize: 11, color: "#64748b" }}>
            This is a visual debugger and pattern explorer. All signals derive from /api/status.
          </div>
        </section>
      </div>

      {openInsight ? (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(2,6,23,0.7)", padding: 24 }}>
          <div style={{ width: "100%", maxWidth: 540, borderRadius: 24, border: "1px solid rgba(168,85,247,0.3)", background: "#020617", padding: 24, color: "#e2e8f0" }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 600, color: "#e9d5ff" }}>{openInsight.recordName}</div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>{openInsight.pattern}</div>
              </div>
              <button
                type="button"
                style={{ borderRadius: 999, border: "1px solid rgba(168,85,247,0.3)", padding: "6px 12px", fontSize: 11, color: "#e9d5ff", background: "transparent", cursor: "pointer" }}
                onClick={() => setOpenInsight(null)}
              >
                Close
              </button>
            </div>
            <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 8, fontSize: 12, color: "#cbd5f5" }}>
              {openInsight.sequence.map((entry, index) => (
                <div key={`${entry}-${index}`} style={{ borderRadius: 12, border: "1px solid rgba(71,85,105,0.4)", background: "rgba(15,23,42,0.6)", padding: 8 }}>
                  {entry}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

