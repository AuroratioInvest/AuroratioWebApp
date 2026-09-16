import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import {
  getPrivateChannelConfiguration,
  getPrivateChannelOperationsOverview,
  type PrivateChannelConfigurationItem,
} from "../api/privateChannelOperations";
import NavHeader from "../components/layout/NavHeader";

type Language = "en" | "fr";

const CHANNEL_PAGE_LIMIT = 25;

const text = {
  en: {
    eyebrow: "Operations",
    title: "Private Channel Operations",
    description:
      "Read-only operational visibility for access delivery, channel readiness, and signal publication workflows.",
    readOnly:
      "This dashboard is read-only in this slice. Processing, retry, and backfill actions will be added later. No automatic scheduler is shown as running here.",
    refresh: "Refresh",
    refreshing: "Refreshing...",
    backToAdmin: "Back to admin",
    loading: "Loading operations status...",
    errorTitle: "Operations status is temporarily unavailable.",
    errorBody: "Refresh the page or verify your administrator session.",
    emptyChannels: "No private channels are configured yet.",
    credentialsConfigured: "Credentials configured",
    credentialsMissing: "Credentials missing",
    totalChannels: "Total private channels",
    readyChannels: "Ready private channels",
    activeMappings: "Active plan mappings",
    pendingAccess: "Pending access deliveries",
    retryableAccess: "Retryable access deliveries",
    terminalAccess: "Terminal access-delivery failures",
    pendingPublications: "Pending signal publications",
    retryablePublications: "Retryable signal publications",
    terminalPublications: "Terminal signal-publication failures",
    approvedSignals: "Approved signals",
    draftSignals: "Draft signals",
    channelReadiness: "Channel readiness",
    channelCode: "Channel code",
    displayName: "Display name",
    state: "State",
    target: "Delivery target",
    ready: "Ready",
    plans: "Plan mappings",
    present: "Present",
    missing: "Missing",
    active: "Active",
    inactive: "Inactive",
    configured: "Configured",
    unconfigured: "Unconfigured",
    archived: "Archived",
    yes: "Yes",
    no: "No",
    noMappings: "No mapped plans",
    nextPage: "Next page",
  },
  fr: {
    eyebrow: "Opérations",
    title: "Opérations du canal privé",
    description:
      "Visibilité opérationnelle en lecture seule sur la livraison des accès, la préparation des canaux et la publication des signaux.",
    readOnly:
      "Ce tableau de bord est en lecture seule dans cette tranche. Le traitement, les relances et le backfill seront ajoutés plus tard. Aucun planificateur automatique n’est indiqué comme actif ici.",
    refresh: "Actualiser",
    refreshing: "Actualisation...",
    backToAdmin: "Retour à l’admin",
    loading: "Chargement de l’état opérationnel...",
    errorTitle: "L’état opérationnel est temporairement indisponible.",
    errorBody: "Actualisez la page ou vérifiez votre session administrateur.",
    emptyChannels: "Aucun canal privé n’est encore configuré.",
    credentialsConfigured: "Identifiants configurés",
    credentialsMissing: "Identifiants manquants",
    totalChannels: "Total des canaux privés",
    readyChannels: "Canaux privés prêts",
    activeMappings: "Mappings actifs",
    pendingAccess: "Livraisons d’accès en attente",
    retryableAccess: "Livraisons d’accès à relancer",
    terminalAccess: "Échecs terminaux de livraison d’accès",
    pendingPublications: "Publications de signaux en attente",
    retryablePublications: "Publications de signaux à relancer",
    terminalPublications: "Échecs terminaux de publication",
    approvedSignals: "Signaux approuvés",
    draftSignals: "Brouillons de signaux",
    channelReadiness: "Préparation des canaux",
    channelCode: "Code du canal",
    displayName: "Nom affiché",
    state: "État",
    target: "Cible de livraison",
    ready: "Prêt",
    plans: "Mappings de plans",
    present: "Présente",
    missing: "Manquante",
    active: "Actif",
    inactive: "Inactif",
    configured: "Configuré",
    unconfigured: "Non configuré",
    archived: "Archivé",
    yes: "Oui",
    no: "Non",
    noMappings: "Aucun plan mappé",
    nextPage: "Page suivante",
  },
} satisfies Record<Language, Record<string, string>>;

function getStoredLanguage(): Language {
  return localStorage.getItem("language") === "fr" ? "fr" : "en";
}

function countValue(counts: Record<string, number> | undefined, key: string) {
  return counts?.[key] ?? 0;
}

function StatusBadge({
  tone,
  children,
}: {
  tone: "success" | "warning" | "danger" | "muted";
  children: React.ReactNode;
}) {
  return <span className={`ops-badge ops-badge-${tone}`}>{children}</span>;
}

function OverviewCard({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string | number;
  tone?: "success" | "warning" | "danger" | "muted";
}) {
  return (
    <article className={`ops-card ops-card-${tone}`}>
      <p>{label}</p>
      <strong>{value}</strong>
    </article>
  );
}

function ChannelState({
  channel,
  labels,
  language,
}: {
  channel: PrivateChannelConfigurationItem;
  labels: typeof text.en;
  language: Language;
}) {
  const displayName =
    language === "fr"
      ? channel.display_name_fr || channel.display_name_en
      : channel.display_name_en || channel.display_name_fr;
  return (
    <tr>
      <td className="ops-primary-cell">
        <span>{channel.channel_code || "—"}</span>
      </td>
      <td>{displayName || "—"}</td>
      <td>
        <div className="ops-badge-stack">
          <StatusBadge tone={channel.is_active ? "success" : "muted"}>
            {channel.is_active ? labels.active : labels.inactive}
          </StatusBadge>
          <StatusBadge tone={channel.is_configured ? "success" : "warning"}>
            {channel.is_configured ? labels.configured : labels.unconfigured}
          </StatusBadge>
          {channel.is_archived && (
            <StatusBadge tone="danger">{labels.archived}</StatusBadge>
          )}
        </div>
      </td>
      <td>
        <StatusBadge tone={channel.has_provider_target ? "success" : "warning"}>
          {channel.has_provider_target ? labels.present : labels.missing}
        </StatusBadge>
      </td>
      <td>
        <StatusBadge tone={channel.is_ready ? "success" : "danger"}>
          {channel.is_ready ? labels.yes : labels.no}
        </StatusBadge>
      </td>
      <td>
        {channel.mappings.length === 0 ? (
          <span className="ops-muted">{labels.noMappings}</span>
        ) : (
          <div className="ops-plan-list">
            {channel.mappings.map((mapping) => (
              <span key={mapping.mapping_id} className="ops-plan-pill">
                {mapping.plan_code || mapping.plan_id}
                <em>{mapping.is_active ? labels.active : labels.inactive}</em>
              </span>
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}

export default function PrivateChannelOperations() {
  const language = getStoredLanguage();
  const labels = text[language];
  const [cursor, setCursor] = useState<string | null>(null);

  const overviewQuery = useQuery({
    queryKey: ["private-channel-operations-overview"],
    queryFn: getPrivateChannelOperationsOverview,
  });
  const channelQuery = useQuery({
    queryKey: ["private-channel-configuration", cursor],
    queryFn: () =>
      getPrivateChannelConfiguration({
        limit: CHANNEL_PAGE_LIMIT,
        afterChannelId: cursor,
      }),
  });

  const isLoading = overviewQuery.isLoading || channelQuery.isLoading;
  const isFetching = overviewQuery.isFetching || channelQuery.isFetching;
  const hasError = overviewQuery.isError || channelQuery.isError;
  const overview = overviewQuery.data;
  const channels = channelQuery.data?.items ?? [];

  const cards = useMemo(
    () => [
      {
        label: overview?.provider_credentials_configured
          ? labels.credentialsConfigured
          : labels.credentialsMissing,
        value: overview?.provider_credentials_configured ? labels.yes : labels.no,
        tone: overview?.provider_credentials_configured ? "success" : "danger",
      },
      {
        label: labels.totalChannels,
        value: overview?.private_channel_counts.total ?? 0,
      },
      {
        label: labels.readyChannels,
        value: overview?.private_channel_counts.ready ?? 0,
        tone: "success",
      },
      {
        label: labels.activeMappings,
        value: overview?.active_plan_channel_mapping_count ?? 0,
      },
      {
        label: labels.pendingAccess,
        value: countValue(overview?.access_fulfillment_counts, "pending"),
        tone: "warning",
      },
      {
        label: labels.retryableAccess,
        value: countValue(overview?.access_fulfillment_counts, "retryable_failure"),
        tone: "warning",
      },
      {
        label: labels.terminalAccess,
        value: countValue(overview?.access_fulfillment_counts, "terminal_failure"),
        tone: "danger",
      },
      {
        label: labels.pendingPublications,
        value: countValue(overview?.signal_publication_counts, "pending"),
        tone: "warning",
      },
      {
        label: labels.retryablePublications,
        value: countValue(overview?.signal_publication_counts, "retryable_failure"),
        tone: "warning",
      },
      {
        label: labels.terminalPublications,
        value: countValue(overview?.signal_publication_counts, "terminal_failure"),
        tone: "danger",
      },
      {
        label: labels.approvedSignals,
        value: overview?.approved_signal_count ?? 0,
        tone: "success",
      },
      {
        label: labels.draftSignals,
        value: overview?.draft_signal_count ?? 0,
      },
    ],
    [labels, overview]
  );

  const refresh = () => {
    setCursor(null);
    void overviewQuery.refetch();
    void channelQuery.refetch();
  };

  return (
    <div className="admin-page ops-page">
      <style>{`
        .ops-page {
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

        .ops-main {
          max-width: 1280px;
          margin: 0 auto;
          padding: 3rem;
        }

        .ops-hero {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 2rem;
          margin-bottom: 2rem;
        }

        .ops-eyebrow {
          font-family: 'Syncopate', sans-serif;
          font-size: .7rem;
          letter-spacing: .15em;
          text-transform: uppercase;
          color: var(--gold);
          margin-bottom: .75rem;
        }

        .ops-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(2rem, 3vw, 3rem);
          font-weight: 300;
          line-height: 1.05;
          margin: 0;
        }

        .ops-description {
          max-width: 760px;
          color: var(--text-muted);
          line-height: 1.7;
          margin: 1rem 0 0;
        }

        .ops-actions {
          display: flex;
          gap: .75rem;
          flex-wrap: wrap;
          justify-content: flex-end;
        }

        .ops-button,
        .ops-link {
          background: transparent;
          border: 1px solid var(--rule);
          color: var(--gold-light);
          border-radius: 999px;
          padding: .65rem 1rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .82rem;
          cursor: pointer;
          text-decoration: none;
        }

        .ops-button:disabled {
          opacity: .55;
          cursor: wait;
        }

        .ops-note,
        .ops-state-panel {
          border: 1px solid var(--rule);
          background: rgba(201,168,76,.035);
          border-radius: 10px;
          padding: 1rem 1.1rem;
          color: var(--text-muted);
          line-height: 1.65;
          margin-bottom: 1.5rem;
        }

        .ops-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 1rem;
          margin-bottom: 2rem;
        }

        .ops-card {
          border: 1px solid var(--rule);
          background: var(--ink-2);
          border-radius: 10px;
          padding: 1rem;
        }

        .ops-card p {
          margin: 0 0 .8rem;
          color: var(--text-muted);
          font-size: .78rem;
          line-height: 1.45;
        }

        .ops-card strong {
          font-size: 1.55rem;
          color: var(--text);
        }

        .ops-card-success strong { color: #6FB586; }
        .ops-card-warning strong { color: var(--gold-light); }
        .ops-card-danger strong { color: #D47575; }

        .ops-section-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          gap: 1rem;
          margin: 2rem 0 1rem;
        }

        .ops-section-header h2 {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(1.6rem, 2.4vw, 2.2rem);
          font-weight: 300;
          margin: 0;
        }

        .ops-table-wrap {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          overflow: hidden;
        }

        .ops-table {
          width: 100%;
          border-collapse: collapse;
          font-size: .9rem;
        }

        .ops-table thead {
          background: var(--ink-3);
        }

        .ops-table th {
          color: var(--text-muted);
          font-size: .68rem;
          text-transform: uppercase;
          letter-spacing: .14em;
          font-weight: 700;
          padding: 1rem;
          text-align: left;
          border-bottom: 1px solid var(--rule);
        }

        .ops-table td {
          padding: 1rem;
          border-bottom: 1px solid rgba(201,168,76,.1);
          color: var(--text-muted);
          vertical-align: top;
        }

        .ops-table tr:last-child td {
          border-bottom: none;
        }

        .ops-primary-cell span {
          color: var(--text);
          font-weight: 600;
        }

        .ops-badge-stack,
        .ops-plan-list {
          display: flex;
          flex-wrap: wrap;
          gap: .4rem;
        }

        .ops-badge,
        .ops-plan-pill {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          padding: .28rem .65rem;
          font-size: .72rem;
          font-weight: 600;
          border: 1px solid transparent;
        }

        .ops-badge-success {
          background: rgba(90,158,114,.12);
          color: #6FB586;
          border-color: rgba(90,158,114,.22);
        }

        .ops-badge-warning {
          background: rgba(232,201,122,.1);
          color: var(--gold-light);
          border-color: rgba(232,201,122,.22);
        }

        .ops-badge-danger {
          background: rgba(158,90,90,.14);
          color: #D47575;
          border-color: rgba(158,90,90,.24);
        }

        .ops-badge-muted,
        .ops-plan-pill {
          background: rgba(232,228,216,.06);
          color: var(--text-muted);
          border-color: rgba(232,228,216,.08);
        }

        .ops-plan-pill {
          gap: .45rem;
        }

        .ops-plan-pill em {
          color: var(--gold-light);
          font-style: normal;
        }

        .ops-muted {
          color: var(--text-muted);
        }

        .ops-pagination {
          display: flex;
          justify-content: flex-end;
          margin-top: 1rem;
        }

        @media (max-width: 1050px) {
          .ops-main { padding: 2rem 1rem; }
          .ops-hero,
          .ops-section-header {
            flex-direction: column;
            align-items: flex-start;
          }
          .ops-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .ops-table-wrap {
            overflow-x: auto;
          }
          .ops-table {
            min-width: 920px;
          }
        }

        @media (max-width: 640px) {
          .ops-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>

      <NavHeader />

      <main className="ops-main">
        <header className="ops-hero">
          <div>
            <p className="ops-eyebrow">{labels.eyebrow}</p>
            <h1 className="ops-title">{labels.title}</h1>
            <p className="ops-description">{labels.description}</p>
          </div>
          <div className="ops-actions">
            <Link className="ops-link" to="/admin">
              {labels.backToAdmin}
            </Link>
            <button
              className="ops-button"
              type="button"
              onClick={refresh}
              disabled={isFetching}
            >
              {isFetching ? labels.refreshing : labels.refresh}
            </button>
          </div>
        </header>

        <p className="ops-note">{labels.readOnly}</p>

        {isLoading && (
          <section className="ops-state-panel" aria-live="polite">
            {labels.loading}
          </section>
        )}

        {hasError && (
          <section className="ops-state-panel" role="alert">
            <strong>{labels.errorTitle}</strong>
            <br />
            {labels.errorBody}
          </section>
        )}

        {!hasError && overview && (
          <section aria-labelledby="ops-overview-heading">
            <h2 id="ops-overview-heading" className="ops-section-header">
              <span>{labels.title}</span>
            </h2>
            <div className="ops-grid">
              {cards.map((card) => (
                <OverviewCard
                  key={card.label}
                  label={card.label}
                  value={card.value}
                  tone={card.tone as "success" | "warning" | "danger" | "muted"}
                />
              ))}
            </div>
          </section>
        )}

        {!hasError && (
          <section aria-labelledby="ops-channel-heading">
            <div className="ops-section-header">
              <h2 id="ops-channel-heading">{labels.channelReadiness}</h2>
            </div>

            {!channelQuery.isLoading && channels.length === 0 ? (
              <div className="ops-state-panel">{labels.emptyChannels}</div>
            ) : (
              <div className="ops-table-wrap">
                <table className="ops-table">
                  <thead>
                    <tr>
                      <th>{labels.channelCode}</th>
                      <th>{labels.displayName}</th>
                      <th>{labels.state}</th>
                      <th>{labels.target}</th>
                      <th>{labels.ready}</th>
                      <th>{labels.plans}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {channels.map((channel) => (
                      <ChannelState
                        key={channel.private_channel_id}
                        channel={channel}
                        labels={labels}
                        language={language}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {channelQuery.data?.has_more && (
              <div className="ops-pagination">
                <button
                  className="ops-button"
                  type="button"
                  disabled={channelQuery.isFetching}
                  onClick={() => setCursor(channelQuery.data?.next_cursor ?? null)}
                >
                  {labels.nextPage}
                </button>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
