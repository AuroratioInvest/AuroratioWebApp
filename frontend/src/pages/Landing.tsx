import { useEffect, useState } from "react";
import Ticker from "../components/Ticker";
import MetalsStrip from "../components/MetalsStrip";
import PublicFooter from "../components/PublicFooter";
import PublicHeader from "../components/PublicHeader";
import PublicCheckoutError from "../components/PublicCheckoutError";
import type { MarketData } from "../types/market";
import { usePublicCheckout } from "../hooks/usePublicCheckout";
import { usePublicLanguage, type PublicLanguage } from "../context/PublicLanguageContext";

interface LandingProps {
  marketData: MarketData;
  marketDataAvailable: boolean;
}

const copy = {
  en: {
    how: "How it works",
    features: "Benefits",
    pricing: "Pricing",
    faq: "FAQ",
    contact: "Contact",
    subscribe: "Subscribe",
    checkoutLoading: "Opening secure checkout…",
    checkoutError:
      "We couldn’t open secure checkout. Please try again or contact support.",
    checkoutSupport: "Contact support",
    learnMore: "Learn More",

    heroEyebrow: "Professional signals · Private members channel",
    heroTitle1: "Precious-metals signals.",
    heroTitle2: "Your decisions. Your broker.",
    heroSubtitle: "A disciplined signal service for independent traders",
    heroBody:
      "AuroRatio analyzes relative-value opportunities across precious metals and delivers structured trading signals to a private members channel. You review every alert and execute manually through our approved broker.",
    heroTrust: "Private-channel delivery",
    heroControl: "You keep full control of execution",

    featuresLabel: "What subscribers receive",
    featuresTitle1: "Clear signals.",
    featuresTitle2: "Disciplined decisions.",
    featuresSub:
      "Focused market analysis designed to help independent traders act with more structure—without handing over control of their capital.",
    feature1Title: "Structured trading signals",
    feature1Desc:
      "Each approved alert communicates the instrument, direction, timing context, and risk parameters when applicable.",
    feature2Title: "Private-channel delivery",
    feature2Desc:
      "Receive timely signals in one members-only channel, without another customer dashboard or password.",
    feature3Title: "Risk-aware framework",
    feature3Desc:
      "Signals are developed within a rules-based process that considers invalidation levels, targets, and market conditions.",
    feature4Title: "Precious-metals analysis",
    feature4Desc:
      "The methodology focuses on relative-value relationships across gold, silver, platinum, and palladium.",
    feature5Title: "Timely, human-approved alerts",
    feature5Desc:
      "The initial publication workflow includes administrator review before a signal reaches the private channel.",
    feature6Title: "Full execution control",
    feature6Desc:
      "You decide whether, when, and how to trade through AuroRatio’s partner broker. AuroRatio never takes custody of your funds.",

    howLabel: "How it works",
    howTitle1: "From subscription",
    howTitle2: "to your own execution",
    howSub:
      "No account password, broker connection, or managed portfolio is required.",
    step1Title: "Choose the plan",
    step1Desc:
      "Select the single recurring AuroRatio signal subscription.",
    step2Title: "Pay securely with Stripe",
    step2Desc:
      "Complete payment in Stripe’s hosted Checkout.",
    step3Title: "Receive your invitation",
    step3Desc:
      "After server-side payment confirmation, your private channel invitation is emailed to you.",
    step4Title: "Join the members-only channel",
    step4Desc:
      "Use the one-member invitation to access the subscriber-only broadcast channel.",
    step5Title: "Receive signals",
    step5Desc:
      "Follow structured alerts and the accompanying risk context as they are published.",
    step6Title: "Trade manually",
    step6Desc:
      "Evaluate each signal and place any trade yourself with AuroRatio’s partner broker.",

    previewTitle: "auroratio · private signal channel",
    previewStatus: "Human approved",
    previewInstrument: "GOLD / SILVER",
    previewDirection: "Relative-value opportunity",
    previewEntry: "Entry condition",
    previewRisk: "Risk level",
    previewTargets: "Targets",
    previewTime: "UTC timestamp",
    previewBody:
      "Signal details appear here after approval, with the market condition and source-data timestamp clearly identified.",
    previewDefined: "Defined when applicable",
    previewLevels: "Structured levels",
    previewExecution: "Execution",
    previewManual: "Manual · partner broker",
    previewDisclaimer: "Illustrative format only · Customer-facing wording is under review",

    roadmapLabel: "Broker partner",
    roadmapTitle: "Partner-broker connectivity is coming soon",
    roadmapSub:
      "Subscribers will receive permanent technical support and assistance opening an account with our partner broker. Until the integration launches, all execution remains manual.",
    roadmapBroker: "Broker integrations",
    roadmapAutomation: "Optional automation",
    roadmapExecution: "Advanced execution",
    roadmapChannels: "Additional delivery channels",
    comingSoon: "Coming Soon",

    methodologyLabel: "Transparent methodology",
    methodologyTitle1: "A focused framework",
    methodologyTitle2: "with clear boundaries",
    methodologySub:
      "AuroRatio separates signal generation, human approval, message delivery, and your independent execution.",
    method1Value: "3",
    method1Label: "Precious-metal ratios",
    method1Desc: "Gold/silver, gold/platinum, and gold/palladium relationships.",
    method2Value: "UTC",
    method2Label: "Timestamped analysis",
    method2Desc: "Signal and source-data times are recorded consistently.",
    method3Value: "You",
    method3Label: "Control execution",
    method3Desc: "No custody, connected brokerage account, or automatic trade placement.",

    pricingLabel: "Pricing",
    pricingTitle: "Simple, transparent pricing",
    pricingSub: "One recurring plan for the private AuroRatio signal channel.",
    planName: "AuroRatio Signals",
    planDesc: "Professional precious-metals signals delivered through a private members channel",
    planTrial: "Monthly subscription · Access continues through the paid period",
    planFeature1: "Private members channel access",
    planFeature2: "Structured precious-metals trading signals",
    planFeature3: "Entry, risk, and target context when applicable",
    planFeature4: "Human-approved publication workflow",
    planFeature5: "English and French service experience",
    planFeature6: "Transactional email support",
    checkoutNote:
      "You’ll continue to Stripe’s secure Checkout. Access follows verified payment; no AuroRatio account is required.",

    faqLabel: "Frequently asked questions",
    faqTitle1: "Know exactly",
    faqTitle2: "what you are subscribing to",
    faqBrokerQ: "Do I need a brokerage account?",
    faqBrokerA:
      "Yes. AuroRatio provides signals only. You need your own account with AuroRatio’s partner broker if you decide to execute a signal.",
    faqTradeQ: "Does AuroRatio trade for me?",
    faqTradeA:
      "No. You remain responsible for evaluating and manually executing every trade. AuroRatio does not control or hold customer capital.",
    faqDeliveryQ: "How are signals delivered?",
    faqDeliveryA:
      "After verified payment, subscribers receive an emailed, single-use invitation to the private members channel.",
    faqAnyBrokerQ: "Can I use any broker?",
    faqAnyBrokerA:
      "No. You must use AuroRatio’s partner broker. Subscribers receive permanent technical support and assistance opening their account. Execution remains manual until broker connectivity is available.",
    faqPaymentQ: "What happens after payment?",
    faqPaymentA:
      "The backend verifies payment through Stripe before an invitation is generated. Access is never provisioned solely from a browser success page.",
    faqCancelQ: "Can I cancel my subscription?",
    faqCancelA:
      "Cancellation is intended to take effect at the end of the paid billing period. Final cancellation and refund terms remain subject to the published legal policies.",
    faqAutomationQ: "Will more automation be available later?",
    faqAutomationA:
      "Broker integrations, optional automation, and advanced execution are planned capabilities and are marked Coming Soon. They are not included in the launch service.",

    ctaLabel: "Trade with your own judgment",
    ctaTitle1: "Professional signals.",
    ctaTitle2: "Control stays with you.",
    ctaSub:
      "Choose the monthly plan and continue to secure Checkout. You remain in control of every trading decision.",

  },
  fr: {
    how: "Fonctionnement",
    features: "Avantages",
    pricing: "Tarifs",
    faq: "FAQ",
    contact: "Contact",
    subscribe: "S’abonner",
    checkoutLoading: "Ouverture du Checkout sécurisé…",
    checkoutError:
      "Impossible d’ouvrir le Checkout sécurisé. Réessayez ou contactez le support.",
    checkoutSupport: "Contacter le support",
    learnMore: "En savoir plus",

    heroEyebrow: "Signaux professionnels · Canal privé réservé aux membres",
    heroTitle1: "Signaux sur métaux précieux.",
    heroTitle2: "Vos décisions. Votre courtier.",
    heroSubtitle: "Un service de signaux discipliné pour les traders autonomes",
    heroBody:
      "AuroRatio analyse les opportunités de valeur relative entre métaux précieux et transmet des signaux structurés dans un canal privé réservé aux membres. Vous examinez chaque alerte et exécutez manuellement auprès de notre courtier agréé.",
    heroTrust: "Diffusion dans un canal privé",
    heroControl: "Vous gardez le contrôle total de l’exécution",

    featuresLabel: "Ce que reçoivent les abonnés",
    featuresTitle1: "Des signaux clairs.",
    featuresTitle2: "Des décisions disciplinées.",
    featuresSub:
      "Une analyse de marché ciblée pour aider les traders autonomes à agir avec plus de structure, sans céder le contrôle de leur capital.",
    feature1Title: "Signaux structurés",
    feature1Desc:
      "Chaque alerte approuvée présente l’instrument, la direction, le contexte temporel et les paramètres de risque lorsqu’ils s’appliquent.",
    feature2Title: "Diffusion dans un canal privé",
    feature2Desc:
      "Recevez les signaux dans un canal réservé aux membres, sans tableau de bord client ni mot de passe supplémentaire.",
    feature3Title: "Cadre attentif au risque",
    feature3Desc:
      "Les signaux suivent un processus fondé sur des règles, avec niveaux d’invalidation, objectifs et contexte de marché.",
    feature4Title: "Analyse des métaux précieux",
    feature4Desc:
      "La méthodologie étudie les relations de valeur relative entre l’or, l’argent, le platine et le palladium.",
    feature5Title: "Alertes validées humainement",
    feature5Desc:
      "Au lancement, un administrateur vérifie chaque signal avant sa publication dans le canal privé.",
    feature6Title: "Contrôle total de l’exécution",
    feature6Desc:
      "Vous décidez si, quand et comment trader auprès du courtier partenaire d’AuroRatio. AuroRatio ne détient jamais vos fonds.",

    howLabel: "Fonctionnement",
    howTitle1: "De l’abonnement",
    howTitle2: "à votre propre exécution",
    howSub:
      "Aucun mot de passe client, aucune connexion courtier et aucune gestion de portefeuille ne sont nécessaires.",
    step1Title: "Choisissez l’offre",
    step1Desc:
      "Sélectionnez l’unique abonnement récurrent aux signaux AuroRatio.",
    step2Title: "Payez avec Stripe",
    step2Desc:
      "Effectuez le paiement sur le Checkout hébergé par Stripe.",
    step3Title: "Recevez votre invitation",
    step3Desc:
      "Après confirmation serveur du paiement, votre invitation au canal privé vous est envoyée par email.",
    step4Title: "Rejoignez le canal privé",
    step4Desc:
      "Utilisez l’invitation à usage unique pour accéder au canal réservé aux abonnés.",
    step5Title: "Recevez les signaux",
    step5Desc:
      "Consultez les alertes structurées et leur contexte de risque dès leur publication.",
    step6Title: "Tradez manuellement",
    step6Desc:
      "Évaluez chaque signal et passez vous-même vos ordres auprès du courtier partenaire d’AuroRatio.",

    previewTitle: "auroratio · canal privé de signaux",
    previewStatus: "Validation humaine",
    previewInstrument: "OR / ARGENT",
    previewDirection: "Opportunité de valeur relative",
    previewEntry: "Condition d’entrée",
    previewRisk: "Niveau de risque",
    previewTargets: "Objectifs",
    previewTime: "Horodatage UTC",
    previewBody:
      "Les détails du signal apparaissent ici après validation, avec la condition de marché et l’horodatage des données sources.",
    previewDefined: "Défini si applicable",
    previewLevels: "Niveaux structurés",
    previewExecution: "Exécution",
    previewManual: "Manuelle · courtier partenaire",
    previewDisclaimer: "Format illustratif · Formulation client en cours de revue",

    roadmapLabel: "Courtier partenaire",
    roadmapTitle: "La connectivité avec notre courtier partenaire arrive bientôt",
    roadmapSub:
      "Les abonnés bénéficieront d’un support technique permanent et d’un accompagnement à l’ouverture de leur compte auprès de notre courtier partenaire. D’ici au lancement de l’intégration, toute exécution reste manuelle.",
    roadmapBroker: "Intégrations courtiers",
    roadmapAutomation: "Automatisation optionnelle",
    roadmapExecution: "Exécution avancée",
    roadmapChannels: "Autres canaux de diffusion",
    comingSoon: "Bientôt",

    methodologyLabel: "Méthodologie transparente",
    methodologyTitle1: "Un cadre ciblé",
    methodologyTitle2: "aux limites claires",
    methodologySub:
      "AuroRatio sépare génération du signal, validation humaine, diffusion du message et exécution indépendante.",
    method1Value: "3",
    method1Label: "Ratios de métaux précieux",
    method1Desc: "Relations or/argent, or/platine et or/palladium.",
    method2Value: "UTC",
    method2Label: "Analyse horodatée",
    method2Desc: "Les heures du signal et des données sources sont enregistrées.",
    method3Value: "Vous",
    method3Label: "Contrôlez l’exécution",
    method3Desc: "Aucune conservation de fonds, connexion courtier ou exécution automatique.",

    pricingLabel: "Tarifs",
    pricingTitle: "Une tarification simple et transparente",
    pricingSub: "Une offre récurrente pour accéder au canal privé de signaux AuroRatio.",
    planName: "AuroRatio Signals",
    planDesc: "Des signaux professionnels sur métaux précieux diffusés dans un canal privé réservé aux membres",
    planTrial: "Abonnement mensuel · Accès maintenu jusqu’à la fin de la période payée",
    planFeature1: "Accès au canal privé réservé aux membres",
    planFeature2: "Signaux structurés sur métaux précieux",
    planFeature3: "Contexte d’entrée, de risque et d’objectifs si applicable",
    planFeature4: "Publication validée humainement",
    planFeature5: "Expérience en anglais et en français",
    planFeature6: "Support transactionnel par email",
    checkoutNote:
      "Vous allez poursuivre vers le Checkout Stripe sécurisé. L’accès suit la confirmation du paiement ; aucun compte AuroRatio n’est requis.",

    faqLabel: "Questions fréquentes",
    faqTitle1: "Sachez exactement",
    faqTitle2: "à quoi vous vous abonnez",
    faqBrokerQ: "Ai-je besoin d’un compte de courtage ?",
    faqBrokerA:
      "Oui. AuroRatio fournit uniquement des signaux. Vous avez besoin de votre propre compte auprès du courtier partenaire d’AuroRatio si vous décidez d’exécuter un signal.",
    faqTradeQ: "AuroRatio trade-t-il pour moi ?",
    faqTradeA:
      "Non. Vous restez responsable de l’évaluation et de l’exécution manuelle de chaque trade. AuroRatio ne contrôle ni ne détient le capital des clients.",
    faqDeliveryQ: "Comment les signaux sont-ils diffusés ?",
    faqDeliveryA:
      "Après vérification du paiement, l’abonné reçoit par email une invitation à usage unique pour le canal privé réservé aux membres.",
    faqAnyBrokerQ: "Puis-je utiliser n’importe quel courtier ?",
    faqAnyBrokerA:
      "Non. Vous devez utiliser le courtier partenaire d’AuroRatio. Les abonnés bénéficient d’un support technique permanent et d’un accompagnement à l’ouverture de leur compte. L’exécution reste manuelle jusqu’à la disponibilité de la connectivité courtier.",
    faqPaymentQ: "Que se passe-t-il après le paiement ?",
    faqPaymentA:
      "Le backend vérifie le paiement auprès de Stripe avant de générer une invitation. L’accès n’est jamais accordé uniquement depuis une page de succès du navigateur.",
    faqCancelQ: "Puis-je annuler mon abonnement ?",
    faqCancelA:
      "L’annulation est prévue pour prendre effet à la fin de la période payée. Les conditions finales d’annulation et de remboursement restent soumises aux politiques juridiques publiées.",
    faqAutomationQ: "Davantage d’automatisation sera-t-elle proposée ?",
    faqAutomationA:
      "Les intégrations courtiers, l’automatisation optionnelle et l’exécution avancée sont prévues et indiquées comme « Bientôt ». Elles ne font pas partie du service de lancement.",

    ctaLabel: "Tradez avec votre propre jugement",
    ctaTitle1: "Des signaux professionnels.",
    ctaTitle2: "Vous gardez le contrôle.",
    ctaSub:
      "Choisissez l’offre mensuelle et poursuivez vers le Checkout sécurisé. Vous gardez le contrôle de chaque décision de trading.",

  },
} satisfies Record<PublicLanguage, Record<string, string>>;

const strategyBenefits = {
  en: [
    {
      title: "Protection & an enduring store of value",
      points: [
        ["Protection against devaluation", "Physical gold and precious metals are a safe-haven asset designed to protect capital against the loss of purchasing power caused by inflation and monetary creation."],
        ["Financial sovereignty", "Back your wealth with tangible, universal assets that are independent of traditional banking risks and sovereign collateral."],
      ],
    },
    {
      title: "Exceptional liquidity & agility",
      points: [
        ["Withdraw funds within 48 to 72 hours", "Keep complete freedom: your holdings remain rapidly available with no platform exit fee; only the partner broker’s standard execution fees apply."],
        ["A strong return / availability balance", "An approach for personal liquidity or business treasury that seeks higher returns than savings accounts without locking up your money."],
      ],
    },
    {
      title: "Business & holding-company treasury optimization",
      points: [
        ["Put operating surplus to work", "Allocate operating surplus and company or trust reserves to resilient assets."],
        ["Professional wealth-transfer tool", "A turnkey strategy for accumulating and transferring professional cash flow without destabilizing operations."],
      ],
    },
    {
      title: "Long-term wealth & retirement",
      points: [
        ["Long-term compounding engine", "Prepare for retirement by combining the stability of precious metals with the outperformance sought through algorithmic rebalancing."],
        ["Tax transparency", "A clear legal framework subject to the ordinary securities-account taxation of your country of residence."],
      ],
    },
    {
      title: "Estate & succession planning",
      points: [
        ["Succession optimization", "Securities may be transferred in specie to heirs without selling positions, potentially resetting accumulated capital-gains tax depending on local law."],
        ["Flexibility on death", "Heirs may choose between retaining the physical-metal securities or liquidating them entirely for cash."],
      ],
    },
  ],
  fr: [
    {
      title: "Protection & Réserve de Valeur Inaltérable",
      points: [
        ["Protection contre la dévaluation", "L’or physique et les métaux précieux constituent la valeur refuge par excellence pour immuniser votre capital contre la perte de pouvoir d’achat des monnaies systémiques (inflation, création monétaire)."],
        ["Souveraineté financière", "Vous adossez votre patrimoine à des actifs tangibles, universels et indépendants des risques bancaires traditionnels et des collatéraux étatiques."],
      ],
    },
    {
      title: "Liquidité & Agilité Exceptionnelles",
      points: [
        ["Retrait de vos fonds sous 48h à 72h", "Conservez une liberté totale. Vos avoirs restent disponibles rapidement et sans frais de sortie de la plateforme (seuls les frais d’exécution standards du courtier partenaire s’appliquent)."],
        ["Le meilleur couple Rendement / Disponibilité", "Un arbitrage optimal pour vos liquidités personnelles ou la trésorerie de votre entreprise, offrant un rendement supérieur aux comptes sur livret sans bloquer votre argent."],
      ],
    },
    {
      title: "Optimisation de la Trésorerie d’Entreprise & Holding",
      points: [
        ["Capitalisation de l’EBE", "Faites travailler l’Excédent Brut d’Exploitation et les réserves de vos sociétés ou Trusts dans des actifs résilients."],
        ["Outil de transmission pro", "Une stratégie clé en main pour accumuler et transmettre le cash-flow professionnel sans déstabiliser l’exploitation."],
      ],
    },
    {
      title: "Vision Patrimoniale & Retraite",
      points: [
        ["Moteur de capitalisation long terme", "Préparez sereinement votre retraite en combinant la stabilité des métaux précieux et la surperformance des arbitrages algorithmiques."],
        ["Transparence fiscale totale", "Un cadre juridique clair soumis à la fiscalité classique du Compte Titres Ordinaire (CTO) de votre pays de résidence."],
      ],
    },
    {
      title: "Transmission & Successions Privilégiées",
      points: [
        ["Optimisation successorale", "Possibilité de transférer les titres « In Specie » aux héritiers sans vendre les positions, permettant la purge totale de l’impôt sur les plus-values accumulées (selon les législations locales, ex : France)."],
        ["Flexibilité au décès", "Choix sur-mesure pour vos héritiers entre la conservation des titres physiques ou la liquidation intégrale en cash."],
      ],
    },
  ],
} satisfies Record<PublicLanguage, ReadonlyArray<{ title: string; points: ReadonlyArray<readonly [string, string]> }>>;


export default function Landing({
  marketData,
  marketDataAvailable,
}: LandingProps) {
  const [activeStep, setActiveStep] = useState(0);
  const [activeSection, setActiveSection] = useState<"how" | "features" | "why-auroratio" | "pricing" | "faq" | null>(null);
  const { language } = usePublicLanguage();

  const text = copy[language];
  const {
    beginCheckout,
    checkoutError,
    checkoutLoading,
  } = usePublicCheckout(language, { error: text.checkoutError });

  useEffect(() => {
    const sectionIds = ["how", "features", "why-auroratio", "pricing", "faq"] as const;
    const sections = sectionIds
      .map((id) => document.getElementById(id))
      .filter((section): section is HTMLElement => section !== null);

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) {
          setActiveSection(visible.target.id as typeof sectionIds[number]);
        }
      },
      { rootMargin: "-20% 0px -60% 0px", threshold: [0, 0.1, 0.35] }
    );

    sections.forEach((section) => observer.observe(section));
    const clearAtTop = () => { if (window.scrollY < 160) setActiveSection(null); };
    window.addEventListener("scroll", clearAtTop, { passive: true });
    clearAtTop();

    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", clearAtTop);
    };
  }, []);

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
    <div className="auroratio-landing">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500&display=swap');

        .auroratio-landing,
        .auroratio-landing *,
        .auroratio-landing *::before,
        .auroratio-landing *::after {
          box-sizing: border-box; margin: 0; padding: 0; 
        }

        .auroratio-landing {
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
          --border: rgba(201,168,76,.18);
          --surface2: #111109;
          --surface3: #242418;
          --r: 4px;
          --r-lg: 10px;

          font-family: 'DM Sans', sans-serif;
          background: var(--ink);
          color: var(--text);
          line-height: 1.75;
          overflow-x: hidden;
          -webkit-font-smoothing: antialiased;
        }

        html { scroll-behavior: smooth; }

        .auroratio-landing::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
          pointer-events: none;
          z-index: 0;
          opacity: 0.4;
        }

        .auroratio-landing > nav {
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
          font-family: 'Cormorant Garamond', serif;
          font-size: 22px;
          font-weight: 500;
          color: var(--gold);
          letter-spacing: 0.12em;
          text-transform: uppercase;
          cursor: pointer;
          white-space: nowrap;
          border: 0;
          background: transparent;
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

        .language-option:hover {
          color: var(--text);
        }

        .language-option.active {
          background: rgba(201,168,76,.12);
          color: var(--gold);
        }

        button:focus-visible,
        a:focus-visible,
        summary:focus-visible {
          outline: 2px solid var(--gold-light);
          outline-offset: 3px;
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
          position: relative;
          min-height: 90vh;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          padding: 80px 40px 100px;
          overflow: hidden;
        }

        .hero-glow {
          position: absolute;
          width: 700px;
          height: 700px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(200,168,75,0.07) 0%, transparent 65%);
          top: 50%;
          left: 50%;
          transform: translate(-50%, -55%);
          pointer-events: none;
        }

        .hero-grid {
          position: absolute;
          inset: 0;
          background-image:
            linear-gradient(rgba(200,168,75,0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(200,168,75,0.04) 1px, transparent 1px);
          background-size: 60px 60px;
          mask-image: radial-gradient(ellipse 70% 70% at 50% 50%, black 30%, transparent 100%);
          pointer-events: none;
        }

        .hero-eyebrow {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          letter-spacing: 0.2em;
          text-transform: uppercase;
          color: var(--gold);
          border: 1px solid var(--border);
          padding: 6px 16px;
          border-radius: 20px;
          margin-bottom: 28px;
          background: rgba(200,168,75,0.05);
          position: relative;
          z-index: 2;
        }

        .hero-eyebrow::before {
          content: '';
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--gold);
          animation: pulse 2s ease infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.8); }
        }

        .hero-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(52px, 7vw, 88px);
          font-weight: 300;
          line-height: 1.05;
          letter-spacing: -0.01em;
          color: var(--text);
          margin-bottom: 12px;
          position: relative;
          z-index: 2;
        }

        .hero-title em { font-style: italic; color: var(--gold); }

        .hero-subtitle-main {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(24px, 3vw, 36px);
          font-weight: 300;
          font-style: italic;
          color: var(--gold-light);
          margin-bottom: 24px;
          position: relative;
          z-index: 2;
        }

        .hero-sub {
          font-size: 17px;
          font-weight: 300;
          color: var(--text-muted);
          max-width: 640px;
          margin: 0 auto 44px;
          position: relative;
          z-index: 2;
          line-height: 1.7;
        }

        .hero-actions {
          display: flex;
          gap: 16px;
          align-items: center;
          justify-content: center;
          position: relative;
          z-index: 2;
          flex-wrap: wrap;
        }

        .btn-primary-lg {
          font-family: 'DM Sans', sans-serif;
          font-size: 13px;
          font-weight: 500;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          color: var(--ink);
          background: var(--gold);
          border: none;
          padding: 14px 32px;
          border-radius: var(--r);
          cursor: pointer;
          text-decoration: none;
          transition: background 0.2s, transform 0.15s, box-shadow 0.2s;
        }

        .btn-primary-lg:hover {
          background: var(--gold-light);
          transform: translateY(-2px);
          box-shadow: 0 8px 32px rgba(200,168,75,0.25);
        }

        .btn-outline-lg {
          font-family: 'DM Sans', sans-serif;
          font-size: 13px;
          font-weight: 400;
          letter-spacing: 0.06em;
          color: var(--text);
          border: 1px solid var(--border);
          padding: 14px 32px;
          border-radius: var(--r);
          cursor: pointer;
          text-decoration: none;
          transition: border-color 0.2s, background 0.2s;
          background: transparent;
        }

        .btn-outline-lg:hover { border-color: var(--gold); background: rgba(200,168,75,0.05); }

        .hero-trust {
          margin-top: 56px;
          font-size: 12px;
          color: var(--text-muted);
          letter-spacing: 0.08em;
          text-transform: uppercase;
          position: relative;
          z-index: 2;
        }

        .hero-trust span { color: var(--gold); }

        .auroratio-landing > section {
          position: relative;
          z-index: 1;
        }

        .container { max-width: 1100px; margin: 0 auto; padding: 0 40px; }

        .section-pad { padding: 100px 0; }

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

        .section-sub {
          font-size: 16px;
          font-weight: 300;
          color: var(--text-muted);
          max-width: 520px;
          margin-top: 16px;
          line-height: 1.7;
        }

        .features-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1px;
          background: var(--rule);
          border: 1px solid var(--rule);
          border-radius: var(--r-lg);
          overflow: hidden;
          margin-top: 60px;
        }

        .feature-cell {
          background: var(--ink-2);
          padding: 36px 32px;
          transition: background 0.2s;
        }

        .feature-cell:hover { background: var(--ink-3); }

        .feature-icon {
          width: 40px;
          height: 40px;
          border: 1px solid var(--border);
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 20px;
          background: rgba(200,168,75,0.06);
        }

        .feature-icon svg { 
          width: 18px; 
          height: 18px; 
          stroke: var(--gold); 
          fill: none; 
          stroke-width: 1.5; 
          stroke-linecap: round; 
          stroke-linejoin: round; 
        }

        .feature-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 20px;
          font-weight: 500;
          color: var(--text);
          margin-bottom: 10px;
        }

        .feature-desc {
          font-size: 14px;
          font-weight: 300;
          color: var(--text-muted);
          line-height: 1.7;
        }

        .how-layout {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 80px;
          align-items: center;
          margin-top: 60px;
        }

        .steps { display: flex; flex-direction: column; gap: 0; }

        .step {
          width: 100%;
          display: flex;
          text-align: left;
          gap: 20px;
          padding: 28px 0;
          border-bottom: 1px solid var(--rule);
          border-left: 0;
          border-right: 0;
          border-top: 0;
          background: transparent;
          color: inherit;
          font: inherit;
          cursor: pointer;
          transition: all 0.2s;
        }

        .step:first-child { border-top: 1px solid var(--rule); }

        .step.active .step-num { border-color: var(--gold); color: var(--gold); }

        .step.active .step-title { color: var(--text); }

        .step-num {
          width: 32px;
          height: 32px;
          border: 1px solid var(--border);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          color: var(--text-muted);
          flex-shrink: 0;
          transition: all 0.2s;
        }

        .step-content { flex: 1; }

        .step-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 18px;
          font-weight: 500;
          color: var(--text-muted);
          margin-bottom: 6px;
          transition: color 0.2s;
        }

        .step-desc {
          font-size: 14px;
          font-weight: 300;
          color: var(--text-muted);
          line-height: 1.6;
        }

        .dashboard-preview {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: var(--r-lg);
          overflow: hidden;
        }

        .dash-header {
          padding: 14px 20px;
          border-bottom: 1px solid var(--rule);
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .dash-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--surface3); }

        .dash-title {
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          letter-spacing: 0.1em;
          color: var(--text-muted);
          margin-left: auto;
        }

        .dash-body { padding: 28px; }

        .dash-stat-row {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 16px;
          margin-bottom: 24px;
        }

        .dash-stat {
          background: rgba(200,168,75,0.03);
          border: 1px solid var(--rule);
          border-radius: var(--r);
          padding: 16px;
        }

        .dash-stat-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          color: var(--text-muted);
          margin-bottom: 6px;
        }

        .dash-stat-val {
          font-family: 'Cormorant Garamond', serif;
          font-size: 24px;
          font-weight: 500;
          color: var(--text);
          margin-bottom: 4px;
        }

        .dash-stat-sub {
          font-size: 11px;
          color: #5A9E72;
        }

        .chart-area {
          background: rgba(200,168,75,0.02);
          border: 1px solid var(--rule);
          border-radius: var(--r);
          padding: 16px;
          margin-bottom: 20px;
        }

        .chart-label {
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          color: var(--text-muted);
          margin-bottom: 12px;
        }

        .signal-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .signal-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 14px 16px;
          background: rgba(200,168,75,0.02);
          border: 1px solid var(--rule);
          border-radius: var(--r);
          transition: background .2s, border-color .2s;
        }

        .signal-item:hover {
          background: rgba(200,168,75,0.045);
          border-color: rgba(201,168,76,.28);
        }
        
        .signal-metal {
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          letter-spacing: 0.08em;
          color: var(--text);
        }

        .signal-conf {
          font-family: 'DM Mono', monospace;
          font-size: 10px;
          color: var(--text-muted);
        }

        .broker-strip {
          background: var(--ink);
          border-top: 1px solid var(--rule);
          border-bottom: 1px solid var(--rule);
          padding: 60px 40px;
          text-align: center;
        }

        .broker-grid {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 48px;
          flex-wrap: wrap;
        }

        .broker-item {
          font-size: 16px;
          color: var(--text-muted);
          position: relative;
        }

        .broker-item.coming {
          opacity: 0.78;
          display: flex;
          align-items: center;
          gap: .75rem;
        }

        .coming-badge {
          font-size: 8px;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          color: var(--gold);
          background: rgba(200,168,75,0.1);
          border: 1px solid var(--rule);
          padding: 3px 7px;
          border-radius: 999px;
        }

        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 24px;
          margin-top: 60px;
        }

        .metric-cell {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: var(--r-lg);
          padding: 32px 24px;
          text-align: center;
          transition: all 0.3s;
        }

        .metric-cell:hover {
          border-color: var(--gold);
          transform: translateY(-4px);
        }

        .metric-val {
          font-family: 'Cormorant Garamond', serif;
          font-size: 42px;
          font-weight: 500;
          color: var(--gold);
          margin-bottom: 10px;
        }

        .strategy-benefits-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 18px;
          margin-top: 48px;
        }

        .strategy-benefit {
          display: flex;
          gap: 20px;
          border: 1px solid var(--rule);
          border-radius: var(--r-lg);
          background: var(--ink-2);
          padding: 26px;
        }

        .strategy-benefit:last-child {
          grid-column: 1 / -1;
        }

        .strategy-benefit-number {
          color: var(--gold);
          font: 600 11px 'Syncopate', sans-serif;
          letter-spacing: .12em;
        }

        .strategy-benefit h3 {
          color: var(--text);
          font: 500 23px/1.2 'Cormorant Garamond', serif;
          margin-bottom: 10px;
        }

        .strategy-benefit p {
          color: var(--text-muted);
          font-size: 14px;
          line-height: 1.75;
        }

        .strategy-benefit ul {
          display: grid;
          gap: 12px;
          margin: 0;
          padding-left: 18px;
          color: var(--text-muted);
          font-size: 14px;
          line-height: 1.65;
        }

        .strategy-benefit li::marker { color: var(--gold); }
        .strategy-benefit strong { color: var(--text); font-weight: 500; }

        .metric-val sup {
          font-size: 20px;
          margin-left: 2px;
        }

        .metric-label {
          font-size: 13px;
          line-height: 1.4;
          color: var(--text-muted);
        }

        .pricing-section {
          background: var(--ink-2);
        }

        .pricing-container {
          max-width: 500px;
          margin: 60px auto 0;
        }

        .price-card {
          background: var(--surface2);
          border: 2px solid var(--gold);
          border-radius: var(--r-lg);
          padding: 48px 40px;
          position: relative;
        }

        .plan-name {
          font-family: 'Cormorant Garamond', serif;
          font-size: 28px;
          font-weight: 500;
          color: var(--text);
          margin-bottom: 8px;
          text-align: center;
        }

        .plan-desc {
          font-size: 14px;
          color: var(--text-muted);
          margin-bottom: 32px;
          text-align: center;
        }

        .plan-price {
          font-family: 'Cormorant Garamond', serif;
          font-size: 56px;
          font-weight: 500;
          color: var(--text);
          margin-bottom: 8px;
          text-align: center;
        }

        .plan-price sup {
          font-size: 24px;
          vertical-align: super;
          margin-right: 2px;
        }

        .plan-price sub {
          font-size: 18px;
          color: var(--text-muted);
          font-weight: 400;
        }

        .plan-trial {
          text-align: center;
          font-size: 13px;
          color: var(--gold);
          margin-bottom: 32px;
        }

        .checkout-note {
          color: var(--text-muted);
          font-size: 12px;
          line-height: 1.6;
          margin-top: 16px;
          text-align: center;
        }

        .faq-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          align-items: start;
          gap: 14px;
          margin-top: 56px;
        }

        .faq-item {
          border: 1px solid var(--rule);
          border-radius: var(--r-lg);
          background: var(--ink-2);
          padding: 0 24px;
        }

        .faq-item summary {
          cursor: pointer;
          list-style: none;
          color: var(--text);
          font-family: 'Cormorant Garamond', serif;
          font-size: 20px;
          font-weight: 500;
          padding: 22px 34px 22px 0;
          position: relative;
        }

        .faq-item summary::-webkit-details-marker { display: none; }

        .faq-item summary::after {
          content: '+';
          position: absolute;
          right: 0;
          color: var(--gold);
          font-family: 'DM Sans', sans-serif;
          font-weight: 300;
        }

        .faq-item[open] summary::after { content: '–'; }

        .faq-item p {
          color: var(--text-muted);
          font-size: 14px;
          line-height: 1.75;
          padding: 0 0 22px;
        }

        .plan-sep {
          border: none;
          border-top: 1px solid var(--rule);
          margin: 32px 0;
        }

        .plan-features {
          list-style: none;
          margin-bottom: 36px;
        }

        .plan-features li {
          font-size: 14px;
          color: var(--text-muted);
          margin-bottom: 14px;
          padding-left: 24px;
          position: relative;
        }

        .plan-features li::before {
          content: '→';
          position: absolute;
          left: 0;
          color: var(--gold);
        }

        .cta-section {
          padding: 120px 40px;
          text-align: center;
          position: relative;
          overflow: hidden;
        }

        .cta-glow {
          position: absolute;
          width: 600px;
          height: 600px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(200,168,75,0.08) 0%, transparent 70%);
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          pointer-events: none;
        }

        .cta-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(42px, 6vw, 68px);
          font-weight: 300;
          line-height: 1.1;
          color: var(--text);
          margin-bottom: 20px;
          position: relative;
          z-index: 2;
        }

        .cta-title em {
          font-style: italic;
          color: var(--gold);
        }

        .cta-sub {
          font-size: 17px;
          color: var(--text-muted);
          margin-bottom: 40px;
          position: relative;
          z-index: 2;
        }

        .cta-form {
          display: flex;
          gap: 12px;
          max-width: 440px;
          margin: 0 auto;
          position: relative;
          z-index: 2;
          flex-wrap: wrap;
          justify-content: center;
        }

        .cta-input {
          font-family: 'DM Sans', sans-serif;
          font-size: 14px;
          color: var(--text);
          background: var(--ink);
          border: 1px solid var(--border);
          padding: 14px 20px;
          border-radius: var(--r);
          width: 280px;
          outline: none;
          transition: border-color 0.2s;
        }

        .cta-input:focus { border-color: var(--gold); }

        .cta-input::placeholder { color: var(--text-muted); }

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
          .features-grid { grid-template-columns: 1fr; }
          .how-layout { grid-template-columns: 1fr; gap: 40px; }
          .metrics-grid { grid-template-columns: repeat(2, 1fr); }
          .dash-stat-row { grid-template-columns: 1fr; }
          .faq-grid { grid-template-columns: 1fr; }
          .strategy-benefits-grid { grid-template-columns: 1fr; }
          .strategy-benefit:last-child { grid-column: auto; }
        }

        @media (max-width: 760px) {
          .auroratio-landing > nav {
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

        @media (max-width: 640px) {
          .hero { padding: 60px 20px 80px; }
          .section-pad { padding: 60px 0; }
          .container { padding: 0 20px; }
          .metrics-grid { grid-template-columns: 1fr; }
          .hero-actions, .cta-form { flex-direction: column; width: 100%; }
          .btn-primary-lg, .btn-outline-lg, .cta-input { width: 100%; }
        }

        @media (prefers-reduced-motion: reduce) {
          html { scroll-behavior: auto; }
          .auroratio-landing,
          .auroratio-landing *,
          .auroratio-landing *::before,
          .auroratio-landing *::after {
            animation: none !important;
            transition: none !important;
          }
          .reveal {
            opacity: 1 !important;
            transform: none !important;
          }
        }
      `}</style>

      {marketDataAvailable && <Ticker marketData={marketData} />}

      <PublicHeader
        onSubscribe={beginCheckout}
        checkoutLoading={checkoutLoading}
        activePage="home"
        activeSection={activeSection}
        onHomeReset={() => setActiveSection(null)}
      />

      <PublicCheckoutError message={checkoutError} />

      <section className="hero">
        <div className="hero-glow"></div>
        <div className="hero-grid"></div>

        <div className="hero-eyebrow">{text.heroEyebrow}</div>

        <h1 className="hero-title">
          {text.heroTitle1}
          <br />
          <em>{text.heroTitle2}</em>
        </h1>

        <p className="hero-subtitle-main">{text.heroSubtitle}</p>

        <p className="hero-sub">{text.heroBody}</p>

        <div className="hero-actions">
          <button
            type="button"
            onClick={beginCheckout}
            className="btn-primary-lg"
            disabled={checkoutLoading}
          >
            {checkoutLoading ? text.checkoutLoading : text.subscribe}
          </button>
          <a className="btn-outline-lg" href="#how">
            {text.learnMore}
          </a>
        </div>

        <p className="hero-trust">
          <span>{text.heroTrust}</span> · {text.heroControl}
        </p>
      </section>

      {marketDataAvailable && <MetalsStrip marketData={marketData} />}

      <section className="section-pad" id="features">
        <div className="container">
          <div className="reveal">
            <p className="section-label">{text.featuresLabel}</p>
            <h2 className="section-title">
              {text.featuresTitle1}
              <br />
              <em>{text.featuresTitle2}</em>
            </h2>
            <p className="section-sub">{text.featuresSub}</p>
          </div>

          <div className="features-grid reveal">
            <div className="feature-cell">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <div className="feature-title">{text.feature1Title}</div>
              <div className="feature-desc">{text.feature1Desc}</div>
            </div>

            <div className="feature-cell">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
              </div>
              <div className="feature-title">{text.feature2Title}</div>
              <div className="feature-desc">{text.feature2Desc}</div>
            </div>

            <div className="feature-cell">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" />
                  <polyline points="2 17 12 22 22 17" />
                  <polyline points="2 12 12 17 22 12" />
                </svg>
              </div>
              <div className="feature-title">{text.feature3Title}</div>
              <div className="feature-desc">{text.feature3Desc}</div>
            </div>

            <div className="feature-cell">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <line x1="3" y1="9" x2="21" y2="9" />
                  <line x1="9" y1="21" x2="9" y2="9" />
                </svg>
              </div>
              <div className="feature-title">{text.feature4Title}</div>
              <div className="feature-desc">{text.feature4Desc}</div>
            </div>

            <div className="feature-cell">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24">
                  <path d="M18 20V10" />
                  <path d="M12 20V4" />
                  <path d="M6 20v-6" />
                </svg>
              </div>
              <div className="feature-title">{text.feature5Title}</div>
              <div className="feature-desc">{text.feature5Desc}</div>
            </div>

            <div className="feature-cell">
              <div className="feature-icon">
                <svg viewBox="0 0 24 24">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
              </div>
              <div className="feature-title">{text.feature6Title}</div>
              <div className="feature-desc">{text.feature6Desc}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad" id="how" style={{ background: "var(--ink-2)" }}>
        <div className="container">
          <div className="how-layout">
            <div className="reveal">
              <p className="section-label">{text.howLabel}</p>
              <h2 className="section-title">
                {text.howTitle1}
                <br />
                <em>{text.howTitle2}</em>
              </h2>
              <p className="section-sub">{text.howSub}</p>

              <div className="steps" style={{ marginTop: "36px" }}>
                <button
                  type="button"
                  className={`step ${activeStep === 0 ? "active" : ""}`}
                  onClick={() => setActiveStep(0)}
                  aria-pressed={activeStep === 0}
                >
                  <div className="step-num">01</div>
                  <div className="step-content">
                    <div className="step-title">{text.step1Title}</div>
                    <div className="step-desc">{text.step1Desc}</div>
                  </div>
                </button>

                <button
                  type="button"
                  className={`step ${activeStep === 1 ? "active" : ""}`}
                  onClick={() => setActiveStep(1)}
                  aria-pressed={activeStep === 1}
                >
                  <div className="step-num">02</div>
                  <div className="step-content">
                    <div className="step-title">{text.step2Title}</div>
                    <div className="step-desc">{text.step2Desc}</div>
                  </div>
                </button>

                <button
                  type="button"
                  className={`step ${activeStep === 2 ? "active" : ""}`}
                  onClick={() => setActiveStep(2)}
                  aria-pressed={activeStep === 2}
                >
                  <div className="step-num">03</div>
                  <div className="step-content">
                    <div className="step-title">{text.step3Title}</div>
                    <div className="step-desc">{text.step3Desc}</div>
                  </div>
                </button>

                <button
                  type="button"
                  className={`step ${activeStep === 3 ? "active" : ""}`}
                  onClick={() => setActiveStep(3)}
                  aria-pressed={activeStep === 3}
                >
                  <div className="step-num">04</div>
                  <div className="step-content">
                    <div className="step-title">{text.step4Title}</div>
                    <div className="step-desc">{text.step4Desc}</div>
                  </div>
                </button>

                <button
                  type="button"
                  className={`step ${activeStep === 4 ? "active" : ""}`}
                  onClick={() => setActiveStep(4)}
                  aria-pressed={activeStep === 4}
                >
                  <div className="step-num">05</div>
                  <div className="step-content">
                    <div className="step-title">{text.step5Title}</div>
                    <div className="step-desc">{text.step5Desc}</div>
                  </div>
                </button>

                <button
                  type="button"
                  className={`step ${activeStep === 5 ? "active" : ""}`}
                  onClick={() => setActiveStep(5)}
                  aria-pressed={activeStep === 5}
                >
                  <div className="step-num">06</div>
                  <div className="step-content">
                    <div className="step-title">{text.step6Title}</div>
                    <div className="step-desc">{text.step6Desc}</div>
                  </div>
                </button>
              </div>
            </div>

            <div className="dashboard-preview reveal" aria-label={text.previewTitle}>
              <div className="dash-header">
                <div className="dash-dot"></div>
                <div className="dash-dot"></div>
                <div className="dash-dot"></div>
                <div className="dash-title">{text.previewTitle}</div>
              </div>

              <div className="dash-body">
                <div className="dash-stat-row">
                  {["AU / AG", "AU / PD", "AU / PT"].map((ratio) => (
                    <div className="dash-stat" key={ratio}>
                      <div className="dash-stat-label">{text.previewInstrument}</div>
                      <div className="dash-stat-val">{ratio}</div>
                      <div className="dash-stat-sub">33.33% · {text.previewDirection}</div>
                    </div>
                  ))}
                </div>

                <div className="chart-area">
                  <div className="chart-label">{text.previewEntry}</div>
                  <div style={{ color: "var(--text)", fontSize: "15px", lineHeight: 1.7 }}>
                    {text.previewBody}
                  </div>
                </div>

                <div className="signal-list">
                  <div className="signal-item">
                    <span className="signal-metal">{text.previewRisk}</span>
                    <span className="signal-conf">{text.previewDefined}</span>
                  </div>

                  <div className="signal-item">
                    <span className="signal-metal">{text.previewTargets}</span>
                    <span className="signal-conf">{text.previewLevels}</span>
                  </div>

                  <div className="signal-item">
                    <span className="signal-metal">{text.previewExecution}</span>
                    <span className="signal-conf">{text.previewManual}</span>
                  </div>
                </div>
                <p style={{ color: "var(--text-muted)", fontSize: "11px", marginTop: "18px" }}>
                  {text.previewDisclaimer}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad broker-strip" aria-labelledby="roadmap-title">
        <div className="container">
          <div className="section-label" style={{ justifyContent: "center" }}>
            {text.roadmapLabel}
          </div>
          <h2
            className="section-title"
            id="roadmap-title"
            style={{ maxWidth: "760px", margin: "0 auto 16px" }}
          >
            {text.roadmapTitle}
          </h2>
          <p className="section-sub" style={{ margin: "0 auto 40px" }}>
            {text.roadmapSub}
          </p>
          <div className="broker-grid">
            <div className="broker-item coming">
              <span>{language === "fr" ? "Courtier partenaire" : "Partner broker"}</span>
              <span className="coming-badge">{text.comingSoon}</span>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad" id="methodology">
        <div className="container">
          <div className="reveal" style={{ textAlign: "center" }}>
            <p className="section-label" style={{ justifyContent: "center" }}>
              {text.methodologyLabel}
            </p>
            <h2 className="section-title">
              {text.methodologyTitle1}
              <br />
              <em>{text.methodologyTitle2}</em>
            </h2>
            <p className="section-sub" style={{ margin: "16px auto 0" }}>
              {text.methodologySub}
            </p>
          </div>

          <div className="metrics-grid reveal">
            <div className="metric-cell">
              <div className="metric-val">{text.method1Value}</div>
              <div className="metric-label">{text.method1Label}</div>
              <p className="feature-desc" style={{ marginTop: "10px" }}>
                {text.method1Desc}
              </p>
            </div>

            <div className="metric-cell">
              <div className="metric-val">{text.method2Value}</div>
              <div className="metric-label">{text.method2Label}</div>
              <p className="feature-desc" style={{ marginTop: "10px" }}>
                {text.method2Desc}
              </p>
            </div>

            <div className="metric-cell">
              <div className="metric-val">{text.method3Value}</div>
              <div className="metric-label">{text.method3Label}</div>
              <p className="feature-desc" style={{ marginTop: "10px" }}>
                {text.method3Desc}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad" id="why-auroratio" aria-labelledby="strategy-benefits-title">
        <div className="container">
          <div className="reveal" style={{ textAlign: "center" }}>
            <p className="section-label" style={{ justifyContent: "center" }}>
              {language === "fr" ? "Pourquoi les métaux précieux" : "Why precious metals"}
            </p>
            <h2 className="section-title" id="strategy-benefits-title">
              {language === "fr" ? "Pourquoi choisir la stratégie " : "Why choose the "}
              <em>AuroRatio</em> ?
            </h2>
          </div>

          <div className="strategy-benefits-grid reveal">
            {strategyBenefits[language].map(({ title, points }, index) => (
              <article className="strategy-benefit" key={title}>
                <span className="strategy-benefit-number">0{index + 1}</span>
                <div>
                  <h3>{title}</h3>
                  <ul>
                    {points.map(([label, description]) => (
                      <li key={label}><strong>{label} :</strong> {description}</li>
                    ))}
                  </ul>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section-pad pricing-section" id="pricing">
        <div className="container">
          <div className="reveal" style={{ textAlign: "center" }}>
            <p className="section-label">{text.pricingLabel}</p>
            <h2 className="section-title">
              {text.pricingTitle.split(" ").slice(0, -1).join(" ")}{" "}
              <em>{text.pricingTitle.split(" ").slice(-1)}</em>
            </h2>
            <p className="section-sub" style={{ margin: "16px auto 0" }}>
              {text.pricingSub}
            </p>
          </div>

          <div className="pricing-container reveal">
            <div className="price-card">
              <div className="plan-name">{text.planName}</div>
              <div className="plan-desc">{text.planDesc}</div>
              <div className="plan-price">
                <sup>€</sup>14.99<sub>/{language === "fr" ? "mois" : "month"}</sub>
              </div>
              <div className="plan-trial">{text.planTrial}</div>
              <hr className="plan-sep" />

              <ul className="plan-features">
                <li>{text.planFeature1}</li>
                <li>{text.planFeature2}</li>
                <li>{text.planFeature3}</li>
                <li>{text.planFeature4}</li>
                <li>{text.planFeature5}</li>
                <li>{text.planFeature6}</li>
              </ul>

              <button
                type="button"
                onClick={beginCheckout}
                disabled={checkoutLoading}
                className="btn-primary-lg"
                data-testid="pricing-subscribe"
                style={{ display: "block", width: "100%", textAlign: "center" }}
              >
                {checkoutLoading ? text.checkoutLoading : text.subscribe}
              </button>
              <p className="checkout-note">{text.checkoutNote}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad" id="faq">
        <div className="container">
          <div className="reveal" style={{ textAlign: "center" }}>
            <p className="section-label" style={{ justifyContent: "center" }}>
              {text.faqLabel}
            </p>
            <h2 className="section-title">
              {text.faqTitle1}
              <br />
              <em>{text.faqTitle2}</em>
            </h2>
          </div>

          <div className="faq-grid reveal">
            {[
              [text.faqBrokerQ, text.faqBrokerA],
              [text.faqTradeQ, text.faqTradeA],
              [text.faqDeliveryQ, text.faqDeliveryA],
              [text.faqAnyBrokerQ, text.faqAnyBrokerA],
              [text.faqPaymentQ, text.faqPaymentA],
              [text.faqCancelQ, text.faqCancelA],
              [text.faqAutomationQ, text.faqAutomationA],
            ].map(([question, answer]) => (
              <details className="faq-item" key={question}>
                <summary>{question}</summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="cta-section section-pad">
        <div className="container">
          <div className="cta-glow"></div>
          <p className="section-label reveal" style={{ textAlign: "center", marginBottom: "16px" }}>
            {text.ctaLabel}
          </p>
          <h2 className="cta-title reveal">
            {text.ctaTitle1}
            <br />
            <em>{text.ctaTitle2}</em>
          </h2>
          <p className="cta-sub reveal">{text.ctaSub}</p>
          <div className="cta-form reveal">
            <button
              type="button"
              onClick={beginCheckout}
              className="btn-primary-lg"
              disabled={checkoutLoading}
            >
              {checkoutLoading ? text.checkoutLoading : text.subscribe}
            </button>
            <a href="/contact" className="btn-outline-lg">
              {text.contact}
            </a>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
