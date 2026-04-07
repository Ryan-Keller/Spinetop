import { useEffect, useState } from "react";
import Dashboard from "./pages/Dashboard";
import HonchoItemWorld from "./pages/HonchoItemWorld";
import AgentMemoryTriadPage from "./pages/AgentMemoryTriadPage";
import EmissaryReturnGatePage from "./pages/EmissaryReturnGatePage";
import ExpressionConsolePage from "./pages/ExpressionConsolePage";
import VisibleExpressionConsolePage from "./pages/VisibleExpressionConsolePage";

type Page = "dashboard" | "console" | "visibleConsole" | "honcho" | "triad" | "emissary";

const pageHashes: Record<Page, string> = {
  dashboard: "#/dashboard",
  console: "#/console",
  visibleConsole: "#/visible-console",
  honcho: "#/honcho",
  triad: "#/triad",
  emissary: "#/emissary",
};

const hashToPage = (hash: string): Page => {
  const normalized = hash.trim().toLowerCase();
  if (normalized === "#/visible-console") return "visibleConsole";
  if (normalized === "#/console") return "console";
  if (normalized === "#/honcho") return "honcho";
  if (normalized === "#/triad") return "triad";
  if (normalized === "#/emissary") return "emissary";
  return "dashboard";
};

const styles = {
  app: {
    minHeight: "100vh",
    background: "#0b1220",
    color: "#e2e8f0",
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
  } as const,
  nav: {
    position: "sticky" as const,
    top: 0,
    zIndex: 50,
    background: "rgba(11, 18, 32, 0.9)",
    borderBottom: "1px solid rgba(148, 163, 184, 0.2)",
    padding: "12px 24px",
    backdropFilter: "blur(10px)",
  } as const,
  navInner: {
    maxWidth: 1200,
    margin: "0 auto",
    display: "flex",
    flexWrap: "wrap" as const,
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  } as const,
  brand: {
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: "0.06em",
    color: "#e2e8f0",
  } as const,
  navButtons: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap" as const,
  } as const,
  button: {
    borderRadius: 999,
    padding: "8px 16px",
    fontSize: 13,
    fontWeight: 600,
    border: "1px solid rgba(148, 163, 184, 0.3)",
    background: "transparent",
    color: "#cbd5f5",
    cursor: "pointer",
  } as const,
  buttonActive: {
    border: "none",
    background: "#7c3aed",
    color: "#ffffff",
  } as const,
};

function App() {
  const [page, setPage] = useState<Page>(() => hashToPage(window.location.hash));

  useEffect(() => {
    const applyHash = () => setPage(hashToPage(window.location.hash));
    window.addEventListener("hashchange", applyHash);
    if (!window.location.hash) {
      window.location.hash = pageHashes.dashboard;
    }
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  const navigate = (nextPage: Page) => {
    const nextHash = pageHashes[nextPage];
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash;
      return;
    }
    setPage(nextPage);
  };

  return (
    <div style={styles.app}>
      <nav style={styles.nav}>
        <div style={styles.navInner}>
          <div style={styles.brand}>Spinetop Memory UI</div>
          <div style={styles.navButtons}>
            <button
              type="button"
              onClick={() => navigate("dashboard")}
              style={{
                ...styles.button,
                ...(page === "dashboard" ? styles.buttonActive : null),
              }}
            >
              Expeditions
            </button>
            <button
              type="button"
              onClick={() => navigate("visibleConsole")}
              style={{
                ...styles.button,
                ...(page === "visibleConsole" ? styles.buttonActive : null),
              }}
            >
              Visible Console
            </button>
            <button
              type="button"
              onClick={() => navigate("console")}
              style={{
                ...styles.button,
                ...(page === "console" ? styles.buttonActive : null),
              }}
            >
              Expression Console V1
            </button>
            <button
              type="button"
              onClick={() => navigate("honcho")}
              style={{
                ...styles.button,
                ...(page === "honcho" ? styles.buttonActive : null),
              }}
            >
              Honcho Item World
            </button>
            <button
              type="button"
              onClick={() => navigate("triad")}
              style={{
                ...styles.button,
                ...(page === "triad" ? styles.buttonActive : null),
              }}
            >
              Agent Memory Triad
            </button>
            <button
              type="button"
              onClick={() => navigate("emissary")}
              style={{
                ...styles.button,
                ...(page === "emissary" ? styles.buttonActive : null),
              }}
            >
              Emissary Return Gate
            </button>
          </div>
        </div>
      </nav>

      {page === "dashboard" ? (
        <Dashboard />
      ) : page === "visibleConsole" ? (
        <VisibleExpressionConsolePage />
      ) : page === "console" ? (
        <ExpressionConsolePage />
      ) : page === "honcho" ? (
        <HonchoItemWorld />
      ) : page === "triad" ? (
        <AgentMemoryTriadPage />
      ) : (
        <EmissaryReturnGatePage />
      )}
    </div>
  );
}

export default App;
