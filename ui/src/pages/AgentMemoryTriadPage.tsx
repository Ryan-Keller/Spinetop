import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";

// AGENT MEMORY TRIAD PAGE
// This page explains the system to you.
// Each agent = a self-contained loop of learning, action, and intent.

type HonchoSession = {
  id: string;
  metadata?: {
    agent_id?: string;
  };
};

type StatusResponse = {
  honcho_sessions: HonchoSession[];
};

type GemType = "topaz" | "emerald" | "sapphire" | "amethyst" | "obsidian";

const gemEmoji: Record<GemType, string> = {
  topaz: "??",
  emerald: "??",
  sapphire: "??",
  amethyst: "??",
  obsidian: "??",
};

const gemColor: Record<GemType, string> = {
  topaz: "#fbbf24",
  emerald: "#34d399",
  sapphire: "#7dd3fc",
  amethyst: "#e879f9",
  obsidian: "#fb7185",
};

const gemMap: Record<string, GemType> = {
  hermes: "amethyst",
  laptop: "emerald",
  desktop: "sapphire",
};

const styles = {
  page: {
    minHeight: "100vh",
    background: "#000",
    color: "#fff",
    padding: 40,
  } as const,
  container: {
    maxWidth: 1200,
    margin: "0 auto",
    display: "flex",
    flexDirection: "column" as const,
    gap: 40,
  } as const,
  headerTitle: {
    fontSize: 32,
    color: "#f0abfc",
    margin: 0,
  } as const,
  headerText: {
    marginTop: 8,
    color: "#94a3b8",
  } as const,
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: 24,
  } as const,
  card: {
    borderRadius: 24,
    border: "1px solid rgba(217,70,239,0.2)",
    padding: 24,
    background: "rgba(15,23,42,0.7)",
  } as const,
  cardTitle: {
    fontSize: 18,
    color: "#f0abfc",
  } as const,
  cardSub: {
    marginTop: 4,
    color: "#94a3b8",
    fontSize: 13,
  } as const,
  triad: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 16,
    marginTop: 16,
  } as const,
  triadLabel: {
    fontSize: 12,
    color: "#94a3b8",
    marginBottom: 8,
  } as const,
};

function inferGem(agentId?: string): GemType {
  if (!agentId) return "topaz";
  const key = Object.keys(gemMap).find((k) => agentId.toLowerCase().includes(k));
  return key ? gemMap[key] : "topaz";
}

function rand(seed: number) {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

export default function AgentMemoryTriadPage() {
  const [data, setData] = useState<StatusResponse>({ honcho_sessions: [] });

  useEffect(() => {
    fetch("http://127.0.0.1:5051/api/status")
      .then((r) => r.json())
      .then((json) => setData({ honcho_sessions: json.honcho_sessions || [] }))
      .catch(() =>
        setData({
          honcho_sessions: [
            { id: "hermes-desktop", metadata: { agent_id: "hermes-desktop" } },
            { id: "spinelab", metadata: { agent_id: "laptop-agent" } },
          ],
        })
      );
  }, []);

  const agents = useMemo(() => {
    return data.honcho_sessions.map((s, i) => {
      const gem = inferGem(s.metadata?.agent_id);

      const learned = Array.from({ length: 3 }).map((_, idx) => ({
        id: `learn-${i}-${idx}`,
        gem,
        strength: rand(i * 10 + idx) * 10,
      }));

      const actions = Array.from({ length: 2 }).map((_, idx) => ({
        id: `act-${i}-${idx}`,
        result: rand(i * 20 + idx) > 0.5 ? "success" : "fail",
      }));

      const intent = {
        gem,
        intensity: rand(i * 30) * 10,
      };

      return {
        id: s.id,
        agent: s.metadata?.agent_id || "unknown",
        gem,
        learned,
        actions,
        intent,
      };
    });
  }, [data]);

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <div>
          <h1 style={styles.headerTitle}>Agent Memory Triad</h1>
          <p style={styles.headerText}>
            Each agent forms a loop: what it learned, what it tried, and what it wants next.
          </p>
        </div>

        <div style={styles.grid}>
          {agents.map((a) => (
            <div key={a.id} style={styles.card}>
              <div style={{ marginBottom: 16 }}>
                <div style={styles.cardTitle}>{a.agent}</div>
                <div style={{ ...styles.cardSub, color: gemColor[a.gem] }}>
                  {gemEmoji[a.gem]} core bias
                </div>
              </div>

              <div style={styles.triad}>
                <div>
                  <div style={styles.triadLabel}>?? Learned</div>
                  {a.learned.map((l) => (
                    <motion.div
                      key={l.id}
                      style={{ color: gemColor[l.gem], fontSize: 18 }}
                      animate={{ scale: [0.8, 1.2, 0.8] }}
                      transition={{ duration: 2, repeat: Infinity }}
                    >
                      {gemEmoji[l.gem]}
                    </motion.div>
                  ))}
                </div>

                <div>
                  <div style={styles.triadLabel}>?? Actions</div>
                  {a.actions.map((act) => (
                    <div key={act.id} style={{ fontSize: 18 }}>
                      {act.result === "success" ? "?" : "?"}
                    </div>
                  ))}
                </div>

                <div>
                  <div style={styles.triadLabel}>?? Intent</div>
                  <motion.div
                    style={{ color: gemColor[a.intent.gem], fontSize: 24 }}
                    animate={{ scale: [1, 1.5, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  >
                    {gemEmoji[a.intent.gem]}
                  </motion.div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
