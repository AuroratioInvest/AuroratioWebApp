import { useQuery } from "@tanstack/react-query";
import { getBalance } from "../api/portfolio";

export default function PortfolioBalance() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["portfolio-balance"],
    queryFn: getBalance,
    refetchInterval: 60000,
  });

  const modules = data?.virtual_modules || Object.values(data?.modules || {});
  const realPositions = data?.real_positions || data?.positions || [];

  return (
    <section className="dashboard-card portfolio-balance-card">
      <style>{`
        .portfolio-balance-card .balance-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 2rem;
          margin-bottom: 1.35rem;
        }

        .portfolio-balance-card .balance-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 2.35rem;
          font-weight: 300;
          line-height: 1;
          color: var(--text);
        }

        .portfolio-balance-card .balance-total {
          text-align: right;
        }

        .portfolio-balance-card .balance-total-value {
          font-family: 'Cormorant Garamond', serif;
          color: var(--gold-light);
          font-size: 2.4rem;
          font-weight: 600;
          line-height: 1;
        }

        .portfolio-balance-card .balance-subnote {
          color: var(--text-muted);
          font-size: .76rem;
          margin-top: .4rem;
          max-width: 22rem;
        }

        .portfolio-balance-card .balance-list {
          display: grid;
          gap: .85rem;
        }

        .portfolio-balance-card .balance-module {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
          background: rgba(255,255,255,.018);
          border: 1px solid rgba(201,168,76,.12);
          border-radius: 10px;
          padding: 1rem 1.15rem;
        }

        .portfolio-balance-card .balance-module-name {
          color: var(--text);
          font-size: .82rem;
          letter-spacing: .08em;
          text-transform: uppercase;
        }

        .portfolio-balance-card .balance-module-metal {
          color: var(--text-muted);
          font-size: .78rem;
          margin-top: .35rem;
        }

        .portfolio-balance-card .balance-module-badge {
          display: inline-flex;
          margin-top: .45rem;
          padding: .18rem .5rem;
          border-radius: 999px;
          border: 1px solid rgba(201,168,76,.2);
          color: var(--gold-light);
          font-size: .68rem;
          letter-spacing: .08em;
          text-transform: uppercase;
        }

        .portfolio-balance-card .balance-module-value {
          font-family: 'Cormorant Garamond', serif;
          color: var(--text);
          font-size: 1.45rem;
          font-weight: 600;
          white-space: nowrap;
          text-align: right;
        }

        .portfolio-balance-card .balance-module-qty {
          color: var(--text-muted);
          font-size: .72rem;
          margin-top: .28rem;
          text-align: right;
        }

        .portfolio-balance-card .balance-real {
          margin-top: 1.35rem;
          border-top: 1px solid rgba(201,168,76,.12);
          padding-top: 1rem;
        }

        .portfolio-balance-card .balance-real-title {
          color: var(--text);
          font-size: .8rem;
          letter-spacing: .08em;
          text-transform: uppercase;
          margin-bottom: .65rem;
        }

        .portfolio-balance-card .balance-real-row {
          display: flex;
          justify-content: space-between;
          color: var(--text-muted);
          font-size: .78rem;
          padding: .35rem 0;
        }

        .portfolio-balance-card .balance-updated {
          color: var(--text-muted);
          font-size: .78rem;
          margin-top: 1.25rem;
          opacity: .75;
        }

        .portfolio-balance-card .balance-error {
          color: #E89A9A;
          font-size: .88rem;
        }

        @media (max-width: 700px) {
          .portfolio-balance-card .balance-header {
            flex-direction: column;
            align-items: flex-start;
          }

          .portfolio-balance-card .balance-total {
            text-align: left;
          }

          .portfolio-balance-card .balance-module {
            flex-direction: column;
            align-items: flex-start;
          }

          .portfolio-balance-card .balance-module-value,
          .portfolio-balance-card .balance-module-qty {
            text-align: left;
          }
        }
      `}</style>

      {isLoading ? (
        <p className="loading-text">Loading balance...</p>
      ) : error || !data ? (
        <p className="balance-error">
          Unable to load balance. Connect your broker or wait for FA onboarding.
        </p>
      ) : (
        <>
          <div className="balance-header">
            <div>
              <p className="section-label">Portfolio</p>
              <h2 className="balance-title">Balance</h2>
              <p className="balance-subnote">
                Modules are tracked by AuroRatio’s virtual ledger. Broker
                positions are displayed separately.
              </p>
            </div>

            <div className="balance-total">
              <p className="field-label">Displayed total value</p>
              <p className="balance-total-value">
                CHF {Number(data.total_chf || 0).toLocaleString()}
              </p>
            </div>
          </div>

          <div className="balance-list">
            {modules.map((module: any) => (
              <article key={module.code || module.module_name} className="balance-module">
                <div>
                  <p className="balance-module-name">
                    {module.name || module.display_name}
                  </p>
                  <p className="balance-module-metal">
                    {module.current_metal || module.metal} · {module.etf_symbol}
                  </p>
                  <span className="balance-module-badge">
                    {module.is_enabled === false ? "Disabled" : "Enabled"}
                  </span>
                </div>

                <div>
                  <p className="balance-module-value">
                    CHF {Number(module.value_chf || 0).toLocaleString()}
                  </p>
                  <p className="balance-module-qty">
                    Qty: {Number(module.quantity || 0).toLocaleString()}
                  </p>
                </div>
              </article>
            ))}
          </div>

          {realPositions.length > 0 && (
            <div className="balance-real">
              <p className="balance-real-title">Broker display positions</p>
              {realPositions.map((position: any) => (
                <div
                  key={`${position.symbol}-${position.metal}`}
                  className="balance-real-row"
                >
                  <span>
                    {position.symbol} · {position.metal} · Qty{" "}
                    {Number(position.quantity || 0).toLocaleString()}
                  </span>
                  <span>
                    CHF {Number(position.value_chf || 0).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          )}

          <p className="balance-updated">
            Last updated:{" "}
            {data.last_synced
              ? new Date(data.last_synced).toLocaleTimeString()
              : "—"}
          </p>
        </>
      )}
    </section>
  );
}