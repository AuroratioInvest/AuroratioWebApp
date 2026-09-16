import { useEffect } from "react";
import Ticker from "../components/Ticker";
import type { MarketData, BacktestData } from "../types/market";
import {
  PortfolioGrowthChart,
} from "../components/charts/BacktestCharts";
import PublicFooter from "../components/PublicFooter";
import PublicHeader from "../components/PublicHeader";
import PublicCheckoutError from "../components/PublicCheckoutError";
import { usePublicCheckout } from "../hooks/usePublicCheckout";
import { usePublicLanguage, type PublicLanguage } from "../context/PublicLanguageContext";

interface PerformanceProps {
  marketData: MarketData;
  backtestData: BacktestData;
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

    heroLabel: "Hypothetical backtest · methodology under review",
    heroTitle1: "Historical strategy",
    heroTitle2: "research",
    heroSub:
      "Hypothetical backtest from {start} to {end}, based on precious-metals spot data and the current research methodology. These are not subscriber results or actual trading performance.",

    summaryLabel: "Backtest summary",
    summaryTitle: "Key",
    summaryTitleEm: "Metrics",
    finalValue: "Hypothetical final value",
    initialCapital: "From CHF {amount}K hypothetical starting value",
    annualizedGrowth: "Backtested annualized growth",
    bestProfile: "Module 3 · historical simulation",
    exposureGrowth: "Simulated exposure growth",
    longTermExposure: "Hypothetical long-term exposure",

    chartLabel: "Wealth Accumulation",
    chartTitle: "Portfolio",
    chartTitleEm: "Growth",
    chartHeading: "Portfolio Value Growth",

    breakdownLabel: "Portfolio Breakdown",
    breakdownTitle: "Independent",
    breakdownTitleEm: "Modules",
    group1: "Gold ↔ Silver",
    group2: "Gold ↔ Platinum",
    group3: "Gold ↔ Palladium",
    group1Allocation: "Group / Sleeve 1 · 33% of portfolio",
    group2Allocation: "Group / Sleeve 2 · 33% of portfolio",
    group3Allocation: "Group / Sleeve 3 · 33% of portfolio",
    bestPerformer: "Module 3 - Best Historical Profile",
    finalValueMetric: "Final Value",
    cagr: "CAGR",
    multiplier: "Exposure Multiplier",
    reviewEvents: "Review Events",

    riskLabel: "Risk Analysis",
    riskTitle: "Drawdown",
    riskTitleEm: "Profile",
    drawdownHeading: "Maximum Drawdown Over Time",
    exposureHeading: "Long-Term Exposure Accumulation",

    activityLabel: "Activity History",
    activityTitle: "Major",
    activityTitleEm: "Portfolio Reviews",
    date: "Date",
    group: "Group",
    action: "Action",
    condition: "Condition",
    result: "Result",
    reviewed: "Reviewed",
    portfolioAction: "Portfolio review",
    allocationUpdated: "Allocation updated",
    allocationMaintained: "Allocation maintained",
    currentState: "Current portfolio state",
    historicalReview: "Historical review",
    completed: "Completed",
    current: "Current",

    disclaimer:
      "Research notice: these figures are hypothetical and backtested, not actual subscriber performance. The methodology and source data remain under review. The simulation uses spot-price data and does not include every real-world cost, execution condition, tax treatment, slippage, or market impact. Past performance does not guarantee future results. Legal wording is pending review.",
    allocationDisclaimer:
      "Backtest returns assume the portfolio is divided equally across the three independent sleeves shown above.",

  },
  fr: {
    how: "Fonctionnement",
    features: "Avantages",
    platform: "Méthodologie",
    performance: "Recherche historique",
    pricing: "Tarifs",
    faq: "FAQ",
    contact: "Contact",

    heroLabel: "Backtest hypothétique · méthodologie en cours de revue",
    heroTitle1: "Recherche historique",
    heroTitle2: "sur la stratégie",
    heroSub:
      "Backtest hypothétique de {start} à {end}, fondé sur les prix spot des métaux précieux et la méthodologie de recherche actuelle. Il ne s’agit ni de résultats abonnés ni de performances réelles.",

    summaryLabel: "Résumé du backtest",
    summaryTitle: "Indicateurs",
    summaryTitleEm: "clés",
    finalValue: "Valeur finale hypothétique",
    initialCapital: "Depuis CHF {amount}K de valeur initiale hypothétique",
    annualizedGrowth: "Croissance annualisée backtestée",
    bestProfile: "Module 3 · simulation historique",
    exposureGrowth: "Croissance simulée de l’exposition",
    longTermExposure: "Exposition long terme hypothétique",

    chartLabel: "Accumulation de patrimoine",
    chartTitle: "Croissance",
    chartTitleEm: "du portefeuille",
    chartHeading: "Croissance de la valeur du portefeuille",

    breakdownLabel: "Répartition du portefeuille",
    breakdownTitle: "Groupes d’allocation",
    breakdownTitleEm: "indépendants",
    group1: "Or ↔ Argent",
    group2: "Or ↔ Platine",
    group3: "Or ↔ Palladium",
    group1Allocation: "Groupe / Pot 1 · 33 % du portefeuille",
    group2Allocation: "Groupe / Pot 2 · 33 % du portefeuille",
    group3Allocation: "Groupe / Pot 3 · 33 % du portefeuille",
    bestPerformer: "Meilleur profil historique",
    finalValueMetric: "Valeur finale",
    cagr: "CAGR",
    multiplier: "Multiplicateur d’exposition",
    reviewEvents: "Événements de revue",

    riskLabel: "Analyse du risque",
    riskTitle: "Profil de",
    riskTitleEm: "drawdown",
    drawdownHeading: "Drawdown maximal dans le temps",
    exposureHeading: "Accumulation d’exposition long terme",

    activityLabel: "Historique d’activité",
    activityTitle: "Revues majeures",
    activityTitleEm: "du portefeuille",
    date: "Date",
    group: "Groupe",
    action: "Action",
    condition: "Condition",
    result: "Résultat",
    reviewed: "Revu",
    portfolioAction: "Revue du portefeuille",
    allocationUpdated: "Allocation mise à jour",
    allocationMaintained: "Allocation maintenue",
    currentState: "État actuel du portefeuille",
    historicalReview: "Revue historique",
    completed: "Terminé",
    current: "Actuel",

    disclaimer:
      "Note de recherche : ces chiffres sont hypothétiques et issus d’un backtest, et non de performances réelles d’abonnés. La méthodologie et les données sources restent en cours de revue. La simulation utilise des prix spot et n’intègre pas tous les coûts, conditions d’exécution, traitements fiscaux, slippage ou impacts de marché. Les performances passées ne garantissent pas les résultats futurs. La formulation juridique est en attente de revue.",
    allocationDisclaimer:
      "Les rendements du backtest supposent une allocation du portefeuille à parts égales entre les trois pots indépendants présentés ci-dessus.",

  },
} satisfies Record<PublicLanguage, Record<string, string>>;


export default function Performance({
  marketData,
  backtestData,
  marketDataAvailable,
}: PerformanceProps) {

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

  const heroSub = text.heroSub
    .replace("{start}", backtestData.timeframe.start)
    .replace("{end}", backtestData.timeframe.end);

  const initialCapital = text.initialCapital.replace(
    "{amount}",
    (backtestData.initialValueCHF / 1000).toFixed(0)
  );
  const timeframeYears = Math.max(
    1,
    Number(backtestData.timeframe.end) - Number(backtestData.timeframe.start)
  );
  const portfolioCagr =
    (Math.pow(backtestData.finalValueCHF / backtestData.initialValueCHF, 1 / timeframeYears) - 1) * 100;
  const portfolioMultiplier = backtestData.finalValueCHF / backtestData.initialValueCHF;

  return (
    <div className="performance-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

        .performance-page {
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

        .performance-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
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

        section { position: relative; z-index: 1; padding: 80px 40px; }

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

        .summary-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 24px;
          margin-top: 40px;
        }

        .summary-card {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 8px;
          padding: 32px 28px;
          text-align: center;
        }

        .summary-card .sc-label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          color: var(--text-muted);
          margin-bottom: 12px;
        }

        .summary-card .sc-value {
          font-family: 'Cormorant Garamond', serif;
          font-size: 42px;
          font-weight: 500;
          color: var(--gold);
          margin-bottom: 8px;
        }

        .summary-card .sc-sub {
          font-size: 13px;
          color: var(--text-muted);
        }

        .module-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 2rem;
          margin-top: 4rem;
        }

        .module-card {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 8px;
          padding: 36px;
        }

        .module-card.featured {
          border-color: var(--gold);
          background: rgba(200,168,75,0.03);
        }

        .module-card .mod-name {
          font-family: 'Cormorant Garamond', serif;
          font-size: 24px;
          font-weight: 500;
          color: var(--text);
          margin-bottom: 8px;
        }

        .mod-allocation {
          color: var(--gold);
          font-size: 10px;
          font-weight: 600;
          letter-spacing: .1em;
          text-transform: uppercase;
          margin-bottom: 8px;
        }

        .module-card .mod-badge {
          display: inline-block;
          font-size: 9px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: #5A9E72;
          background: rgba(90,158,114,0.12);
          padding: 4px 10px;
          border-radius: 10px;
          margin-bottom: 20px;
        }

        .module-card .mod-metrics {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .module-card .mod-metric {
          display: flex;
          justify-content: space-between;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--rule);
        }

        .module-card .mod-metric:last-child {
          border-bottom: none;
        }

        .module-card .mod-metric-label {
          font-size: 12px;
          color: var(--text-muted);
        }

        .module-card .mod-metric-value {
          font-family: 'Cormorant Garamond', serif;
          font-size: 20px;
          font-weight: 500;
          color: var(--text);
        }

        .chart-section {
          background: var(--ink-2);
        }

        .chart-box {
          background: var(--surface2);
          border: 1px solid var(--rule);
          border-radius: 8px;
          padding: 32px;
          margin-top: 40px;
        }

        .chart-box h3 {
          font-family: 'Cormorant Garamond', serif;
          font-size: 24px;
          font-weight: 500;
          color: var(--text);
          margin-bottom: 24px;
        }

        .disclaimer {
          background: var(--ink-2);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 24px 32px;
          margin-top: 60px;
          text-align: center;
        }

        .allocation-disclaimer {
          color: var(--gold-light);
          font-size: 13px;
          margin: 22px 0 12px;
        }

        .disclaimer p {
          font-size: 12px;
          color: var(--text-muted);
          line-height: 1.7;
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
          .summary-grid, .module-grid { grid-template-columns: 1fr; }
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

          section {
            padding: 60px 20px;
          }

          .container {
            padding: 0;
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
        activePage="performance"
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
            {text.heroTitle1} <em>{text.heroTitle2}</em>
          </h1>
          <p className="hero-sub">{heroSub}</p>
        </div>
      </section>

      <section>
        <div className="container">
          <div className="reveal">
            <p className="section-label">{text.summaryLabel}</p>
            <h2 className="section-title">
              {text.summaryTitle} <em>{text.summaryTitleEm}</em>
            </h2>
          </div>

          <div className="summary-grid reveal">
            <div className="summary-card">
              <div className="sc-label">{text.finalValue}</div>
              <div className="sc-value">
                CHF {(backtestData.finalValueCHF / 1000000).toFixed(1)}M
              </div>
              <div className="sc-sub">{initialCapital}</div>
            </div>

            <div className="summary-card">
              <div className="sc-label">{text.annualizedGrowth}</div>
              <div className="sc-value">
                {portfolioCagr.toFixed(2)}%
              </div>
              <div className="sc-sub">{text.bestProfile}</div>
            </div>

            <div className="summary-card">
              <div className="sc-label">{text.exposureGrowth}</div>
              <div className="sc-value">
                {portfolioMultiplier.toFixed(2)}×
              </div>
              <div className="sc-sub">{text.longTermExposure}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="chart-section">
        <div className="container">
          <div className="reveal">
            <p className="section-label">{text.chartLabel}</p>
            <h2 className="section-title">
              {text.chartTitle} <em>{text.chartTitleEm}</em>
            </h2>
          </div>

          <div className="chart-box reveal">
            <h3>{text.chartHeading}</h3>
            <PortfolioGrowthChart backtestData={backtestData} />
          </div>
        </div>
      </section>

      <section>
        <div className="container">
          <div className="reveal">
            <p className="section-label">{text.breakdownLabel}</p>
            <h2 className="section-title">
              {text.breakdownTitle} <em>{text.breakdownTitleEm}</em>
            </h2>
          </div>

          <div className="module-grid reveal">
            <div className="module-card">
              <div className="mod-allocation">{text.group1Allocation}</div>
              <div className="mod-name">{text.group1}</div>
              <div
                className="mod-badge"
                style={{ color: "var(--text-muted)", background: "rgba(122,120,112,0.12)" }}
              >
                Module 1
              </div>

              <div className="mod-metrics">
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.finalValueMetric}</span>
                  <span className="mod-metric-value">
                    CHF {(backtestData.modules.goldSilver.finalValue / 1000000).toFixed(1)}M
                  </span>
                </div>
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.cagr}</span>
                  <span className="mod-metric-value">
                    {backtestData.modules.goldSilver.cagr.toFixed(2)}%
                  </span>
                </div>
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.multiplier}</span>
                  <span className="mod-metric-value">
                    {backtestData.modules.goldSilver.ounceMultiplier.toFixed(2)}×
                  </span>
                </div>
              </div>
            </div>

            <div className="module-card">
              <div className="mod-allocation">{text.group2Allocation}</div>
              <div className="mod-name">{text.group2}</div>
              <div
                className="mod-badge"
                style={{ color: "var(--text-muted)", background: "rgba(122,120,112,0.12)" }}
              >
                Module 2
              </div>

              <div className="mod-metrics">
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.finalValueMetric}</span>
                  <span className="mod-metric-value">
                    CHF {(backtestData.modules.goldPlatinum.finalValue / 1000000).toFixed(1)}M
                  </span>
                </div>
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.cagr}</span>
                  <span className="mod-metric-value">
                    {backtestData.modules.goldPlatinum.cagr.toFixed(2)}%
                  </span>
                </div>
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.multiplier}</span>
                  <span className="mod-metric-value">
                    {backtestData.modules.goldPlatinum.ounceMultiplier.toFixed(2)}×
                  </span>
                </div>
              </div>
            </div>

            <div className="module-card featured">
              <div className="mod-allocation">{text.group3Allocation}</div>
              <div className="mod-name">{text.group3}</div>
              <div className="mod-badge">{text.bestPerformer}</div>

              <div className="mod-metrics">
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.finalValueMetric}</span>
                  <span className="mod-metric-value">
                    CHF {(backtestData.modules.goldPalladium.finalValue / 1000000).toFixed(1)}M
                  </span>
                </div>
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.cagr}</span>
                  <span className="mod-metric-value">
                    {backtestData.modules.goldPalladium.cagr.toFixed(2)}%
                  </span>
                </div>
                <div className="mod-metric">
                  <span className="mod-metric-label">{text.multiplier}</span>
                  <span className="mod-metric-value">
                    {backtestData.modules.goldPalladium.ounceMultiplier.toFixed(2)}×
                  </span>
                </div>
              </div>
            </div>
          </div>

          <p className="allocation-disclaimer reveal">* {text.allocationDisclaimer}</p>

            <div className="disclaimer reveal">
                <p>
                    <strong>{text.disclaimer.split(":")[0]}:</strong>
                    {text.disclaimer.includes(":") ? text.disclaimer.substring(text.disclaimer.indexOf(":") + 1) : ""}
                </p>
            </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
