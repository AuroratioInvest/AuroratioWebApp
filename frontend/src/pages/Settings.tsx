import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import NavHeader from "../components/layout/NavHeader";
import client from "../api/client";

const getConnections = async () => (await client.get("/broker/connections")).data;
const connectBroker = async () => (await client.post("/broker/connect")).data;
const disconnectBroker = async () => (await client.delete("/broker/disconnect")).data;

export default function Settings() {
  const queryClient = useQueryClient();
  const [connecting, setConnecting] = useState(false);
  const [searchParams] = useSearchParams();

  const { data: connections, isLoading } = useQuery({
    queryKey: ["connections"],
    queryFn: getConnections,
    refetchInterval: 10000,
  });

  const activeConnection = connections?.find(
    (c: any) => c.is_active === true || c.status === "active"
  );

  const pendingConnection = connections?.find(
    (c: any) =>
      !(c.is_active === true || c.status === "active") &&
      c.status !== "disconnected"
  );

  const disconnectMutation = useMutation({
    mutationFn: disconnectBroker,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["connections"] }),
  });

  const handleConnect = async () => {
    localStorage.removeItem("skipped_onboarding");
    setConnecting(true);

    try {
      const { redirect_url } = await connectBroker();
      window.open(redirect_url, "_blank");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    } catch (err) {
      console.error("Connection failed:", err);
    } finally {
      setConnecting(false);
    }
  };

  const handleConnectDifferentBroker = async () => {
    const confirmed = window.confirm(
      "This will disconnect your current broker before connecting a different one. Continue?"
    );

    if (!confirmed) return;

    localStorage.removeItem("skipped_onboarding");
    setConnecting(true);

    try {
      await disconnectBroker();
      queryClient.invalidateQueries({ queryKey: ["connections"] });

      const { redirect_url } = await connectBroker();

      if (!redirect_url) {
        throw new Error("Missing broker redirect URL.");
      }

      window.open(redirect_url, "_blank", "noopener,noreferrer");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    } catch (err) {
      console.error("Connection failed:", err);
    } finally {
      setConnecting(false);
    }
  };

  const handleCancel = async () => {
    try {
      await client.delete("/broker/disconnect");
      localStorage.removeItem("skipped_onboarding");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    } catch (err) {
      console.error("Disconnect failed:", err);
    }
  };

  const getStatusDisplay = (status: string) => {
    switch (status) {
      case "pending":
        return {
          label: "Waiting for broker login...",
          className: "badge-warning",
          icon: "...",
          message: "Complete the broker login process to activate your connection.",
        };
      case "connecting":
        return {
          label: "Connecting to broker...",
          className: "badge-gold",
          icon: "↻",
          message: "Establishing secure connection with your broker...",
        };
      case "syncing":
        return {
          label: "Syncing portfolio data...",
          className: "badge-gold",
          icon: "↔",
          message: "Your broker is connected. Portfolio data is still syncing in the background.",
        };
      case "active":
        return {
          label: "Connected",
          className: "badge-success",
          icon: "✓",
          message: "",
        };
      case "failed":
        return {
          label: "Connection failed",
          className: "badge-danger",
          icon: "✗",
          message: "Connection failed. Please try disconnecting and reconnecting.",
        };
      default:
        return {
          label: "Unknown status",
          className: "badge-muted",
          icon: "?",
          message: "",
        };
    }
  };

  useEffect(() => {
    if (searchParams.get("connected") === "true") {
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    }
  }, [searchParams, queryClient]);

  return (
    <div className="settings-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

        .settings-page {
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
          position: relative;
          overflow-x: hidden;
        }

        .settings-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
          pointer-events: none;
          opacity: .45;
        }

        .settings-main {
          position: relative;
          max-width: 1180px;
          margin: 0 auto;
          padding: 3rem;
        }

        .settings-hero {
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

        .settings-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(2.4rem, 5vw, 4rem);
          font-weight: 300;
          line-height: 1.05;
          color: var(--text);
        }

        .settings-subtitle {
          max-width: 920px;
          color: var(--text-muted);
          font-size: .95rem;
          line-height: 1.65;
          margin-top: 1.1rem;
        }

        .settings-card {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 2rem;
          box-shadow: 0 24px 80px rgba(0,0,0,.28);
        }

        .connection-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 2rem;
        }

        .connection-name {
          color: var(--text);
          font-size: 1.1rem;
          font-weight: 600;
          margin-bottom: .6rem;
        }

        .connection-meta {
          color: var(--text-muted);
          font-size: .82rem;
          font-family: monospace;
          margin-bottom: .8rem;
        }

        .badge {
          display: inline-flex;
          align-items: center;
          gap: .45rem;
          border-radius: 999px;
          padding: .35rem .7rem;
          font-size: .72rem;
          font-weight: 600;
          border: 1px solid transparent;
        }

        .badge-gold {
          background: rgba(201,168,76,.12);
          color: var(--gold-light);
          border-color: rgba(201,168,76,.22);
        }

        .badge-warning {
          background: rgba(201,168,76,.1);
          color: var(--gold);
          border-color: rgba(201,168,76,.2);
        }

        .badge-success {
          background: rgba(90,158,114,.12);
          color: #5A9E72;
          border-color: rgba(90,158,114,.22);
        }

        .badge-danger {
          background: rgba(158,90,90,.14);
          color: #C96A6A;
          border-color: rgba(158,90,90,.24);
        }

        .badge-muted {
          background: rgba(232,228,216,.06);
          color: var(--text-muted);
          border-color: rgba(232,228,216,.08);
        }

        .message-text {
          color: var(--text-muted);
          font-size: .85rem;
          line-height: 1.55;
          margin-top: .9rem;
          max-width: 620px;
        }

        .primary-btn {
          background: var(--gold);
          color: var(--ink);
          border: 1px solid var(--gold);
          border-radius: 4px;
          padding: .75rem 1rem;
          font-size: .75rem;
          font-weight: 700;
          letter-spacing: .09em;
          text-transform: uppercase;
          transition: all .2s;
        }

        .primary-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          background: var(--gold-light);
        }

        .danger-btn {
          background: transparent;
          border: 1px solid rgba(158,90,90,.35);
          color: #C96A6A;
          border-radius: 4px;
          padding: .55rem .85rem;
          font-size: .75rem;
          cursor: pointer;
          transition: all .2s;
        }

        .danger-btn:hover:not(:disabled) {
          background: rgba(158,90,90,.1);
          transform: translateY(-1px);
        }

        .link-btn {
          color: var(--gold);
          font-size: .78rem;
          text-decoration: underline;
          text-underline-offset: 4px;
        }

        .muted {
          color: var(--text-muted);
        }

        .empty-title {
          color: var(--text);
          font-size: 1.05rem;
          font-weight: 600;
          margin-bottom: .5rem;
        }

        .auth-box {
          background: rgba(201,168,76,.025);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 1.25rem;
          margin: 1.5rem auto;
          max-width: 640px;
          text-align: left;
        }

        .auth-box p,
        .auth-box li {
          font-size: .85rem;
        }

        .loading-text {
          color: var(--text-muted);
          font-size: .9rem;
        }

        @media (max-width: 900px) {
          .settings-main {
            padding: 2rem 1rem;
          }

          .connection-header {
            flex-direction: column;
          }

          .settings-card {
            padding: 1.5rem;
          }
        }
      `}</style>

      <NavHeader />

      <main className="settings-main">
        <div className="settings-hero">
          <p className="section-label">Settings</p>
          <h1 className="settings-title">Broker Connection</h1>
          <p className="settings-subtitle">
            Connect your broker account so AuroRatio can synchronize your portfolio
            and support your authorized account workflow. Your credentials are
            handled securely by SnapTrade. We never see them.
          </p>
        </div>

        {isLoading ? (
          <p className="loading-text">Loading connection...</p>
        ) : activeConnection ? (
          <div className="settings-card">
            {(() => {
              const statusInfo = getStatusDisplay(activeConnection.status);

              return (
                <div className="connection-header">
                  <div>
                    <p className="connection-name">
                      {activeConnection.broker_name === "Pending" ||
                      activeConnection.broker_name === "Unknown Broker"
                        ? "Broker Account"
                        : activeConnection.broker_name}
                    </p>

                    {activeConnection.snaptrade_account_id && (
                      <p className="connection-meta">
                        {activeConnection.snaptrade_account_id.slice(0, 8)}...
                      </p>
                    )}

                    <span className={`badge ${statusInfo.className}`}>
                      <span>{statusInfo.icon}</span>
                      <span>{statusInfo.label}</span>
                    </span>

                    {statusInfo.message && (
                      <p className="message-text">{statusInfo.message}</p>
                    )}
                  </div>

                  <button
                    onClick={() => disconnectMutation.mutate()}
                    disabled={disconnectMutation.isPending}
                    className="danger-btn"
                  >
                    {disconnectMutation.isPending ? "Disconnecting..." : "Disconnect"}
                  </button>
                </div>
              );
            })()}

            <div className="text-center mt-6">
              <button
                onClick={handleConnectDifferentBroker}
                disabled={connecting}
                className="link-btn"
              >
                {connecting ? "Redirecting..." : "Connect a different broker"}
              </button>
            </div>
          </div>
        ) : pendingConnection ? (
          <div className="settings-card text-center">
            {(() => {
              const statusInfo = getStatusDisplay(pendingConnection.status);

              return (
                <>
                  <span className={`badge ${statusInfo.className}`}>
                    <span>{statusInfo.icon}</span>
                    <span>{statusInfo.label}</span>
                  </span>

                  <p className="empty-title mt-5">Connection in progress</p>

                  {statusInfo.message && (
                    <p className="message-text mx-auto">{statusInfo.message}</p>
                  )}
                </>
              );
            })()}

            {pendingConnection.broker_name &&
              pendingConnection.broker_name !== "Pending" &&
              pendingConnection.broker_name !== "Unknown Broker" && (
                <p className="muted text-sm mt-5">
                  Broker: {pendingConnection.broker_name}
                </p>
              )}

            {(pendingConnection.status === "pending" ||
              pendingConnection.status === "failed") && (
              <div className="flex items-center justify-center gap-5 mt-7">
                <button onClick={handleConnect} disabled={connecting} className="link-btn">
                  {connecting
                    ? "Redirecting..."
                    : pendingConnection.status === "failed"
                    ? "Try again"
                    : "Reopen SnapTrade"}
                </button>

                <span className="text-[#3a372d]">|</span>

                <button
                  onClick={handleCancel}
                  className="text-sm text-[#5f5b4c] hover:text-red-400 transition"
                >
                  Cancel and start over
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="settings-card text-center">
            <p className="empty-title">No broker connected</p>

            <p className="muted text-sm leading-relaxed">
              Supports Interactive Brokers, eToro, Fidelity and more.
              <br />
              Some brokers require additional activation time after setup.
            </p>

            <div className="auth-box">
              <p className="text-[#E8E4D8] mb-3">
                By connecting your broker, you authorize AuroRatio to:
              </p>

              <ul className="space-y-2 muted mb-4">
                <li>• View your portfolio positions</li>
                <li>• Display account balances</li>
                <li>• Synchronize account data for portfolio tracking</li>
              </ul>

              <p className="muted text-xs">
                ✓ Your credentials are secured by SnapTrade. We never see them.
              </p>
            </div>

            <button onClick={handleConnect} disabled={connecting} className="primary-btn">
              {connecting ? "Redirecting to SnapTrade..." : "I understand and authorize"}
            </button>

            <p className="text-[#5f5b4c] text-xs mt-4">
              Secured by SnapTrade. Your broker credentials never touch our servers.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}