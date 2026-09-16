import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { getState } from "../api/signals";
import NavHeader from "../components/layout/NavHeader";
import PortfolioBalance from "../components/PortfolioBalance";
// import RatioChart from "../components/charts/RatioChart";

const GROUP_COLORS: Record<string, string> = {
  CORE: "#C9A84C",
  GROUP_1: "#ADB5BD",
  GROUP_2: "#90E0EF",
  GROUP_3: "#C77DFF",
};

function DashboardCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`dashboard-card ${className}`}>{children}</section>;
}

function SectionLabel({ children }: { children: ReactNode }) {
  return <p className="section-label">{children}</p>;
}

export default function Dashboard() {
  const queryClient = useQueryClient();

  const { data: state, isLoading: stateLoading } = useQuery({
    queryKey: ["state"],
    queryFn: getState,
    refetchInterval: 60000,
  });

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["state"] });
  };

  const modules = [
    {
      id: "m1",
      label: "Module 1",
      description: "Gold ↔ Silver",
      position: state?.m1_position ?? "—",
      days: state?.m1_silver_days ?? 0,
      colorKey: "GROUP_1",
    },
    {
      id: "m2",
      label: "Module 2",
      description: "Gold ↔ Platinum",
      position: state?.m2_position ?? "—",
      days: state?.m2_platinum_days ?? 0,
      colorKey: "GROUP_2",
    },
    {
      id: "m3",
      label: "Module 3",
      description: "Gold ↔ Palladium",
      position: state?.m3_position ?? "—",
      days: state?.m3_palladium_days ?? 0,
      colorKey: "GROUP_3",
    },
  ];

  return (
    <div className="dashboard-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

        .dashboard-page {
          --gold: #C9A84C;
          --gold-light: #E8C97A;
          --ink: #0A0A08;
          --ink-2: #111109;
          --ink-3: #1A1A14;
          --text: #E8E4D8;
          --text-muted: #8A8670;
          --rule: rgba(201,168,76,.18);

          min-height: 100vh;
          background: var(--ink);
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          font-weight: 300;
          overflow-x: hidden;
          position: relative;
        }

        .dashboard-page * { box-sizing: border-box; }

        .dashboard-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
          pointer-events: none;
          opacity: .5;
          z-index: 0;
        }

        .dashboard-main {
          position: relative;
          z-index: 1;
          max-width: 1180px;
          margin: 0 auto;
          padding: 3rem;
        }

        .dashboard-hero {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          gap: 2rem;
          margin-bottom: 2rem;
        }

        .section-label {
          font-family: 'Syncopate', sans-serif;
          font-size: .7rem;
          letter-spacing: .15em;
          text-transform: uppercase;
          color: var(--gold);
          font-weight: 700;
          margin-bottom: .75rem;
        }

        .dashboard-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(2.6rem, 5vw, 4.4rem);
          font-weight: 300;
          line-height: 1.02;
          letter-spacing: -.02em;
          color: var(--text);
        }

        .dashboard-title em {
          color: var(--gold-light);
          font-style: italic;
        }

        .dashboard-subtitle {
          max-width: 580px;
          color: var(--text-muted);
          line-height: 1.8;
          margin-top: 1rem;
          font-size: .95rem;
        }

        .refresh-btn {
          display: inline-flex;
          align-items: center;
          gap: .55rem;
          border: 1px solid var(--rule);
          background: rgba(201,168,76,.04);
          color: var(--text-muted);
          border-radius: 4px;
          padding: .75rem 1rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .74rem;
          letter-spacing: .1em;
          text-transform: uppercase;
          cursor: pointer;
          transition: color .2s, border-color .2s, background .2s, transform .15s;
        }

        .refresh-btn:hover {
          color: var(--text);
          border-color: rgba(201,168,76,.36);
          background: rgba(201,168,76,.08);
          transform: translateY(-1px);
        }

        .dashboard-grid {
          display: grid;
          gap: 1.2rem;
        }

        .dashboard-card {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 1.5rem;
          box-shadow: 0 24px 80px rgba(0,0,0,.24);
        }

        .module-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 1rem;
          margin-top: 1.35rem;
        }

        .module-card {
          background: rgba(255,255,255,.018);
          border: 1px solid rgba(201,168,76,.12);
          border-radius: 10px;
          padding: 1.25rem;
          min-height: 176px;
        }

        .module-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          margin-bottom: 1.4rem;
        }

        .module-name {
          color: var(--text);
          font-size: .82rem;
          letter-spacing: .08em;
          text-transform: uppercase;
        }

        .module-pair {
          color: var(--text-muted);
          font-size: .78rem;
          white-space: nowrap;
        }

        .field-label {
          color: var(--text-muted);
          font-size: .72rem;
          letter-spacing: .08em;
          text-transform: uppercase;
          margin-bottom: .35rem;
        }

        .position-value {
          font-family: 'Cormorant Garamond', serif;
          font-size: 2.45rem;
          font-weight: 600;
          line-height: 1;
          margin-bottom: 1.35rem;
        }

        .signal-row {
          display: flex;
          justify-content: space-between;
          color: var(--text-muted);
          font-size: .75rem;
          margin-bottom: .55rem;
        }

        .signal-track {
          height: 6px;
          border-radius: 999px;
          background: rgba(232,228,216,.08);
          overflow: hidden;
        }

        .signal-fill {
          height: 100%;
          border-radius: 999px;
          transition: width .35s ease;
        }

        .cycle-text {
          color: var(--text-muted);
          font-size: .78rem;
          text-align: right;
          opacity: .72;
          margin-top: -.25rem;
        }

        .loading-text {
          color: var(--text-muted);
          font-size: .88rem;
        }

        @media (max-width: 860px) {
          .dashboard-main { padding: 2rem 1.25rem; }
          .dashboard-hero { flex-direction: column; align-items: flex-start; }
          .module-grid { grid-template-columns: 1fr; }
          .refresh-btn { width: 100%; justify-content: center; }
          .cycle-text { text-align: left; }
        }
      `}</style>

      <NavHeader />

      <main className="dashboard-main">
        <div className="dashboard-hero">
          <div>
            <SectionLabel>Command center</SectionLabel>
            <h1 className="dashboard-title">
              Live portfolio <em>dashboard</em>
            </h1>
            <p className="dashboard-subtitle">
              Monitor your portfolio allocation, account status, and latest system review through the AuroRatio dashboard.
            </p>
          </div>

          <button onClick={handleRefresh} className="refresh-btn">
            <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>

        <div className="dashboard-grid">
          <DashboardCard>
            <SectionLabel>Modules</SectionLabel>

            <div className="module-grid">
              {modules.map((module) => {
                const positionColor =
                  module.position === "GOLD"
                    ? GROUP_COLORS.CORE
                    : GROUP_COLORS[module.colorKey];

                const progress = Math.min((module.days / 2) * 100, 100);

                return (
                  <article key={module.id} className="module-card">
                    <div className="module-head">
                      <span className="module-name">{module.label}</span>
                      <span className="module-pair">{module.description}</span>
                    </div>

                    {stateLoading ? (
                      <p className="loading-text">Loading...</p>
                    ) : (
                      <>
                        <p className="field-label">Current allocation</p>
                        <p className="position-value" style={{ color: positionColor }}>
                          {module.position}
                        </p>

                        <div className="signal-row">
                          <span>Review progress</span>
                          <span>{module.days}/2 days</span>
                        </div>

                        <div className="signal-track">
                          <div
                            className="signal-fill"
                            style={{
                              width: `${progress}%`,
                              background: GROUP_COLORS[module.colorKey],
                            }}
                          />
                        </div>
                      </>
                    )}
                  </article>
                );
              })}
            </div>
          </DashboardCard>

          <PortfolioBalance />

          {state?.last_cycle_run && (
            <p className="cycle-text">
              Last system review: {new Date(state.last_cycle_run).toLocaleString()}
            </p>
          )}          
        </div>
      </main>
    </div>
  );
}