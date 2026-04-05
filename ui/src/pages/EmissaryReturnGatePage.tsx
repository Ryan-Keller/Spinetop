import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ImagePlus, Shield, UserCircle2, Backpack, Orbit, ScrollText } from "lucide-react";

// EMISSARY RETURN GATE PAGE
// Narrative rules:
// - emissaries spawn without an avatar
// - before re-entry to Honcho, they must choose a portrait/avatar photo
// - choosing a portrait locks style/persona
// - items/images brought back stay OUTSIDE Honcho in a clean-room return cache
// - Honcho itself stays clean
// - this page also shows a 3D-ish phrase/mind map of language gathered while outside

// System rules:
// 1. Emissaries cannot spawn bots.
// 2. Emissaries are gatherers only and may crawl the internet to bring back information.
// 3. Custodial staff are the only authority that can spawn emissaries.
// 4. Custodial/self-heal/emergency support emissaries should auto-dispatch after 5 seconds.
// 5. Any self-heal action should use rapid deployment.
// 6. Add a global kill switch concept: "Return All to Base".
// 7. Replace gemstone-type labels with data-category labels (colors may remain).

type Emissary = {
  id: string;
  name: string;
  status: "new" | "returned";
  avatarLocked: boolean;
  archetype: string;
  outsidePhrases: string[];
  returnImages: { id: string; label: string; kind: "photo" | "scan" | "reference" }[];
  category: "input" | "growth" | "truth" | "bridge" | "risk";
  origin: "custodial" | "self-heal" | "emergency" | "field";
  autoDispatchAt?: string;
  rapidDeployment?: boolean;
};

const fallbackEmissaries: Emissary[] = [
  {
    id: "emissary-001",
    name: "Lapis Courier",
    status: "new",
    avatarLocked: false,
    archetype: "unformed",
    outsidePhrases: ["bridge retry", "timeout cluster", "pattern drift", "rate polite", "neighbor safe"],
    returnImages: [],
    category: "bridge",
    origin: "custodial",
    autoDispatchAt: "T+5s",
    rapidDeployment: false,
  },
  {
    id: "emissary-002",
    name: "Verdant Runner",
    status: "returned",
    avatarLocked: true,
    archetype: "field naturalist",
    outsidePhrases: ["emerald seam", "repeat anomaly", "cluster review", "signal overlap", "artifact request"],
    returnImages: [
      { id: "img-1", label: "Portal residue", kind: "photo" },
      { id: "img-2", label: "Field reference", kind: "reference" },
    ],
    category: "growth",
    origin: "field",
  },
  {
    id: "emissary-003",
    name: "Sable Witness",
    status: "returned",
    avatarLocked: false,
    archetype: "uncertain",
    outsidePhrases: ["contradiction seam", "obsidian warning", "defer entry", "compare traces"],
    returnImages: [
      { id: "img-3", label: "Anomaly clipping", kind: "scan" },
    ],
    category: "risk",
    origin: "self-heal",
    autoDispatchAt: "T+5s",
    rapidDeployment: true,
  },
];

const avatarChoices = [
  { id: "a1", label: "Torch Scholar", emoji: "??" },
  { id: "a2", label: "Stone Runner", emoji: "??" },
  { id: "a3", label: "Guild Envoy", emoji: "???" },
  { id: "a4", label: "Crystal Scout", emoji: "??" },
];

const categoryColor: Record<Emissary["category"], string> = {
  input: "#fbbf24",
  growth: "#34d399",
  truth: "#7dd3fc",
  bridge: "#e879f9",
  risk: "#fb7185",
};

const categoryLabel: Record<Emissary["category"], string> = {
  input: "Input",
  growth: "Growth",
  truth: "Truth",
  bridge: "Bridge",
  risk: "Risk",
};

const originLabel: Record<Emissary["origin"], string> = {
  custodial: "custodial",
  "self-heal": "self-heal",
  emergency: "emergency",
  field: "field",
};

const styles = {
  page: {
    minHeight: "100vh",
    background: "#06070b",
    color: "#e2e8f0",
    padding: "24px 32px",
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
  panel: {
    borderRadius: 24,
    border: "1px solid rgba(217,70,239,0.2)",
    background: "rgba(15,23,42,0.8)",
    padding: 20,
  } as const,
  split: {
    display: "grid",
    gap: 24,
    gridTemplateColumns: "minmax(0, 0.9fr) minmax(0, 1.1fr)",
  } as const,
};

function phraseNodes(phrases: string[]) {
  return phrases.map((phrase, i) => ({
    phrase,
    x: 14 + ((i * 19) % 72),
    y: 18 + ((i * 23) % 56),
    z: 0.7 + ((i % 4) * 0.18),
    delay: i * 0.12,
  }));
}

export default function EmissaryReturnGatePage() {
  const [emissaries, setEmissaries] = useState<Emissary[]>(fallbackEmissaries);
  const [selectedId, setSelectedId] = useState<string>(fallbackEmissaries[0].id);
  const [killSwitchArmed, setKillSwitchArmed] = useState(false);
  const [actionLog, setActionLog] = useState<string[]>([]);
  const selected = emissaries.find((e) => e.id === selectedId) || emissaries[0];

  const nodes = useMemo(() => phraseNodes(selected.outsidePhrases), [selected]);

  const pushAction = (message: string) => {
    setActionLog((prev) => [message, ...prev].slice(0, 4));
  };

  const lockAvatar = (choice: (typeof avatarChoices)[number]) => {
    setEmissaries((prev) =>
      prev.map((e) =>
        e.id === selected.id
          ? {
              ...e,
              avatarLocked: true,
              archetype: choice.label.toLowerCase(),
              name: `${choice.label}`,
            }
          : e
      )
    );
    pushAction(`Locked portrait for ${selected.name}: ${choice.label}`);
  };

  const handleKillSwitch = () => {
    setKillSwitchArmed((prev) => {
      const next = !prev;
      pushAction(next ? "Return All to Base armed" : "Return All to Base cleared");
      return next;
    });
  };

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={styles.pillRow}>
            <span style={{ ...styles.pill, background: "#c026d3", color: "#fff", fontWeight: 600 }}>
              Emissary Return Gate
            </span>
            <span
              style={{
                ...styles.pill,
                border: "1px solid rgba(56,189,248,0.3)",
                background: "rgba(8,47,73,0.4)",
                color: "#a5f3fc",
              }}
            >
              clean room boundary
            </span>
            <span
              style={{
                ...styles.pill,
                border: "1px solid rgba(148,163,184,0.3)",
                background: "rgba(15,23,42,0.6)",
                color: "#cbd5f5",
              }}
            >
              custodial-only spawn authority
            </span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 16 }}>
            <div>
              <h1 style={{ margin: 0, fontSize: 32, color: "#f0abfc" }}>Portrait Oath & Return Cache</h1>
              <p style={{ marginTop: 8, color: "#94a3b8", maxWidth: 720 }}>
                Emissaries are gatherers only. They must lock a portrait before re-entry.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
                <span style={{ ...styles.pill, border: "1px solid rgba(52,211,153,0.35)", background: "rgba(6,78,59,0.22)", color: "#bbf7d0" }}>
                  selected: {selected.name}
                </span>
                <span style={{ ...styles.pill, border: "1px solid rgba(56,189,248,0.35)", background: "rgba(8,47,73,0.22)", color: "#a5f3fc" }}>
                  portrait: {selected.avatarLocked ? selected.archetype : "unlocked"}
                </span>
                <span style={{ ...styles.pill, border: "1px solid rgba(251,191,36,0.35)", background: "rgba(120,53,15,0.22)", color: "#fde68a" }}>
                  return cache: {selected.returnImages.length} item{selected.returnImages.length === 1 ? "" : "s"}
                </span>
                <span style={{ ...styles.pill, border: "1px solid rgba(244,63,94,0.35)", background: killSwitchArmed ? "rgba(190,18,60,0.26)" : "rgba(15,23,42,0.55)", color: killSwitchArmed ? "#fecdd3" : "#cbd5f5" }}>
                  return all: {killSwitchArmed ? "armed" : "clear"}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={handleKillSwitch}
              style={{
                borderRadius: 999,
                border: killSwitchArmed ? "1px solid rgba(244,63,94,0.6)" : "1px solid rgba(148,163,184,0.3)",
                background: killSwitchArmed ? "rgba(190,18,60,0.25)" : "rgba(15,23,42,0.6)",
                color: killSwitchArmed ? "#fecdd3" : "#cbd5f5",
                padding: "8px 16px",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
              >
              {killSwitchArmed ? "Return All Armed" : "Return All to Base"}
            </button>
          </div>
        </div>

        <div style={styles.panel}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "#f0abfc" }}>Action Receipt</div>
              <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                These buttons are local-state controls, so clicking them should visibly change the page.
              </div>
            </div>
            <span style={{ ...styles.pill, border: "1px solid rgba(217,70,239,0.3)", background: "rgba(2,6,23,0.5)", color: "#e9d5ff" }}>
              preview only
            </span>
          </div>
          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
            {actionLog.length ? (
              actionLog.map((entry) => (
                <div
                  key={entry}
                  style={{
                    borderRadius: 14,
                    border: "1px solid rgba(217,70,239,0.2)",
                    background: "rgba(2,6,23,0.55)",
                    padding: "10px 12px",
                    fontSize: 12,
                    color: "#cbd5f5",
                  }}
                >
                  {entry}
                </div>
              ))
            ) : (
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Click a ledger card, portrait choice, or the return button to see action receipts here.</div>
            )}
          </div>
        </div>

        <div style={styles.split}>
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div style={styles.panel}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 18, fontWeight: 600, color: "#f0abfc" }}>
                <ScrollText size={18} />
                Emissary Ledger
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}>
                {emissaries.map((e) => (
                  <button
                    key={e.id}
                    onClick={() => {
                      setSelectedId(e.id);
                      pushAction(`Selected emissary ledger card: ${e.name}`);
                    }}
                    style={{
                      borderRadius: 16,
                      border: selected.id === e.id ? "1px solid rgba(252,211,77,0.4)" : "1px solid rgba(217,70,239,0.2)",
                      background: selected.id === e.id ? "rgba(252,211,77,0.1)" : "rgba(2,6,23,0.5)",
                      padding: 16,
                      textAlign: "left",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                      <div>
                        <div style={{ fontWeight: 600, color: "#f0abfc" }}>{e.name}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#94a3b8" }}>
                          {e.status === "new" ? "newly spawned" : "returned from outside"}
                        </div>
                        <div style={{ marginTop: 6, fontSize: 12, color: categoryColor[e.category] }}>
                          {categoryLabel[e.category]} category
                        </div>
                        <div style={{ marginTop: 4, fontSize: 11, color: "#64748b" }}>
                          origin: {originLabel[e.origin]}
                        </div>
                      </div>
                      <div
                        style={{
                          borderRadius: 999,
                          border: e.avatarLocked ? "1px solid rgba(52,211,153,0.3)" : "1px solid rgba(248,113,113,0.3)",
                          background: e.avatarLocked ? "rgba(52,211,153,0.1)" : "rgba(248,113,113,0.1)",
                          color: e.avatarLocked ? "#bbf7d0" : "#fecaca",
                          padding: "4px 10px",
                          fontSize: 11,
                        }}
                      >
                        {e.avatarLocked ? "portrait locked" : "faceless"}
                      </div>
                    </div>
                    {e.autoDispatchAt ? (
                      <div style={{ marginTop: 10, fontSize: 11, color: "#fbbf24" }}>
                        auto-dispatch {e.autoDispatchAt}
                      </div>
                    ) : null}
                    {e.rapidDeployment ? (
                      <div style={{ marginTop: 6, fontSize: 11, color: "#38bdf8" }}>
                        rapid deployment
                      </div>
                    ) : null}
                  </button>
                ))}
              </div>
            </div>

            <div style={styles.panel}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 18, fontWeight: 600, color: "#f0abfc" }}>
                <UserCircle2 size={18} />
                Portrait Oath
              </div>
              {!selected.avatarLocked ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 16 }}>
                  <div style={{ fontSize: 13, color: "#cbd5f5" }}>
                    A portrait must be chosen before re-entry. Emissaries cannot spawn bots.
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 }}>
                    {avatarChoices.map((choice) => (
                      <button
                        key={choice.id}
                        onClick={() => lockAvatar(choice)}
                        style={{
                          borderRadius: 16,
                          border: "1px solid rgba(217,70,239,0.2)",
                          background: "rgba(2,6,23,0.5)",
                          padding: 14,
                          textAlign: "left",
                          cursor: "pointer",
                        }}
                      >
                        <div style={{ fontSize: 24 }}>{choice.emoji}</div>
                        <div style={{ marginTop: 8, fontWeight: 600, color: "#f0abfc" }}>{choice.label}</div>
                        <div style={{ marginTop: 4, fontSize: 11, color: "#94a3b8" }}>lock style + field persona</div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    marginTop: 16,
                    borderRadius: 16,
                    border: "1px solid rgba(52,211,153,0.2)",
                    background: "rgba(52,211,153,0.1)",
                    padding: 14,
                    color: "#bbf7d0",
                    fontSize: 13,
                  }}
                >
                  Portrait chosen. Persona locked: <strong>{selected.archetype}</strong>
                </div>
              )}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div style={styles.panel}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 18, fontWeight: 600, color: "#f0abfc" }}>
                <Orbit size={18} />
                Outside Language Mind Map
              </div>
              <div
                style={{
                  position: "relative",
                  height: 360,
                  overflow: "hidden",
                  borderRadius: 24,
                  border: "1px solid rgba(217,70,239,0.2)",
                  background: "radial-gradient(circle at center, #0b1020 0%, #05070d 78%)",
                  marginTop: 16,
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background: "radial-gradient(circle at center, rgba(168,85,247,0.1), transparent 55%)",
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    left: "50%",
                    top: "50%",
                    height: 64,
                    width: 64,
                    transform: "translate(-50%, -50%)",
                    borderRadius: "50%",
                    border: "1px solid rgba(217,70,239,0.3)",
                    background: "rgba(217,70,239,0.1)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#f0abfc",
                    fontSize: 12,
                  }}
                >
                  outside
                </div>
                {nodes.map((node) => (
                  <motion.div
                    key={node.phrase}
                    style={{
                      position: "absolute",
                      left: `${node.x}%`,
                      top: `${node.y}%`,
                      transform: `scale(${node.z})`,
                    }}
                    animate={{ y: [0, -8, 0], opacity: [0.5, 1, 0.55] }}
                    transition={{ duration: 3 + node.delay, repeat: Infinity }}
                  >
                    <div
                      style={{
                        borderRadius: 999,
                        border: "1px solid rgba(34,211,238,0.2)",
                        background: "rgba(34,211,238,0.1)",
                        padding: "6px 12px",
                        fontSize: 12,
                        color: "#a5f3fc",
                        boxShadow: "0 0 24px rgba(34,211,238,0.12)",
                      }}
                    >
                      {node.phrase}
                    </div>
                  </motion.div>
                ))}
                {nodes.map((node) => (
                  <svg key={`line-${node.phrase}`} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
                    <line
                      x1="50%"
                      y1="50%"
                      x2={`${node.x + 4}%`}
                      y2={`${node.y + 3}%`}
                      stroke="rgba(103,232,249,0.18)"
                      strokeWidth="1"
                    />
                  </svg>
                ))}
              </div>
            </div>

            <div style={{ display: "grid", gap: 24, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
              <div style={styles.panel}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 18, fontWeight: 600, color: "#f0abfc" }}>
                  <ImagePlus size={18} />
                  Return Cache
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16 }}>
                  <div
                    style={{
                      borderRadius: 16,
                      border: "1px solid rgba(34,211,238,0.2)",
                      background: "rgba(34,211,238,0.1)",
                      padding: 14,
                      fontSize: 12,
                      color: "#a5f3fc",
                    }}
                  >
                    Return cache stays outside Honcho.
                  </div>
                  <div
                    style={{
                      borderRadius: 16,
                      border: "1px solid rgba(217,70,239,0.2)",
                      background: "rgba(2,6,23,0.5)",
                      padding: 14,
                    }}
                  >
                    <div style={{ fontSize: 12, color: "#94a3b8" }}>Image intake slot</div>
                    <div
                      style={{
                        marginTop: 12,
                        height: 96,
                        borderRadius: 16,
                        border: "1px dashed rgba(100,116,139,0.4)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 12,
                        color: "#94a3b8",
                      }}
                    >
                      drop / attach returned image here
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {selected.returnImages.length > 0 ? (
                      selected.returnImages.map((img) => (
                        <div
                          key={img.id}
                          style={{
                            borderRadius: 16,
                            border: "1px solid rgba(217,70,239,0.2)",
                            background: "rgba(2,6,23,0.5)",
                            padding: "10px 14px",
                            fontSize: 12,
                            color: "#e2e8f0",
                          }}
                        >
                          <strong>{img.label}</strong> <span style={{ color: "#94a3b8" }}>({img.kind})</span>
                        </div>
                      ))
                    ) : (
                      <div
                        style={{
                          borderRadius: 16,
                          border: "1px solid rgba(217,70,239,0.2)",
                          background: "rgba(2,6,23,0.5)",
                          padding: "10px 14px",
                          fontSize: 12,
                          color: "#94a3b8",
                        }}
                      >
                        No return images cached yet.
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div style={styles.panel}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 18, fontWeight: 600, color: "#f0abfc" }}>
                  <Backpack size={18} />
                  Re-Entry Rules
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 16, fontSize: 12, color: "#cbd5f5" }}>
                  <div style={{ borderRadius: 16, border: "1px solid rgba(217,70,239,0.2)", background: "rgba(2,6,23,0.5)", padding: 14 }}>
                    Honcho is a clean room. Outside cache stays staged.
                  </div>
                  <div style={{ borderRadius: 16, border: "1px solid rgba(217,70,239,0.2)", background: "rgba(2,6,23,0.5)", padding: 14 }}>
                    Emissaries are gatherers only. They may crawl the internet but cannot spawn bots.
                  </div>
                  <div style={{ borderRadius: 16, border: "1px solid rgba(217,70,239,0.2)", background: "rgba(2,6,23,0.5)", padding: 14 }}>
                    Custodial staff alone can spawn emissaries. Self-heal/emergency uses rapid deployment.
                  </div>
                </div>
                <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#fbbf24" }}>
                  <Shield size={16} />
                  kill switch armed: {killSwitchArmed ? "YES" : "NO"}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
