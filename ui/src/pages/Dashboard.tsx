import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Database,
  RefreshCw,
  CircleDot,
  AlertTriangle,
  CheckCircle2,
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

type StatusResponse = {
  ok: boolean;
  workspace_id: string;
  honcho_sessions_total: number;
  honcho_peers_total: number;
  honcho_sessions: HonchoSession[];
  honcho_peers: HonchoPeer[];
  events_recent: TopologyEvent[];
};

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
};

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

export default function Dashboard() {
  const [data, setData] = useState<StatusResponse>(fallbackData);
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState("demo data");
  const [errorText, setErrorText] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch("http://127.0.0.1:5051/api/status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as StatusResponse;
      setData(json);
      setErrorText("");
      setLastRefresh(new Date().toLocaleTimeString());
    } catch (err) {
      setData(fallbackData);
      setErrorText(`Using fallback data — ${err instanceof Error ? err.message : "request failed"}`);
      setLastRefresh("fallback mode");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const packets = useMemo(() => groupPackets(data.events_recent || []), [data.events_recent]);

  useEffect(() => {
    if (!selectedRecord && packets[0]?.recordName) {
      setSelectedRecord(packets[0].recordName);
    }
  }, [packets, selectedRecord]);

  const selectedPacket = packets.find((p) => p.recordName === selectedRecord) ?? packets[0] ?? null;

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
              <h1 style={styles.headline}>Memory Netherworld Command</h1>
              <p style={styles.subtext}>
                Watch packets move through inbox, promotion, collective truth, and Honcho mirror gates using live backend data.
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

          {errorText ? <div style={styles.alert}>{errorText}</div> : null}
        </div>

        <div style={styles.metrics}>
          {metricCard("Events", (data.events_recent || []).length, "live flow", Activity)}
          {metricCard("Sessions", data.honcho_sessions_total ?? "—", "active memory links", Database)}
          {metricCard(
            "Packet Stage",
            selectedPacket ? `${selectedPacket.stage + 1}/4` : "—",
            selectedPacket?.recordName || "no packet selected",
            CircleDot
          )}
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
                  const stage = event.event_type in { hermes_write: 1, watcher_scan: 1, promote: 1, approve: 1, honcho_bridge: 1 }
                    ? {
                        hermes_write: 0,
                        watcher_scan: 1,
                        promote: 1,
                        approve: 2,
                        honcho_bridge: 3,
                      }[event.event_type as keyof typeof {
                        hermes_write: 0,
                        watcher_scan: 1,
                        promote: 1,
                        approve: 2,
                        honcho_bridge: 3,
                      }]
                    : 0;

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
                  Hermes write spawns left • watcher pulls inward • bridge gets vacuumed into the portal • failures flicker
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
      </div>
    </div>
  );
}
