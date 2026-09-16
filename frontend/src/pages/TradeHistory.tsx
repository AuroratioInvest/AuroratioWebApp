import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import NavHeader from "../components/layout/NavHeader";
import client from "../api/client";

const getModuleLabel = (value?: string) => {
  if (!value) return "—";

  const normalized = String(value).toLowerCase();

  if (normalized.includes("1") || normalized.includes("silver")) return "Module 1";
  if (normalized.includes("2") || normalized.includes("platinum")) return "Module 2";
  if (normalized.includes("3") || normalized.includes("palladium")) return "Module 3";

  return value;
};

export default function TradeHistory() {
  const navigate = useNavigate();
  const [trades, setTrades] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [hasNext, setHasNext] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      navigate("/login");
      return;
    }

    setLoading(true);
    client
      .get(`/trades/history?page=${page}&limit=50`)
      .then((res) => {
        setTrades(res.data.trades || []);
        setHasNext(Boolean(res.data.has_next));
        setError("");
      })
      .catch((err) => {
        console.error("Failed to load trade history", err);
        setTrades([]);
        setHasNext(false);
        setError("Could not load activity history.");
      })
      .finally(() => setLoading(false));
  }, [navigate, page]);

  return (
    <div className="trades-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

        .trades-page {
          --gold: #C9A84C;
          --gold-light: #E8C97A;
          --ink: #0A0A08;
          --ink-2: #111109;
          --ink-3: #1A1A14;
          --text: #E8E4D8;
          --text-muted: #8A8670;
          --rule: rgba(201,168,76,.18);
          --green: #5A9E72;
          --red: #D56A5F;

          min-height: 100vh;
          background: var(--ink);
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          font-weight: 300;
          overflow-x: hidden;
          position: relative;
        }

        .trades-page * { box-sizing: border-box; }

        .trades-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
          pointer-events: none;
          opacity: .5;
          z-index: 0;
        }

        .trades-main {
          position: relative;
          z-index: 1;
          max-width: 1180px;
          margin: 0 auto;
          padding: 3rem;
        }

        .trades-hero {
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

        .trades-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(2.6rem, 5vw, 4.4rem);
          font-weight: 300;
          line-height: 1.02;
          letter-spacing: -.02em;
          color: var(--text);
        }

        .trades-title em {
          color: var(--gold-light);
          font-style: italic;
        }

        .trades-subtitle {
          max-width: 620px;
          color: var(--text-muted);
          line-height: 1.8;
          margin-top: 1rem;
          font-size: .95rem;
        }

        .pager {
          display: inline-flex;
          align-items: center;
          gap: .7rem;
          color: var(--text-muted);
          font-size: .78rem;
        }

        .pager-button {
          border: 1px solid var(--rule);
          background: rgba(201,168,76,.04);
          color: var(--text-muted);
          border-radius: 999px;
          padding: .6rem .9rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .68rem;
          letter-spacing: .1em;
          text-transform: uppercase;
          cursor: pointer;
          transition: color .2s, border-color .2s, background .2s, opacity .2s;
        }

        .pager-button:hover:not(:disabled) {
          color: var(--text);
          border-color: rgba(201,168,76,.36);
          background: rgba(201,168,76,.08);
        }

        .pager-button:disabled {
          opacity: .35;
          cursor: not-allowed;
        }

        .trades-card {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          box-shadow: 0 24px 80px rgba(0,0,0,.24);
          overflow: hidden;
        }

        .table-scroll {
          width: 100%;
          overflow-x: auto;
        }

        .trades-table {
          min-width: 860px;
        }
        
        .table-header,
        .table-row {
          display: grid;
          grid-template-columns: 1.2fr 1.4fr 1.4fr 1fr 1fr;
          align-items: center;
          column-gap: 1rem;
          padding: 1rem 1.5rem;
        }

        .table-header {
          background: var(--ink-3);
          border-bottom: 1px solid var(--rule);
        }

        .table-header-cell {
          font-size: .68rem;
          letter-spacing: .12em;
          text-transform: uppercase;
          color: var(--gold);
          font-weight: 500;
        }

        .table-row {
          min-height: 64px;
          border-bottom: 1px solid rgba(201,168,76,.1);
          transition: background .2s;
        }

        .table-row:last-child { border-bottom: 0; }

        .table-row:hover { background: rgba(201,168,76,.035); }

        .table-cell {
          color: var(--text);
          font-size: .9rem;
          line-height: 1.45;
          min-width: 0;
          overflow-wrap: anywhere;
        }

        .muted-cell {
          color: var(--text-muted);
        }

        .empty-state {
          grid-column: 1 / -1;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          min-height: 220px;
          color: var(--text-muted);
          padding: 2rem;
        }

        .empty-title {
          color: var(--text);
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.8rem;
          margin-bottom: .45rem;
        }

        .status-pill {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: fit-content;
          min-width: 72px;
          border-radius: 999px;
          border: 1px solid rgba(201,168,76,.18);
          padding: .36rem .7rem;
          font-size: .72rem;
          letter-spacing: .08em;
          text-transform: uppercase;
          font-weight: 500;
        }

        .trade-action.completed {
          color: var(--green);
          border-color: rgba(90,158,114,.25);
          background: rgba(90,158,114,.08);
        }

        .trade-action.pending {
          color: var(--gold-light);
          border-color: rgba(201,168,76,.25);
          background: rgba(201,168,76,.08);
        }

        .trade-result.profit { color: var(--green); }
        .trade-result.loss { color: var(--red); }

        .loading-card {
          min-height: 320px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-muted);
        }

        @media (max-width: 900px) {
          .trades-main {
            padding: 2rem 1.5rem;
          }

          .trades-hero {
            align-items: flex-start;
            flex-direction: column;
          }
        }
      `}</style>

      <NavHeader />

      <main className="trades-main">
        <section className="trades-hero">
          <div>
            <p className="section-label">Activity Log</p>
            <h1 className="trades-title">
              Portfolio <em>History</em>
            </h1>
            <p className="trades-subtitle">
              Review portfolio activity, module updates, amounts, and historical outcomes from the AuroRatio system.
            </p>
          </div>

          <div className="pager" aria-label="Portfolio history pagination">
            <button
              className="pager-button"
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              disabled={page === 1 || loading}
            >
              Previous
            </button>
            <span>Page {page}</span>
            <button
              className="pager-button"
              onClick={() => setPage((value) => value + 1)}
              disabled={loading || !hasNext}
            >
              Next
            </button>
          </div>
        </section>

        {error && (
          <div
            className="trades-card"
            style={{
              padding: "1rem",
              marginBottom: "1rem",
              color: "var(--red)",
            }}
          >
            {error}
          </div>
        )}

        <section className="trades-card">
          {loading ? (
            <div className="loading-card">Loading portfolio history...</div>
          ) : (
            <div className="table-scroll">
              <div className="trades-table">
                <div className="table-header">
                  <div className="table-header-cell">Date</div>
                  <div className="table-header-cell">Module</div>
                  <div className="table-header-cell">Activity</div>
                  <div className="table-header-cell">Amount</div>
                  <div className="table-header-cell">Result</div>
                </div>

                {trades.length === 0 ? (
                  <div className="table-row">
                    <div className="empty-state">
                      <div className="empty-title">No activity yet</div>
                      <div>
                        Activity will appear here once the system processes a portfolio update.
                      </div>
                    </div>
                  </div>
                ) : (
                  trades.map((trade: any, i: number) => {
                    const resultNumber = Number(trade.result);
                    const hasResult = Number.isFinite(resultNumber);

                    const activity =
                      trade.action ||
                      `${trade.from_metal || "—"} → ${trade.to_metal || "—"}`;

                    const actionClass =
                      trade.status === "pending" ? "pending" : "completed";

                    return (
                      <div key={`${trade.id || trade.date || "trade"}-${i}`} className="table-row">
                        <div className="table-cell muted-cell">
                          {trade.date
                            ? new Date(trade.date).toLocaleString()
                            : "—"}
                        </div>

                        <div className="table-cell">
                          {trade.module === "AU_AG"
                            ? "Module 1"
                            : trade.module === "AU_PT"
                            ? "Module 2"
                            : trade.module === "AU_PD"
                            ? "Module 3"
                            : getModuleLabel(trade.module || trade.module_name)}
                        </div>

                        <div className={`table-cell status-pill trade-action ${actionClass}`}>
                          {activity}
                        </div>

                        <div className="table-cell muted-cell">
                          {trade.amount ?? "—"}
                        </div>

                        <div
                          className={`table-cell trade-result ${
                            hasResult && resultNumber >= 0 ? "profit" : "loss"
                          }`}
                        >
                          {hasResult ? `${resultNumber >= 0 ? "+" : ""}${resultNumber}%` : "—"}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}