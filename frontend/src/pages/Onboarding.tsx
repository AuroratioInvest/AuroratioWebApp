import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { connectBroker, getConnections } from "../api/broker";

type Language = "en" | "fr";

type BrokerConnection = {
  id?: string | number;
  broker_name?: string;
  account_name?: string;
  account_id?: string;
  snaptrade_account_id?: string;
  status?: string;
  is_active?: boolean;
  can_display_portfolio?: boolean;
  can_execute_trades?: boolean;
  role?: string;
};

const copy = {
  en: {
    finalSetup: "Final setup",
    title: "Connect portfolio display.",
    subtitle:
      "AuroRatio uses SnapTrade to display your broker positions. Trading authorization is handled separately through the IBKR Financial Advisor onboarding process.",
    setupStep: "Setup step",
    syncStatus: "Display sync",
    secureAuth: "Secure auth",
    brokerIntegration: "Portfolio display",
    authorizeConnection: "Connect display account",
    cardSubtitle:
      "This connection lets AuroRatio read/display your broker portfolio. It does not activate automated trading. IBKR FA trading access is reviewed separately.",
    checking: "Checking broker connection...",
    checkingSub: "This should only take a moment.",
    pendingSub:
      "Complete the broker login in the popup window. This page refreshes automatically.",
    infoTitle: "By connecting SnapTrade, you authorize AuroRatio to:",
    info1: "View portfolio positions and balances for display.",
    info2: "Synchronize account data for reporting.",
    info3:
      "Keep trading execution separate from display access. FA trading is not enabled here.",
    faTitle: "Trading authorization",
    faText:
      "Automated trading will require your IBKR account to be linked under the AuroRatio Financial Advisor structure. We will guide you through the IBKR onboarding steps separately.",
    connectionNote:
      "This broker connection must belong only to the currently authenticated AuroRatio user.",
    opening: "Opening broker...",
    inProgress: "Connection in progress",
    connect: "Connect display account",
    later: "Do this later",
    finePrint:
      "AuroRatio never receives your broker credentials. Authorization is handled by the broker connection provider.",
    waitingLogin: "Waiting for broker login",
    authenticating: "Authenticating with broker",
    syncing: "Broker connected — syncing display data",
    failed: "Connection failed",
    connecting: "Connecting to broker",
    missingUrl: "Missing broker redirect URL.",
    brokerFailed: "Broker connection failed.",
    portfolioMonitoring: "Portfolio monitoring",
    metalsModules: "Metals ratio modules",
    brokerInfrastructure: "Broker infrastructure",
  },
  fr: {
    finalSetup: "Configuration finale",
    title: "Connectez l’affichage du portefeuille.",
    subtitle:
      "AuroRatio utilise SnapTrade pour afficher vos positions courtier. L’autorisation de trading est gérée séparément via le processus IBKR Financial Advisor.",
    setupStep: "Étape",
    syncStatus: "Synchronisation",
    secureAuth: "Autorisation",
    brokerIntegration: "Affichage portefeuille",
    authorizeConnection: "Connecter le compte d’affichage",
    cardSubtitle:
      "Cette connexion permet à AuroRatio de lire et afficher votre portefeuille. Elle n’active pas le trading automatisé. L’accès trading IBKR FA est validé séparément.",
    checking: "Vérification de la connexion courtier...",
    checkingSub: "Cela ne devrait prendre qu’un instant.",
    pendingSub:
      "Finalisez la connexion courtier dans la fenêtre ouverte. Cette page se met à jour automatiquement.",
    infoTitle: "En connectant SnapTrade, vous autorisez AuroRatio à :",
    info1: "Consulter les positions et soldes pour l’affichage.",
    info2: "Synchroniser les données du compte pour le reporting.",
    info3:
      "Maintenir l’exécution des ordres séparée de l’accès d’affichage. Le trading FA n’est pas activé ici.",
    faTitle: "Autorisation trading",
    faText:
      "Le trading automatisé nécessitera que votre compte IBKR soit lié à la structure Financial Advisor d’AuroRatio. Nous vous guiderons séparément dans les étapes IBKR.",
    connectionNote:
      "Chaque connexion courtier doit appartenir uniquement à l’utilisateur AuroRatio actuellement authentifié.",
    opening: "Ouverture du courtier...",
    inProgress: "Connexion en cours",
    connect: "Connecter le compte d’affichage",
    later: "Le faire plus tard",
    finePrint:
      "AuroRatio ne reçoit jamais vos identifiants courtier. L’autorisation est gérée par le fournisseur de connexion courtier.",
    waitingLogin: "En attente de connexion au courtier",
    authenticating: "Authentification auprès du courtier",
    syncing: "Courtier connecté — synchronisation des données d’affichage",
    failed: "Échec de la connexion",
    connecting: "Connexion au courtier",
    missingUrl: "URL de redirection courtier manquante.",
    brokerFailed: "La connexion au courtier a échoué.",
    portfolioMonitoring: "Suivi du portefeuille",
    brokerInfrastructure: "Infrastructure courtier",
    metalsModules: "Modules de ratios métaux",
  },
} satisfies Record<Language, Record<string, string>>;

function getStoredLanguage(): Language {
  return localStorage.getItem("language") === "fr" ? "fr" : "en";
}

function isBrokerConnected(connection: BrokerConnection) {
  return connection.is_active === true || connection.status === "active";
}

export default function Onboarding() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [language] = useState<Language>(getStoredLanguage());
  const text = copy[language];

  const userKey =
    localStorage.getItem("user_id") ||
    localStorage.getItem("user_email") ||
    "anonymous";

  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    queryClient.removeQueries({ queryKey: ["connections"] });
  }, [queryClient, userKey]);

  const { data: connections = [], isLoading } = useQuery({
    queryKey: ["connections", userKey],
    queryFn: getConnections,
    refetchInterval: 6000,
    staleTime: 0,
  });

  const activeConnection = useMemo(
    () =>
      connections.find((connection: BrokerConnection) =>
        isBrokerConnected(connection)
      ),
    [connections]
  );

  const pendingConnection = useMemo(
    () =>
      connections.find(
        (connection: BrokerConnection) =>
          !isBrokerConnected(connection) &&
          connection.status !== "disconnected"
      ),
    [connections]
  );

  useEffect(() => {
    if (activeConnection) {
      localStorage.removeItem("skipped_onboarding");
      navigate("/dashboard", { replace: true });
    }
  }, [activeConnection, navigate]);

  const handleConnect = async () => {
    setConnecting(true);
    setError("");

    try {
      const { redirect_url } = await connectBroker();

      if (!redirect_url) {
        throw new Error(text.missingUrl);
      }

      window.open(redirect_url, "_blank", "noopener,noreferrer");
      queryClient.invalidateQueries({ queryKey: ["connections", userKey] });
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || text.brokerFailed);
    } finally {
      setConnecting(false);
    }
  };

  const handleSkip = () => {
    localStorage.setItem("skipped_onboarding", "true");
    navigate("/dashboard", { replace: true });
  };

  const getStatusMessage = (status?: string) => {
    switch (status) {
      case "pending":
        return text.waitingLogin;
      case "connecting":
        return text.authenticating;
      case "syncing":
        return text.syncing;
      case "failed":
        return text.failed;
      default:
        return text.connecting;
    }
  };

  return (
    <main className="onboarding-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

        .onboarding-page {
          --gold: #C9A84C;
          --gold-light: #E8C97A;
          --ink: #0A0A08;
          --text: #E8E4D8;
          --text-muted: #8A8670;
          --rule: rgba(201,168,76,.18);
          --danger: #E89A9A;

          min-height: 100vh;
          background:
            radial-gradient(circle at 15% 0%, rgba(201,168,76,.12), transparent 32rem),
            radial-gradient(circle at 85% 15%, rgba(232,201,122,.06), transparent 28rem),
            var(--ink);
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 2rem;
          position: relative;
          overflow: hidden;
        }

        .onboarding-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
          pointer-events: none;
          opacity: .55;
        }

        .onboarding-shell {
          width: 100%;
          max-width: 1120px;
          display: grid;
          grid-template-columns: minmax(0, 1.05fr) minmax(340px, .95fr);
          gap: 2rem;
          position: relative;
          z-index: 1;
        }

        .onboarding-copy,
        .onboarding-card {
          background: rgba(17,17,9,.84);
          border: 1px solid var(--rule);
          border-radius: 10px;
          box-shadow: 0 24px 80px rgba(0,0,0,.38);
          backdrop-filter: blur(14px);
        }

        .onboarding-copy {
          padding: 3rem;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          min-height: 560px;
        }

        .onboarding-card {
          padding: 2.25rem;
          align-self: stretch;
        }

        .brand {
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.7rem;
          margin-bottom: 4rem;
        }

        .brand-gold {
          color: var(--gold-light);
        }

        .brand-muted {
          color: var(--text);
        }

        .eyebrow {
          font-family: 'Syncopate', sans-serif;
          color: var(--gold-light);
          font-size: .72rem;
          letter-spacing: .16em;
          text-transform: uppercase;
          margin-bottom: .85rem;
          font-weight: 700;
        }

        .title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(3.2rem, 7vw, 5.9rem);
          line-height: .88;
          font-weight: 300;
          margin: 0;
          letter-spacing: -.04em;
        }

        .subtitle {
          color: var(--text-muted);
          font-size: 1rem;
          line-height: 1.75;
          max-width: 600px;
          margin: 1.45rem 0 0;
        }

        .trust-row {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1rem;
          margin-top: 3rem;
        }

        .trust-item {
          border-top: 1px solid var(--rule);
          padding-top: 1rem;
        }

        .trust-value {
          font-family: 'Cormorant Garamond', serif;
          color: var(--gold-light);
          font-size: 2rem;
          line-height: 1;
        }

        .trust-label {
          color: var(--text-muted);
          font-size: .74rem;
          letter-spacing: .08em;
          text-transform: uppercase;
          margin-top: .45rem;
        }

        .card-label {
          color: var(--gold-light);
          font-size: .72rem;
          letter-spacing: .18em;
          text-transform: uppercase;
          margin-bottom: .7rem;
          font-weight: 700;
        }

        .card-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 2.35rem;
          line-height: 1;
          font-weight: 300;
          margin: 0 0 .75rem;
        }

        .card-subtitle {
          color: var(--text-muted);
          line-height: 1.65;
          font-size: .95rem;
          margin-bottom: 1.6rem;
        }

        .info-panel,
        .status-box,
        .error-box,
        .fa-panel {
          border-radius: 8px;
          padding: 1.1rem;
          margin-bottom: 1.35rem;
        }

        .info-panel,
        .fa-panel {
          border: 1px solid var(--rule);
          background: rgba(255,255,255,.018);
        }

        .fa-panel {
          background: rgba(201,168,76,.045);
        }

        .info-title,
        .fa-title {
          color: var(--text);
          font-weight: 600;
          margin-bottom: .9rem;
        }

        .fa-text {
          color: var(--text-muted);
          font-size: .88rem;
          line-height: 1.55;
          margin: 0;
        }

        .info-list {
          display: grid;
          gap: .8rem;
          padding: 0;
          margin: 0;
          list-style: none;
        }

        .info-list li {
          display: flex;
          gap: .65rem;
          color: var(--text-muted);
          font-size: .9rem;
          line-height: 1.55;
        }

        .bullet {
          color: var(--gold-light);
        }

        .status-box {
          border: 1px solid rgba(201,168,76,.26);
          background: rgba(201,168,76,.055);
          color: var(--text);
        }

        .status-muted {
          color: var(--text-muted);
          font-size: .88rem;
          margin-top: .35rem;
          line-height: 1.5;
        }

        .error-box {
          border: 1px solid rgba(232,154,154,.3);
          background: rgba(232,154,154,.09);
          color: var(--danger);
          font-size: .9rem;
        }

        .connection-note {
          border: 1px solid rgba(255,255,255,.08);
          background: rgba(255,255,255,.018);
          border-radius: 8px;
          padding: .95rem 1rem;
          color: var(--text-muted);
          font-size: .84rem;
          line-height: 1.55;
          margin-bottom: 1.35rem;
        }

        .actions {
          display: grid;
          gap: .8rem;
        }

        .primary-button,
        .ghost-button {
          border-radius: 5px;
          padding: 1rem 1.35rem;
          font-family: 'DM Sans', sans-serif;
          font-weight: 700;
          font-size: .88rem;
          text-transform: uppercase;
          letter-spacing: .06em;
          cursor: pointer;
          transition: background .2s, color .2s, border-color .2s, opacity .2s;
        }

        .primary-button {
          background: var(--gold);
          color: var(--ink);
          border: none;
        }

        .primary-button:hover:not(:disabled) {
          background: var(--gold-light);
        }

        .primary-button:disabled {
          opacity: .55;
          cursor: not-allowed;
        }

        .ghost-button {
          background: transparent;
          color: var(--text-muted);
          border: 1px solid var(--rule);
        }

        .ghost-button:hover {
          color: var(--gold-light);
          border-color: rgba(201,168,76,.36);
          background: rgba(201,168,76,.06);
        }

        .fine-print {
          color: var(--text-muted);
          font-size: .76rem;
          line-height: 1.6;
          margin-top: 1.4rem;
        }

        @media (max-width: 920px) {
          .onboarding-shell {
            grid-template-columns: 1fr;
          }

          .onboarding-copy {
            min-height: auto;
          }

          .brand {
            margin-bottom: 2.5rem;
          }
        }

        @media (max-width: 640px) {
          .onboarding-page {
            padding: 1rem;
          }

          .onboarding-copy,
          .onboarding-card {
            padding: 1.5rem;
          }

          .trust-row {
            grid-template-columns: 1fr;
          }
        }
      `}</style>

      <div className="onboarding-shell">
        <section className="onboarding-copy">
          <div>
            <div className="brand">
              <span className="brand-gold">Auro</span>
              <span className="brand-muted">Ratio</span>
            </div>

            <p className="eyebrow">{text.finalSetup}</p>
            <h1 className="title">{text.title}</h1>
            <p className="subtitle">{text.subtitle}</p>
          </div>

          <div className="trust-row">
            <div className="trust-item">
              <div className="trust-value">24/7</div>
              <div className="trust-label">{text.portfolioMonitoring}</div>
            </div>

            <div className="trust-item">
              <div className="trust-value">3</div>
              <div className="trust-label">{text.brokerInfrastructure}</div>
            </div>

            <div className="trust-item">
              <div className="trust-value">IBKR</div>
              <div className="trust-label">{text.brokerInfrastructure}</div>
            </div>
          </div>
        </section>

        <section className="onboarding-card">
          <p className="card-label">{text.brokerIntegration}</p>
          <h2 className="card-title">{text.authorizeConnection}</h2>
          <p className="card-subtitle">{text.cardSubtitle}</p>

          {error && <div className="error-box">{error}</div>}

          {isLoading ? (
            <div className="status-box">
              {text.checking}
              <div className="status-muted">{text.checkingSub}</div>
            </div>
          ) : pendingConnection ? (
            <div className="status-box">
              {getStatusMessage(pendingConnection.status)}
              <div className="status-muted">{text.pendingSub}</div>
            </div>
          ) : (
            <div className="info-panel">
              <p className="info-title">{text.infoTitle}</p>
              <ul className="info-list">
                <li>
                  <span className="bullet">•</span>
                  <span>{text.info1}</span>
                </li>
                <li>
                  <span className="bullet">•</span>
                  <span>{text.info2}</span>
                </li>
                <li>
                  <span className="bullet">•</span>
                  <span>{text.info3}</span>
                </li>
              </ul>
            </div>
          )}

          <div className="fa-panel">
            <p className="fa-title">{text.faTitle}</p>
            <p className="fa-text">{text.faText}</p>
          </div>

          <div className="connection-note">{text.connectionNote}</div>

          <div className="actions">
            <button
              type="button"
              className="primary-button"
              onClick={handleConnect}
              disabled={connecting || Boolean(pendingConnection)}
            >
              {connecting
                ? text.opening
                : pendingConnection
                ? text.inProgress
                : text.connect}
            </button>

            <button type="button" className="ghost-button" onClick={handleSkip}>
              {text.later}
            </button>
          </div>

          <p className="fine-print">{text.finePrint}</p>
        </section>
      </div>
    </main>
  );
}