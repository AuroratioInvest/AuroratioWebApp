import { useEffect } from "react";
import Ticker from "../components/Ticker";
import PublicFooter from "../components/PublicFooter";
import PublicHeader from "../components/PublicHeader";
import PublicCheckoutError from "../components/PublicCheckoutError";
import type { MarketData } from "../types/market";
import { usePublicCheckout } from "../hooks/usePublicCheckout";
import { usePublicLanguage, type PublicLanguage } from "../context/PublicLanguageContext";

interface PlatformProps {
  marketData: MarketData;
  marketDataAvailable: boolean;
}

const copy = {
  en: {
    how: "How it works",
    features: "Benefits",
    platform: "Methodology",
    performance: "Historical research",
    pricing: "Pricing",
    faq: "FAQ",
    contact: "Contact",

    heroLabel: "The Methodology",
    heroTitle1: "Disciplined analysis",
    heroTitle2: "for independent execution",
    heroSub:
      "AuroRatio studies relative-value relationships across precious metals, applies a structured review process, and delivers approved signals through a private members channel.",

    whyLabel: "Why precious metals",
    whyTitle1: "A long-term",
    whyTitle2: "store of value",
    whyLead:
      "Precious metals have historically played a role in wealth preservation, diversification, and protection against currency weakness.",
    p1:
      "Gold and other precious metals are often used by investors as long-term stores of value, especially during periods of inflation, uncertainty, or monetary instability.",
    p2:
      "AuroRatio is built for independent traders who want focused analysis and a repeatable process rather than another generic trading feed.",
    p3:
      "The service emphasizes disciplined signal generation, transparent timestamps, human approval, and manual execution through AuroRatio’s partner broker.",
    truthLabel: "Service philosophy",
    truth:
      "The objective is not constant activity. The objective is to publish clear, risk-aware signals only when the strategy’s conditions are met.",

    metric1: "3",
    metric1Label: "Relative-value strategies",
    metric1Sub: "Gold/silver, gold/platinum, and gold/palladium relationships.",
    metric2: "UTC",
    metric2Label: "Timestamped signals",
    metric2Sub: "Signal-generation and source-data times are clearly identified.",
    metric3: "You",
    metric3Label: "Control execution",
    metric3Sub: "Every trade decision and order remains with the subscriber.",

    tableTitle1: "Built around",
    tableTitle2: "signal discipline",
    tableLead:
      "The service separates market analysis, publication, delivery, and execution.",
    tableHead1: "Area",
    tableHead2: "AuroRatio role",
    tableHead3: "Subscriber role",
    row1a: "Market data",
    row1b: "Validate freshness and strategy inputs",
    row1c: "Review the signal context",
    row2a: "Signal generation",
    row2b: "Apply the structured strategy",
    row2c: "Decide whether the idea fits",
    row3a: "Publication",
    row3b: "Human approval before launch alerts",
    row3c: "Receive the private-channel alert",
    row4a: "Risk context",
    row4b: "Include levels when applicable",
    row4c: "Choose sizing and risk",
    row5a: "Execution",
    row5b: "No automatic customer trades",
    row5c: "Place orders with the partner broker",

    crown: "Professional signals with clear boundaries and independent execution",

    brokersLabel: "Product roadmap",
    brokersTitle1: "Broker connectivity",
    brokersTitle2: "is Coming Soon",
    brokersLead:
      "The launch product does not connect to brokerage accounts. Subscribers execute manually; broker connectivity remains a future capability until it is available.",
    soon: "Coming Soon",
    partnerBroker: "Approved partner broker",
    partnerBrokerDesc:
      "Your subscription includes ongoing technical support and assistance opening an account with our partner broker.",

    processLabel: "Publication framework",
    processTitle1: "A clear path from",
    processTitle2: "analysis to the private channel",
    processLead:
      "Signal candidates move from generated or draft status to pending approval, then approved and published—or rejected when they do not meet requirements.",
    boxLabel: "Protected strategy layer",
    boxText:
      "The service explains its methodology and signal format without publishing proprietary thresholds. Subscriber messages remain separate from broker execution.",

  },
  fr: {
    how: "Fonctionnement",
    features: "Avantages",
    platform: "Méthodologie",
    performance: "Recherche historique",
    pricing: "Tarifs",
    faq: "FAQ",
    contact: "Contact",

    heroLabel: "La méthodologie",
    heroTitle1: "Une analyse disciplinée",
    heroTitle2: "pour une exécution indépendante",
    heroSub:
      "AuroRatio étudie les relations de valeur relative entre métaux précieux, applique un processus structuré et diffuse les signaux approuvés dans un canal privé réservé aux membres.",

    whyLabel: "Pourquoi les métaux précieux",
    whyTitle1: "Une réserve de valeur",
    whyTitle2: "sur le long terme",
    whyLead:
      "Les métaux précieux ont historiquement joué un rôle dans la préservation du patrimoine, la diversification et la protection contre l’affaiblissement des devises.",
    p1:
      "L’or et les autres métaux précieux sont souvent utilisés par les investisseurs comme réserves de valeur long terme, notamment en période d’inflation, d’incertitude ou d’instabilité monétaire.",
    p2:
      "AuroRatio s’adresse aux traders autonomes qui recherchent une analyse ciblée et un processus répétable plutôt qu’un flux de trading générique.",
    p3:
      "Le service met l’accent sur la génération disciplinée des signaux, les horodatages transparents, la validation humaine et l’exécution manuelle auprès du courtier partenaire d’AuroRatio.",
    truthLabel: "Philosophie du service",
    truth:
      "L’objectif n’est pas l’activité permanente. L’objectif est de publier des signaux clairs et attentifs au risque uniquement lorsque les conditions de la stratégie sont réunies.",

    metric1: "3",
    metric1Label: "Stratégies de valeur relative",
    metric1Sub: "Relations or/argent, or/platine et or/palladium.",
    metric2: "UTC",
    metric2Label: "Signaux horodatés",
    metric2Sub: "Les heures du signal et des données sources sont identifiées.",
    metric3: "Vous",
    metric3Label: "Contrôlez l’exécution",
    metric3Sub: "Chaque décision et chaque ordre restent entre les mains de l’abonné.",

    tableTitle1: "Conçu autour",
    tableTitle2: "de la discipline des signaux",
    tableLead:
      "Le service sépare analyse de marché, publication, diffusion et exécution.",
    tableHead1: "Domaine",
    tableHead2: "Rôle d’AuroRatio",
    tableHead3: "Rôle de l’abonné",
    row1a: "Données de marché",
    row1b: "Valider fraîcheur et entrées",
    row1c: "Examiner le contexte",
    row2a: "Génération du signal",
    row2b: "Appliquer la stratégie structurée",
    row2c: "Décider si l’idée convient",
    row3a: "Publication",
    row3b: "Validation humaine au lancement",
    row3c: "Recevoir l’alerte dans le canal privé",
    row4a: "Contexte de risque",
    row4b: "Inclure des niveaux si applicable",
    row4c: "Choisir taille et risque",
    row5a: "Exécution",
    row5b: "Aucun trade client automatique",
    row5c: "Passer les ordres chez le courtier partenaire",

    crown: "Des signaux professionnels aux limites claires et une exécution indépendante",

    brokersLabel: "Feuille de route",
    brokersTitle1: "La connectivité courtier",
    brokersTitle2: "arrive bientôt",
    brokersLead:
      "Le produit de lancement ne se connecte pas aux comptes de courtage. Les abonnés exécutent manuellement ; la connectivité courtier reste une capacité future jusqu’à sa disponibilité.",
    soon: "Bientôt",
    partnerBroker: "Courtier partenaire agréé",
    partnerBrokerDesc:
      "Votre abonnement comprend un support technique permanent et un accompagnement à l’ouverture de votre compte auprès de notre courtier partenaire.",

    processLabel: "Cadre de publication",
    processTitle1: "Un chemin clair de",
    processTitle2: "l’analyse au canal privé",
    processLead:
      "Les signaux passent du statut généré ou brouillon à la validation, puis sont approuvés et publiés — ou rejetés s’ils ne respectent pas les exigences.",
    boxLabel: "Couche stratégique protégée",
    boxText:
      "Le service explique sa méthodologie et le format des signaux sans publier ses seuils propriétaires. Les messages abonnés restent séparés de l’exécution courtier.",

  },
} satisfies Record<PublicLanguage, Record<string, string>>;


export default function Platform({ marketData, marketDataAvailable }: PlatformProps) {

  const { language } = usePublicLanguage();
  const text = copy[language];

  const { beginCheckout, checkoutError, checkoutLoading } = usePublicCheckout(language, {
    error:
      language === "fr"
        ? "Impossible d’ouvrir le paiement sécurisé. Veuillez réessayer ou contacter le support."
        : "We couldn’t open secure checkout. Please try again or contact support.",
  });

  useEffect(() => {
    const els = document.querySelectorAll(".reveal");
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e, i) => {
          if (e.isIntersecting) {
            setTimeout(() => e.target.classList.add("in"), i * 80);
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.1 }
    );

    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div className="platform-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

        .platform-page {
          --gold: #C9A84C;
          --gold-light: #E8C97A;
          --gold-dark: #8B6914;
          --ink: #0A0A08;
          --ink-2: #111109;
          --ink-3: #1A1A14;
          --ink-4: #242418;
          --text: #E8E4D8;
          --text-muted: #8A8670;
          --rule: rgba(201,168,76,.18);
          --r: 4px;
          --border: rgba(201,168,76,.18);
          --surface2: #111109;

          background: var(--ink);
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          font-weight: 300;
          overflow-x: hidden;
          line-height: 1.75;
        }

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        .platform-page::before {
          content: '';
          position: fixed; inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.04'/%3E%3C/svg%3E");
          pointer-events: none; z-index: 0; opacity: .5;
        }

        .site-nav {
          position: sticky;
          top: 0px;
          z-index: 100;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 40px;
          height: 64px;
          background: rgba(10,10,8,.78);
          backdrop-filter: blur(18px);
          -webkit-backdrop-filter: blur(18px);
          border-bottom: 1px solid var(--rule);
        }

        .nav-logo {
          display: inline-block;
          font-family: 'Cormorant Garamond', serif;
          font-size: 22px;
          font-weight: 500;
          color: var(--gold);
          letter-spacing: 0.12em;
          text-transform: uppercase;
          text-decoration: none;
          cursor: pointer;
          white-space: nowrap;
        }

        .nav-logo span { color: var(--text); }

        .nav-links {
          display: flex;
          align-items: center;
          gap: .35rem;
          list-style: none;
        }

        .nav-links a {
          position: relative;
          border: 1px solid transparent;
          background: transparent;
          color: var(--text-muted);
          border-radius: 999px;
          padding: .55rem .85rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .72rem;
          font-weight: 400;
          letter-spacing: .11em;
          text-transform: uppercase;
          text-decoration: none;
          cursor: pointer;
          transition: color .2s, border-color .2s, background .2s;
          white-space: nowrap;
        }

        .nav-links a:hover {
          color: var(--text);
          border-color: rgba(201,168,76,.18);
          background: rgba(201,168,76,.04);
        }

        .nav-links a.active {
          color: var(--text);
          border-color: rgba(201,168,76,.28);
          background: rgba(201,168,76,.08);
        }

        .nav-logo:focus-visible,
        .nav-links a:focus-visible,
        .language-option:focus-visible {
          outline: 2px solid var(--gold-light);
          outline-offset: 3px;
        }

        .nav-cta {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .language-toggle {
          display: inline-flex;
          align-items: center;
          gap: .2rem;
          border: 1px solid var(--rule);
          border-radius: 999px;
          background: rgba(255,255,255,.018);
          padding: .2rem;
        }

        .language-option {
          border: 0;
          background: transparent;
          color: var(--text-muted);
          border-radius: 999px;
          padding: .42rem .58rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .68rem;
          letter-spacing: .08em;
          text-transform: uppercase;
          cursor: pointer;
          transition: color .2s, background .2s;
        }

        .language-option:hover { color: var(--text); }

        .language-option.active {
          background: rgba(201,168,76,.12);
          color: var(--gold);
        }

        .btn-ghost {
          font-size: 13px;
          color: var(--text-muted);
          text-decoration: none;
          letter-spacing: 0.04em;
          transition: color 0.2s;
          background: none;
          border: none;
          cursor: pointer;
        }

        .btn-ghost:hover { color: var(--text); }

        .btn-primary {
          font-family: 'DM Sans', sans-serif;
          font-size: 12px;
          font-weight: 500;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: var(--ink);
          background: var(--gold);
          border: none;
          padding: 10px 22px;
          border-radius: var(--r);
          cursor: pointer;
          text-decoration: none;
          transition: background 0.2s, transform 0.15s;
        }

        .btn-primary:hover { background: var(--gold-light); transform: translateY(-1px); }

        .hero {
          position: relative; min-height: 100vh;
          display: flex; align-items: center; justify-content: center;
          text-align: center; padding: 5rem 2rem;
          overflow: hidden;
        }

        .hero-bg {
          position: absolute; inset: 0;
          background:
            radial-gradient(ellipse 80% 60% at 50% 40%, rgba(201,168,76,.08) 0%, transparent 70%),
            radial-gradient(ellipse 40% 30% at 20% 80%, rgba(139,105,20,.06) 0%, transparent 60%);
        }

        .hero-line {
          position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
          width: 600px; height: 600px; border-radius: 50%;
          border: 1px solid rgba(201,168,76,.06);
          animation: pulse 8s ease-in-out infinite;
        }

        .hero-line:nth-child(2) { width: 800px; height: 800px; animation-delay: 2s; }
        .hero-line:nth-child(3) { width: 1000px; height: 1000px; animation-delay: 4s; }

        @keyframes pulse {
          0%,100% { opacity: .4; transform: translate(-50%,-50%) scale(1); }
          50% { opacity: .1; transform: translate(-50%,-50%) scale(1.02); }
        }

        .hero-content { position: relative; z-index: 1; max-width: 860px; }

        .hero-eyebrow {
          font-family: 'Syncopate', sans-serif;
          font-size: .65rem;
          letter-spacing: .15em;
          text-transform: uppercase;
          color: var(--gold);
          margin-bottom: 1.5rem;
          animation: fadeUp .8s ease both;
          font-weight: 700;
        }

        .hero h1 {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(3rem, 7vw, 6.5rem);
          font-weight: 300; line-height: 1.05;
          color: var(--text);
          animation: fadeUp .8s .15s ease both;
        }

        .hero h1 em { font-style: italic; color: var(--gold-light); }

        .hero-sub {
          margin-top: 1.8rem;
          font-size: 1.05rem; color: var(--text-muted); max-width: 620px; margin-inline: auto;
          animation: fadeUp .8s .3s ease both;
        }

        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(24px); }
          to { opacity: 1; transform: translateY(0); }
        }

        section { position: relative; z-index: 1; }

        .container { max-width: 1200px; margin: 0 auto; padding: 0 3rem; }

        .section-label {
          font-family: 'Syncopate', sans-serif;
          font-size: .6rem;
          letter-spacing: .15em;
          text-transform: uppercase;
          color: var(--gold);
          margin-bottom: 1.2rem;
          display: flex;
          align-items: center;
          gap: 1rem;
          font-weight: 700;
        }

        .section-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(36px, 4vw, 52px);
          font-weight: 300;
          line-height: 1.1;
          color: var(--text);
        }

        .section-title em { font-style: italic; color: var(--gold); }

        .lead {
          font-size: 1.08rem; color: var(--text-muted);
          max-width: 640px; margin-top: 1.2rem; line-height: 1.85;
        }

        #analysis {
          padding: 7rem 0;
          background: linear-gradient(180deg, var(--ink) 0%, var(--ink-2) 100%);
        }

        .analysis-grid {
          display: grid; grid-template-columns: 1fr 1fr; gap: 5rem;
          align-items: start; margin-top: 4rem;
        }

        .analysis-text p { 
          color: var(--text-muted); margin-bottom: 1.4rem; 
          font-size: 1rem; line-height: 1.85; 
        }

        .analysis-text strong { color: var(--text); font-weight: 500; }

        .highlight-box {
          background: linear-gradient(135deg, rgba(201,168,76,.1) 0%, rgba(139,105,20,.05) 100%);
          border: 1px solid rgba(201,168,76,.25);
          border-radius: 2px;
          padding: 2rem 2.2rem;
          margin-top: 2rem;
        }

        .highlight-box .hl-label {
          font-family: 'Syncopate', sans-serif;
          font-size: .58rem;
          letter-spacing: .15em;
          text-transform: uppercase;
          color: var(--gold);
          margin-bottom: 1rem;
          font-weight: 700;
        }

        .highlight-box p {
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.35rem; font-style: italic; font-weight: 300;
          color: var(--gold-light); line-height: 1.6; margin: 0 !important;
        }

        .metrics-stack { display: flex; flex-direction: column; gap: 1.5rem; }

        .metric-card {
          background: var(--ink-3);
          border: 1px solid var(--rule);
          border-left: 3px solid var(--gold);
          padding: 1.6rem 1.8rem;
          position: relative; overflow: hidden;
        }

        .metric-card::before {
          content: ''; position: absolute; top: 0; right: 0;
          width: 80px; height: 80px;
          background: radial-gradient(circle, rgba(201,168,76,.06) 0%, transparent 70%);
        }

        .metric-card .mc-num {
          font-family: 'Cormorant Garamond', serif;
          font-size: 2.4rem; font-weight: 600; color: var(--gold-light);
          line-height: 1; display: block;
        }

        .metric-card .mc-label {
          font-size: .75rem; letter-spacing: .08em;
          color: var(--text-muted); margin-top: .4rem;
        }

        .metric-card .mc-sub {
          font-size: .8rem; color: var(--text-muted);
          margin-top: .6rem; line-height: 1.5;
        }

        .devaluation-section { margin-top: 5rem; }

        .deval-table {
          width: 100%; border-collapse: collapse; margin-top: 2rem;
        }

        .deval-table th {
          font-family: 'Syncopate', sans-serif;
          font-size: .58rem; letter-spacing: .15em; text-transform: uppercase;
          color: var(--gold); padding: 1rem 1.2rem;
          border-bottom: 1px solid var(--rule);
          text-align: left; font-weight: 700;
        }

        .deval-table td {
          padding: 1rem 1.2rem; border-bottom: 1px solid rgba(201,168,76,.06);
          font-size: .9rem; color: var(--text-muted);
        }

        .deval-table tr:hover td { background: rgba(201,168,76,.03); color: var(--text); }

        .deval-table .asset { font-weight: 500; color: var(--text); }

        .crown-badge {
          display: inline-flex; align-items: center; gap: .5rem;
          background: linear-gradient(135deg, rgba(201,168,76,.2), rgba(201,168,76,.05));
          border: 1px solid rgba(201,168,76,.4);
          padding: 1.8rem 2.5rem; margin-top: 3rem;
          text-align: center; width: 100%;
          justify-content: center;
        }

        .crown-badge .crown-text {
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.5rem; font-style: italic; color: var(--gold-light);
        }

        #brokers {
          padding: 7rem 0;
          background: var(--ink-2);
        }

        .broker-grid {
          display: grid;
          grid-template-columns: minmax(0, 720px);
          gap: 2rem;
          margin-top: 4rem;
        }

        .broker-card {
          background: var(--ink-3);
          border: 1px solid var(--rule);
          padding: 2rem;
          border-radius: 4px;
          position: relative;
        }

        .broker-card .broker-name {
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.5rem;
          font-weight: 500;
          color: var(--text);
          margin-bottom: .6rem;
        }

        .broker-card .broker-status {
          display: inline-block;
          font-size: .7rem;
          letter-spacing: .12em;
          text-transform: uppercase;
          padding: .3rem .8rem;
          border-radius: 12px;
          margin-bottom: 1rem;
        }

        .broker-card .broker-status.live {
          background: rgba(102,187,106,.15);
          color: #66BB6A;
        }

        .broker-card .broker-status.soon {
          background: rgba(201,168,76,.15);
          color: var(--gold);
        }

        .broker-card .broker-desc {
          font-size: .9rem;
          color: var(--text-muted);
          line-height: 1.6;
        }

        .process-section {
          padding: 7rem 0;
          background: var(--ink-2);
        }

        .reveal {
          opacity: 0;
          transform: translateY(24px);
          transition: opacity 0.7s ease, transform 0.7s ease;
        }

        .reveal.in {
          opacity: 1;
          transform: translateY(0);
        }
        @media (max-width: 968px) {
          .analysis-grid { grid-template-columns: 1fr; }
          .broker-grid { grid-template-columns: 1fr; }
        }

        @media (max-width: 760px) {
          .site-nav {
            height: auto;
            padding: 16px 20px;
            flex-wrap: wrap;
            gap: 16px;
          }

          .nav-links {
            order: 3;
            width: 100%;
            overflow-x: auto;
            padding-bottom: 4px;
          }

          .nav-cta {
            margin-left: auto;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after {
            animation: none !important;
            transition: none !important;
          }

          .hero-eyebrow,
          .hero h1,
          .hero-sub,
          .reveal {
            animation: none !important;
            opacity: 1 !important;
            transform: none !important;
          }

          .hero-line {
            animation: none !important;
            opacity: .25 !important;
            transform: translate(-50%, -50%) !important;
          }
        }
      `}</style>

      {marketDataAvailable && <Ticker marketData={marketData} />}

      <PublicHeader
        onSubscribe={beginCheckout}
        checkoutLoading={checkoutLoading}
        activePage="platform"
      />

      <PublicCheckoutError message={checkoutError} />

      <section className="hero">
        <div className="hero-bg">
          <div className="hero-line"></div>
          <div className="hero-line"></div>
          <div className="hero-line"></div>
        </div>
        <div className="hero-content">
          <div className="hero-eyebrow">{text.heroLabel}</div>
          <h1>
            {text.heroTitle1}
            <br />
            <em>{text.heroTitle2}</em>
          </h1>
          <p className="hero-sub">{text.heroSub}</p>
        </div>
      </section>

      <section id="analysis">
        <div className="container">
          <div className="reveal">
            <p className="section-label">{text.whyLabel}</p>
            <h2 className="section-title">
              {text.whyTitle1}
              <br />
              <em>{text.whyTitle2}</em>
            </h2>
            <p className="lead">{text.whyLead}</p>
          </div>

          <div className="analysis-grid reveal">
            <div className="analysis-text">
              <p>
                <strong>{text.p1}</strong>
              </p>
              <p>{text.p2}</p>
              <p>{text.p3}</p>

              <div className="highlight-box">
                <div className="hl-label">{text.truthLabel}</div>
                <p>{text.truth}</p>
              </div>
            </div>

            <div className="metrics-stack">
              <div className="metric-card">
                <span className="mc-num">{text.metric1}</span>
                <div className="mc-label">{text.metric1Label}</div>
                <div className="mc-sub">{text.metric1Sub}</div>
              </div>
              <div className="metric-card">
                <span className="mc-num">{text.metric2}</span>
                <div className="mc-label">{text.metric2Label}</div>
                <div className="mc-sub">{text.metric2Sub}</div>
              </div>
              <div className="metric-card">
                <span className="mc-num">{text.metric3}</span>
                <div className="mc-label">{text.metric3Label}</div>
                <div className="mc-sub">{text.metric3Sub}</div>
              </div>
            </div>
          </div>

          <div className="devaluation-section reveal">
            <h2 className="section-title">
              {text.tableTitle1}
              <br />
              <em>{text.tableTitle2}</em>
            </h2>
            <p className="lead" style={{ marginTop: "1.2rem" }}>
              {text.tableLead}
            </p>

            <table className="deval-table">
              <thead>
                <tr>
                  <th>{text.tableHead1}</th>
                  <th>{text.tableHead2}</th>
                  <th>{text.tableHead3}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="asset">{text.row1a}</td>
                  <td>{text.row1b}</td>
                  <td>{text.row1c}</td>
                </tr>
                <tr>
                  <td className="asset">{text.row2a}</td>
                  <td>{text.row2b}</td>
                  <td>{text.row2c}</td>
                </tr>
                <tr>
                  <td className="asset">{text.row3a}</td>
                  <td>{text.row3b}</td>
                  <td>{text.row3c}</td>
                </tr>
                <tr>
                  <td className="asset">{text.row4a}</td>
                  <td>{text.row4b}</td>
                  <td>{text.row4c}</td>
                </tr>
                <tr>
                  <td className="asset">{text.row5a}</td>
                  <td>{text.row5b}</td>
                  <td>{text.row5c}</td>
                </tr>
              </tbody>
            </table>

            <div className="crown-badge">
              <span className="crown-text">{text.crown}</span>
            </div>
          </div>
        </div>
      </section>

      <section id="brokers">
          <div className="container">
            <div className="reveal">
              <p className="section-label">{text.brokersLabel}</p>
              <h2 className="section-title">
                {text.brokersTitle1}
                <br />
                <em>{text.brokersTitle2}</em>
              </h2>
              <p className="lead">{text.brokersLead}</p>
            </div>

            <div className="broker-grid reveal">
              <div className="broker-card">
                <div className="broker-name">{text.partnerBroker}</div>
                <span className="broker-status soon">{text.soon}</span>
                <p className="broker-desc">{text.partnerBrokerDesc}</p>
              </div>
            </div>
          </div>
      </section>

      <section className="process-section">
        <div className="container">
          <div className="reveal">
            <p className="section-label">{text.processLabel}</p>
            <h2 className="section-title">
              {text.processTitle1}
              <br />
              <em>{text.processTitle2}</em>
            </h2>
            <p className="lead">{text.processLead}</p>
          </div>

          <div className="reveal" style={{ marginTop: "4rem" }}>
            <div className="highlight-box">
              <div className="hl-label">{text.boxLabel}</div>
              <p>{text.boxText}</p>
            </div>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
