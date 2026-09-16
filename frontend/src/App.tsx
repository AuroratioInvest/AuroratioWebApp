import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import Landing from "./pages/Landing";
import Platform from "./pages/Platform";
import Performance from "./pages/Performance";
import Contact from "./pages/Contact";
import LegalPlaceholder from "./pages/LegalPlaceholder";
import ManageSubscription from "./pages/ManageSubscription";
import SubscriptionOutcome from "./pages/SubscriptionOutcome";
import {
  getPublicBacktestData,
  getPublicMarketData,
} from "./api/publicMarket";

import type { BacktestData, MarketData } from "./types/market";
import {
  EMPTY_MARKET_DATA,
  loadPublicResource,
} from "./data/publicData";
import { companyInformation } from "./config/companyInformation";
import { getScrollBehavior } from "./utils/motion";

type Language = "en" | "fr";

const messages = {
  en: {
    loading: "Loading...",
    performanceUnavailable: "Historical performance data is temporarily unavailable.",
    contactTitle: "Contact us",
    contactSubtitle: "Questions about signals, subscriptions, or private-channel access? Send us a message.",
    contactEmailLabel: "Email",
    contactEmail: companyInformation.contactEmail,
    contactBackHome: "Back to home",
  },
  fr: {
    loading: "Chargement...",
    performanceUnavailable:
      "Les données de performance historique sont temporairement indisponibles.",
    contactTitle: "Contactez-nous",
    contactSubtitle:
      "Une question sur les signaux, l’abonnement ou l’accès au canal privé ? Envoyez-nous un message.",
    contactEmailLabel: "Email",
    contactEmail: companyInformation.contactEmail,
    contactBackHome: "Retour à l’accueil",
  },
} satisfies Record<Language, Record<string, string>>;

function getStoredLanguage(): Language {
  const language = localStorage.getItem("language");
  return language === "fr" ? "fr" : "en";
}

function t(key: keyof typeof messages.en) {
  return messages[getStoredLanguage()][key];
}

function LoadingScreen({ message = t("loading") }: { message?: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        background: "#09090A",
        color: "#C8A84B",
        fontFamily: "DM Sans, sans-serif",
      }}
    >
      {message}
    </div>
  );
}

function PublicDataUnavailable({ message }: { message: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        background: "#09090A",
        color: "#E8E4D8",
        fontFamily: "DM Sans, sans-serif",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <span>{message}</span>
      <a href="/" style={{ color: "#C8A84B" }}>
        AuroRatio
      </a>
    </div>
  );
}

function ScrollToHash() {
  const location = useLocation();

  useEffect(() => {
    if (location.hash) {
      setTimeout(() => {
        const element = document.querySelector(location.hash);
        if (element) {
          element.scrollIntoView({ behavior: getScrollBehavior() });
        }
      }, 100);
    } else {
      window.scrollTo(0, 0);
    }
  }, [location]);

  return null;
}

function useMarketData() {
  const [marketData, setMarketData] = useState<MarketData | null>(null);

  useEffect(() => {
    void loadPublicResource<MarketData>(getPublicMarketData).then(setMarketData);
  }, []);

  return marketData;
}

function useBacktestData() {
  const [backtestData, setBacktestData] = useState<BacktestData | null>(null);
  const [attempted, setAttempted] = useState(false);

  useEffect(() => {
    void loadPublicResource<BacktestData>(getPublicBacktestData).then((data) => {
      setBacktestData(data);
      setAttempted(true);
    });
  }, []);

  return { backtestData, attempted };
}

function LandingRoute() {
  const marketData = useMarketData();

  return (
    <Landing
      marketData={marketData ?? EMPTY_MARKET_DATA}
      marketDataAvailable={marketData !== null}
    />
  );
}

function PlatformRoute() {
  const marketData = useMarketData();
  return (
    <Platform
      marketData={marketData ?? EMPTY_MARKET_DATA}
      marketDataAvailable={marketData !== null}
    />
  );
}

function ContactRoute() {
  const marketData = useMarketData();
  return (
    <Contact
      marketData={marketData ?? EMPTY_MARKET_DATA}
      marketDataAvailable={marketData !== null}
    />
  );
}

function PerformanceRoute() {
  const marketData = useMarketData();
  const { backtestData, attempted } = useBacktestData();

  if (!attempted) {
    return <LoadingScreen />;
  }

  if (!backtestData) {
    return <PublicDataUnavailable message={t("performanceUnavailable")} />;
  }

  return (
    <Performance
      marketData={marketData ?? EMPTY_MARKET_DATA}
      backtestData={backtestData}
      marketDataAvailable={marketData !== null}
    />
  );
}

const legalRoutes = [
  ["/legal-notice", "Legal Notice", "Mentions légales"],
  ["/terms", "Terms and Conditions", "Conditions générales"],
  ["/privacy", "Privacy Policy", "Politique de confidentialité"],
  ["/cookie-policy", "Cookie Policy", "Politique relative aux cookies"],
  ["/risk-disclosure", "Risk Disclosure", "Information sur les risques"],
  ["/refund-policy", "Refund Policy", "Politique de remboursement"],
  ["/cancellation-policy", "Cancellation Policy", "Politique d’annulation"],
  ["/withdrawal-policy", "Withdrawal Policy", "Politique de rétractation"],
] as const;

export default function App() {
  return (
    <BrowserRouter>
      <ScrollToHash />

      <Routes>
        <Route path="/" element={<LandingRoute />} />
        <Route path="/platform" element={<PlatformRoute />} />
        <Route path="/performance" element={<PerformanceRoute />} />
        <Route path="/contact" element={<ContactRoute />} />
        <Route
          path="/subscription/success"
          element={<SubscriptionOutcome outcome="success" />}
        />
        <Route
          path="/subscription/cancelled"
          element={<SubscriptionOutcome outcome="cancelled" />}
        />
        <Route path="/manage-subscription" element={<ManageSubscription />} />
        <Route
          path="/manage-subscription/access"
          element={<ManageSubscription accessLink />}
        />

        {legalRoutes.map(([path, documentName, documentNameFr]) => (
          <Route
            key={path}
            path={path}
            element={
              <LegalPlaceholder
                documentName={documentName}
                documentNameFr={documentNameFr}
              />
            }
          />
        ))}

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
