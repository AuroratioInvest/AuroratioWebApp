import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getAllUsers, toggleUserActive } from "../api/auth";
import NavHeader from "../components/layout/NavHeader";
import {
  runExecutionNow,
  getExecutionLogs,
  getLatestBotReport,
} from "../api/execution";
import {
  getFaUsers,
  getFaUserDetail,
  activateFaAuthorization,
  updateFaAuthorization,
  enableUserTrading,
  disableUserTrading,
  updateTradingControls,
  updateAdminModulePosition,
} from "../api/adminFA";

const MODULE_LABELS: Record<string, string> = {
  M1: "Module 1 — AU/AG",
  M2: "Module 2 — AU/PT",
  M3: "Module 3 — AU/PD",
  module1: "Module 1 — AU/AG",
  module2: "Module 2 — AU/PT",
  module3: "Module 3 — AU/PD",
};

export default function Admin() {
  const queryClient = useQueryClient();
  const currentUserId = localStorage.getItem("user_id");

  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [mappingForm, setMappingForm] = useState({
    advisor_master_account_id: "",
    ibkr_client_account_id: "",
    account_alias: "",
    base_currency: "CHF",
  });

  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: getAllUsers,
  });

  const { data: faUsers } = useQuery({
    queryKey: ["admin-fa-users"],
    queryFn: getFaUsers,
  });

  const { data: selectedFaDetail } = useQuery({
    queryKey: ["admin-fa-user-detail", selectedUserId],
    queryFn: () => getFaUserDetail(selectedUserId as string),
    enabled: Boolean(selectedUserId),
  });

  const { data: logs, isLoading: logsLoading } = useQuery({
    queryKey: ["execution-logs"],
    queryFn: () => getExecutionLogs(),
  });

  const { data: latestReport, isLoading: reportLoading } = useQuery({
    queryKey: ["latest-bot-report"],
    queryFn: getLatestBotReport,
  });

  const refreshAdmin = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    queryClient.invalidateQueries({ queryKey: ["admin-fa-users"] });
    queryClient.invalidateQueries({ queryKey: ["admin-fa-user-detail"] });
    queryClient.invalidateQueries({ queryKey: ["execution-logs"] });
    queryClient.invalidateQueries({ queryKey: ["latest-bot-report"] });
  };

  const toggleMutation = useMutation({
    mutationFn: (userId: string) => toggleUserActive(userId),
    onSuccess: refreshAdmin,
  });

  const runNowMutation = useMutation({
    mutationFn: () => runExecutionNow(),
    onSuccess: refreshAdmin,
  });

  const activateFaMutation = useMutation({
    mutationFn: (userId: string) =>
      activateFaAuthorization(userId, {
        user_id: userId,
        advisor_master_account_id: mappingForm.advisor_master_account_id.trim(),
        ibkr_client_account_id: mappingForm.ibkr_client_account_id.trim(),
        account_alias: mappingForm.account_alias.trim() || null,
        base_currency: mappingForm.base_currency.trim() || "CHF",
        is_active: true,
        trading_enabled: true,
      }),
    onSuccess: refreshAdmin,
  });

  const updateFaStatusMutation = useMutation({
    mutationFn: ({ userId, status }: { userId: string; status: string }) =>
      updateFaAuthorization(userId, { status }),
    onSuccess: refreshAdmin,
  });

  const enableTradingMutation = useMutation({
    mutationFn: (userId: string) => enableUserTrading(userId),
    onSuccess: refreshAdmin,
  });

  const disableTradingMutation = useMutation({
    mutationFn: (userId: string) => disableUserTrading(userId),
    onSuccess: refreshAdmin,
  });

  const updateControlsMutation = useMutation({
    mutationFn: ({
      userId,
      payload,
    }: {
      userId: string;
      payload: Record<string, boolean | string>;
    }) => updateTradingControls(userId, payload),
    onSuccess: refreshAdmin,
  });

  const updateModuleMutation = useMutation({
    mutationFn: ({
      positionId,
      payload,
    }: {
      positionId: string;
      payload: Record<string, any>;
    }) => updateAdminModulePosition(positionId, payload),
    onSuccess: refreshAdmin,
  });

  const sortedUsers = users
    ? [...users].sort((a: any, b: any) => {
        if (a.id === currentUserId) return -1;
        if (b.id === currentUserId) return 1;
        return 0;
      })
    : [];

  const faByUserId = useMemo(() => {
    const map: Record<string, any> = {};
    (faUsers || []).forEach((row: any) => {
      map[row.user_id] = row;
    });
    return map;
  }, [faUsers]);

  const botReport = latestReport?.summary_text;

  const getUserLabel = (userId: string) => {
    const user = users?.find((u: any) => u.id === userId);

    if (!user) return `${userId.slice(0, 8)}…`;

    return `${user.email} · ${user.id.slice(0, 8)}`;
  };

  const groupedLogs = logs
    ? logs.reduce((groups: any, log: any) => {
        const dateKey = new Date(log.created_at).toLocaleDateString();
        if (!groups[dateKey]) groups[dateKey] = [];
        groups[dateKey].push(log);
        return groups;
      }, {})
    : {};

  return (
    <div className="admin-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

        .admin-page {
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
        }

        .admin-main {
          max-width: 1280px;
          margin: 0 auto;
          padding: 3rem;
        }

        .admin-hero {
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

        .admin-subtitle {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(2rem, 3vw, 2.8rem);
          font-weight: 300;
          line-height: 1.05;
          color: var(--text);
        }

        .admin-subtitle em {
          color: var(--gold-light);
          font-style: italic;
        }

        .admin-stats {
          display: flex;
          gap: .75rem;
          flex-wrap: wrap;
          justify-content: flex-end;
        }

        .stat-pill {
          border: 1px solid var(--rule);
          background: rgba(201,168,76,.025);
          border-radius: 999px;
          padding: .55rem .9rem;
          color: var(--text-muted);
          font-size: .78rem;
        }

        .stat-pill span { color: var(--text); }
        .active { color: #5A9E72; }
        .inactive { color: #C96A6A; }

        .admin-section { margin-top: 3rem; }
        .admin-section-header { margin-bottom: 1rem; }

        .admin-table-card {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          overflow: hidden;
          box-shadow: 0 24px 80px rgba(0,0,0,.28);
        }

        .admin-table {
          width: 100%;
          border-collapse: collapse;
          font-size: .9rem;
        }

        .admin-table thead { background: var(--ink-3); }

        .admin-table th {
          color: var(--text-muted);
          font-size: .68rem;
          text-transform: uppercase;
          letter-spacing: .14em;
          font-weight: 700;
          padding: 1rem 1.25rem;
          text-align: left;
          border-bottom: 1px solid var(--rule);
        }

        .admin-table td {
          padding: 1.1rem 1.25rem;
          border-bottom: 1px solid rgba(201,168,76,.1);
          color: var(--text-muted);
          vertical-align: top;
        }

        .admin-table tr:last-child td { border-bottom: none; }
        .admin-table tbody tr:hover { background: rgba(201,168,76,.035); }
        .admin-table tbody tr.is-me { background: rgba(201,168,76,.055); }

        .email-cell { color: var(--text) !important; }

        .badge {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: .28rem .65rem;
          font-size: .72rem;
          font-weight: 600;
          border: 1px solid transparent;
          white-space: nowrap;
        }

        .badge-gold { background: rgba(201,168,76,.12); color: var(--gold-light); border-color: rgba(201,168,76,.22); }
        .badge-blue { background: rgba(144,224,239,.1); color: #90E0EF; border-color: rgba(144,224,239,.2); }
        .badge-muted { background: rgba(232,228,216,.06); color: var(--text-muted); border-color: rgba(232,228,216,.08); }
        .badge-success { background: rgba(90,158,114,.12); color: #5A9E72; border-color: rgba(90,158,114,.22); }
        .badge-danger { background: rgba(158,90,90,.14); color: #C96A6A; border-color: rgba(158,90,90,.24); }
        .badge-warn { background: rgba(232,201,122,.1); color: var(--gold-light); border-color: rgba(232,201,122,.22); }

        .you-badge { margin-left: .5rem; }

        .action-btn {
          background: transparent;
          border: 1px solid var(--rule);
          border-radius: 4px;
          padding: .45rem .75rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .75rem;
          cursor: pointer;
          transition: all .2s;
          color: var(--text-muted);
          margin: .15rem;
        }

        .action-btn.activate { border-color: rgba(90,158,114,.32); color: #5A9E72; }
        .action-btn.deactivate { border-color: rgba(158,90,90,.35); color: #C96A6A; }
        .action-btn.gold { border-color: rgba(201,168,76,.32); color: var(--gold-light); }
        .action-btn:hover:not(:disabled) { background: rgba(201,168,76,.06); transform: translateY(-1px); }
        .action-btn:disabled { opacity: .5; cursor: not-allowed; }

        .input-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: .75rem;
          margin-bottom: 1rem;
        }

        .admin-input {
          background: rgba(255,255,255,.025);
          border: 1px solid var(--rule);
          color: var(--text);
          border-radius: 6px;
          padding: .75rem .85rem;
          font-family: 'DM Sans', sans-serif;
        }

        .detail-panel {
          padding: 1.5rem;
          display: grid;
          gap: 1.25rem;
        }

        .detail-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 1rem;
        }

        .detail-card {
          border: 1px solid var(--rule);
          border-radius: 8px;
          padding: 1rem;
          background: rgba(255,255,255,.018);
        }

        .detail-title {
          color: var(--text);
          font-weight: 600;
          margin-bottom: .5rem;
        }

        .detail-text {
          color: var(--text-muted);
          font-size: .84rem;
          line-height: 1.55;
        }

        .module-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 1rem;
        }

        .module-card {
          border: 1px solid var(--rule);
          border-radius: 8px;
          padding: 1rem;
          background: rgba(201,168,76,.025);
        }

        .log-date-row td {
          background: rgba(201,168,76,.06);
          color: var(--gold-light);
          font-family: 'Syncopate', sans-serif;
          font-size: .65rem;
          letter-spacing: .12em;
          text-transform: uppercase;
          padding: .75rem 1.25rem !important;
        }

        .loading-text, .empty-action {
          color: var(--text-muted);
          font-size: .9rem;
        }

        @media (max-width: 1000px) {
          .admin-main { padding: 2rem 1rem; }
          .admin-hero { align-items: flex-start; flex-direction: column; }
          .admin-table-card { overflow-x: auto; }
          .admin-table { min-width: 960px; }
          .input-grid, .detail-grid, .module-grid { grid-template-columns: 1fr; }
        }
      `}</style>

      <NavHeader />

      <main className="admin-main">
        <div className="admin-hero">
          <div>
            <p className="section-label">Admin Console</p>
            <h1 className="admin-subtitle">
              User <em>Management</em>
            </h1>
          </div>

          <div className="admin-stats">
            <div className="stat-pill">
              Total: <span>{users?.length ?? 0}</span>
            </div>
            <div className="stat-pill">
              Active:{" "}
              <span className="active">
                {users?.filter((u: any) => u.is_active).length ?? 0}
              </span>
            </div>
            <div className="stat-pill">
              Trading:{" "}
              <span className="active">
                {faUsers?.filter((u: any) => u.trading_enabled).length ?? 0}
              </span>
            </div>

            <button
              className="action-btn activate"
              onClick={() => runNowMutation.mutate()}
              disabled={runNowMutation.isPending}
            >
              {runNowMutation.isPending ? "Running..." : "Run System Now"}
            </button>
            <Link className="action-btn gold" to="/admin/private-channel-operations">
              Private Channel Operations
            </Link>
          </div>
        </div>

        {isLoading ? (
          <p className="loading-text">Loading users...</p>
        ) : (
          <div className="admin-table-card">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Level</th>
                  <th>Status</th>
                  <th>FA</th>
                  <th>IBKR Account</th>
                  <th>Trading</th>
                  <th>Joined</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {sortedUsers.map((user: any) => {
                  const isMe = user.id === currentUserId;
                  const fa = faByUserId[user.id];

                  const levelClass =
                    user.membership_level === "aurum"
                      ? "badge-gold"
                      : user.membership_level === "founder"
                      ? "badge-blue"
                      : "badge-muted";

                  return (
                    <tr key={user.id} className={isMe ? "is-me" : ""}>
                      <td className="email-cell">
                        {user.email}
                        {isMe && <span className="badge badge-gold you-badge">You</span>}
                      </td>

                      <td>
                        <span className={`badge ${levelClass}`}>
                          {user.membership_level}
                        </span>
                      </td>

                      <td>
                        <span className={`badge ${user.is_active ? "badge-success" : "badge-danger"}`}>
                          {user.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>

                      <td>
                        <span
                          className={`badge ${
                            fa?.fa_status === "active"
                              ? "badge-success"
                              : fa?.fa_status
                              ? "badge-warn"
                              : "badge-muted"
                          }`}
                        >
                          {fa?.fa_status || "not started"}
                        </span>
                      </td>

                      <td>{fa?.ibkr_client_account_id || "—"}</td>

                      <td>
                        <span className={`badge ${fa?.trading_enabled ? "badge-success" : "badge-muted"}`}>
                          {fa?.trading_enabled ? "Enabled" : "Disabled"}
                        </span>
                      </td>

                      <td>{new Date(user.created_at).toLocaleDateString()}</td>

                      <td>
                        <button
                          className="action-btn gold"
                          onClick={() => {
                            setSelectedUserId(user.id);
                            setMappingForm({
                              advisor_master_account_id: fa?.advisor_master_account_id || "",
                              ibkr_client_account_id: fa?.ibkr_client_account_id || "",
                              account_alias: "",
                              base_currency: "CHF",
                            });
                          }}
                        >
                          FA Details
                        </button>

                        {!isMe && (
                          <button
                            onClick={() => toggleMutation.mutate(user.id)}
                            disabled={toggleMutation.isPending}
                            className={`action-btn ${user.is_active ? "deactivate" : "activate"}`}
                          >
                            {user.is_active ? "Deactivate" : "Activate"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {selectedUserId && (
          <section className="admin-section">
            <div className="admin-section-header">
              <p className="section-label">IBKR FA</p>
              <h2 className="admin-subtitle">
                Authorization <em>Control</em>
              </h2>
            </div>

            <div className="admin-table-card detail-panel">
              <div className="detail-grid">
                <div className="detail-card">
                  <div className="detail-title">User</div>
                  <div className="detail-text">
                    {selectedFaDetail?.user?.email || getUserLabel(selectedUserId)}
                  </div>
                </div>

                <div className="detail-card">
                  <div className="detail-title">FA Status</div>
                  <div className="detail-text">
                    {selectedFaDetail?.fa_authorization?.status || "not started"}
                  </div>
                </div>

                <div className="detail-card">
                  <div className="detail-title">Trading</div>
                  <div className="detail-text">
                    {selectedFaDetail?.user?.trading_enabled ? "Enabled" : "Disabled"}
                  </div>
                </div>
              </div>

              <div className="input-grid">
                <input
                  className="admin-input"
                  placeholder="Advisor master account ID"
                  value={mappingForm.advisor_master_account_id}
                  onChange={(e) =>
                    setMappingForm((prev) => ({
                      ...prev,
                      advisor_master_account_id: e.target.value,
                    }))
                  }
                />

                <input
                  className="admin-input"
                  placeholder="IBKR client account ID"
                  value={mappingForm.ibkr_client_account_id}
                  onChange={(e) =>
                    setMappingForm((prev) => ({
                      ...prev,
                      ibkr_client_account_id: e.target.value,
                    }))
                  }
                />

                <input
                  className="admin-input"
                  placeholder="Alias"
                  value={mappingForm.account_alias}
                  onChange={(e) =>
                    setMappingForm((prev) => ({
                      ...prev,
                      account_alias: e.target.value,
                    }))
                  }
                />

                <input
                  className="admin-input"
                  placeholder="Base currency"
                  value={mappingForm.base_currency}
                  onChange={(e) =>
                    setMappingForm((prev) => ({
                      ...prev,
                      base_currency: e.target.value,
                    }))
                  }
                />
              </div>

              <div>
                <button
                  className="action-btn activate"
                  disabled={
                    activateFaMutation.isPending ||
                    !mappingForm.advisor_master_account_id ||
                    !mappingForm.ibkr_client_account_id
                  }
                  onClick={() => activateFaMutation.mutate(selectedUserId)}
                >
                  Activate FA Mapping
                </button>

                <button
                  className="action-btn activate"
                  onClick={() => enableTradingMutation.mutate(selectedUserId)}
                  disabled={enableTradingMutation.isPending}
                >
                  Enable Trading
                </button>

                <button
                  className="action-btn deactivate"
                  onClick={() => disableTradingMutation.mutate(selectedUserId)}
                  disabled={disableTradingMutation.isPending}
                >
                  Disable Trading
                </button>

                <button
                  className="action-btn deactivate"
                  onClick={() =>
                    updateFaStatusMutation.mutate({
                      userId: selectedUserId,
                      status: "revoked",
                    })
                  }
                >
                  Revoke FA
                </button>

                <button
                  className="action-btn gold"
                  onClick={() =>
                    updateFaStatusMutation.mutate({
                      userId: selectedUserId,
                      status: "suspended",
                    })
                  }
                >
                  Suspend FA
                </button>
              </div>

              <div className="module-grid">
                {(selectedFaDetail?.module_positions || []).map((module: any) => (
                  <div className="module-card" key={module.id}>
                    <div className="detail-title">
                      {MODULE_LABELS[module.module_name] || module.module_name}
                    </div>
                    <div className="detail-text">
                      {module.metal} · {module.etf_symbol}
                      <br />
                      Qty: {Number(module.quantity || 0).toLocaleString()}
                      <br />
                      Value: CHF {Number(module.last_value_chf || 0).toLocaleString()}
                    </div>

                    <button
                      className={`action-btn ${module.is_enabled ? "deactivate" : "activate"}`}
                      onClick={() =>
                        updateModuleMutation.mutate({
                          positionId: module.id,
                          payload: { is_enabled: !module.is_enabled },
                        })
                      }
                    >
                      {module.is_enabled ? "Disable Module" : "Enable Module"}
                    </button>

                    <button
                      className="action-btn gold"
                      onClick={() =>
                        updateControlsMutation.mutate({
                          userId: selectedUserId,
                          payload:
                            module.module_name === "M1"
                              ? { m1_enabled: !module.is_enabled }
                              : module.module_name === "M2"
                              ? { m2_enabled: !module.is_enabled }
                              : { m3_enabled: !module.is_enabled },
                        })
                      }
                    >
                      Sync Control
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        <section className="admin-section">
          <div className="admin-section-header">
            <p className="section-label">Execution Monitor</p>
            <h1 className="admin-subtitle">
              System <em>Logs</em>
            </h1>
          </div>

          <div className="admin-table-card">
            {logsLoading ? (
              <p className="loading-text" style={{ padding: "1.5rem" }}>
                Loading logs...
              </p>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Module</th>
                    <th>Provider</th>
                    <th>Operation</th>
                    <th>Status</th>
                    <th>Dry Run</th>
                    <th>Date</th>
                  </tr>
                </thead>

                <tbody>
                  {!logs || logs.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ padding: "2rem", textAlign: "center" }}>
                        No execution logs yet
                      </td>
                    </tr>
                  ) : (
                    Object.entries(groupedLogs).map(([date, dayLogs]: any) => (
                      <>
                        <tr key={`date-${date}`} className="log-date-row">
                          <td colSpan={7}>{date}</td>
                        </tr>

                        {dayLogs.map((log: any) => (
                          <tr key={log.id}>
                            <td>{getUserLabel(log.user_id)}</td>
                            <td>{MODULE_LABELS[log.module_name] || log.module_name || "—"}</td>
                            <td>{log.provider || "—"}</td>
                            <td>
                              {log.from_metal && log.to_metal
                                ? `${log.from_metal} → ${log.to_metal}`
                                : "System operation"}
                            </td>
                            <td>
                              <span
                                className={`badge ${
                                  log.status === "success"
                                    ? "badge-success"
                                    : log.status === "failed"
                                    ? "badge-danger"
                                    : log.status === "skipped"
                                    ? "badge-warn"
                                    : "badge-muted"
                                }`}
                              >
                                {log.status}
                              </span>
                            </td>
                            <td>{log.dry_run ? "Yes" : "No"}</td>
                            <td>{new Date(log.created_at).toLocaleTimeString()}</td>
                          </tr>
                        ))}
                      </>
                    ))
                  )}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="admin-section">
          <div className="admin-section-header">
            <p className="section-label">Daily System Report</p>
            <h2 className="admin-subtitle">
              Portfolio <em>Review</em>
            </h2>
          </div>

          <div className="admin-table-card" style={{ padding: "1.5rem" }}>
            {reportLoading ? (
              <p className="loading-text">Loading report...</p>
            ) : (
              <pre
                style={{
                  margin: 0,
                  color: "var(--text-muted)",
                  fontFamily: "DM Sans, sans-serif",
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.6,
                  fontSize: ".9rem",
                }}
              >
                {botReport || "No report available yet."}
              </pre>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
