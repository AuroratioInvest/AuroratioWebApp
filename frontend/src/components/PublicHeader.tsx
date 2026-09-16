import { Link, useLocation } from "react-router-dom";
import { getScrollBehavior } from "../utils/motion";
import { usePublicLanguage, type PublicLanguage } from "../context/PublicLanguageContext";
type PublicPage = "home" | "platform" | "performance" | "contact";
type HomeSection = "how" | "features" | "why-auroratio" | "pricing" | "faq" | null;

interface PublicHeaderProps {
  onSubscribe: () => void;
  checkoutLoading: boolean;
  activePage?: PublicPage;
  activeSection?: HomeSection;
  onHomeReset?: () => void;
}

const labels = {
  en: {
    how: "How it works",
    benefits: "Benefits",
    whyAuroRatio: "Why AuroRatio?",
    methodology: "Methodology",
    research: "Historical Research",
    pricing: "Pricing",
    faq: "FAQ",
    contact: "Contact",
    subscribe: "Subscribe",
    opening: "Opening…",
    navigation: "Primary navigation",
    language: "Language selector",
    home: "AuroRatio home",
  },
  fr: {
    how: "Fonctionnement",
    benefits: "Avantages",
    whyAuroRatio: "Pourquoi AuroRatio ?",
    methodology: "Méthodologie",
    research: "Recherche historique",
    pricing: "Tarifs",
    faq: "FAQ",
    contact: "Contact",
    subscribe: "S’abonner",
    opening: "Ouverture…",
    navigation: "Navigation principale",
    language: "Sélection de la langue",
    home: "Accueil AuroRatio",
  },
} satisfies Record<PublicLanguage, Record<string, string>>;

export default function PublicHeader({
  onSubscribe,
  checkoutLoading,
  activePage,
  activeSection = null,
  onHomeReset,
}: PublicHeaderProps) {
  const location = useLocation();
  const { language, setLanguage } = usePublicLanguage();
  const text = labels[language];
  const isHome = location.pathname === "/";

  const handleLogoClick = () => {
    onHomeReset?.();
    if (isHome) {
      window.history.replaceState(null, "", "/");
      window.scrollTo({ top: 0, behavior: getScrollBehavior() });
    }
  };

  const sectionClass = (section: Exclude<HomeSection, null>) =>
    isHome && activeSection === section ? "active" : undefined;
  const pageClass = (page: PublicPage) =>
    activePage === page ? "active" : undefined;

  return (
    <>
      <style>{`
        .public-site-nav {
          position: sticky;
          top: 0;
          z-index: 100;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1.25rem;
          min-height: 64px;
          padding: 0 40px;
          background: rgba(10,10,8,.82);
          backdrop-filter: blur(18px);
          -webkit-backdrop-filter: blur(18px);
          border-bottom: 1px solid var(--rule, rgba(201,168,76,.18));
        }
        .public-site-logo {
          font-family: 'Cormorant Garamond', serif;
          font-size: 22px;
          font-weight: 500;
          color: var(--gold, #C9A84C);
          letter-spacing: .12em;
          text-transform: uppercase;
          text-decoration: none;
          white-space: nowrap;
        }
        .public-site-logo span { color: var(--text, #E8E4D8); }
        .public-site-logo sup {
          margin-left: .14em;
          font-family: 'DM Sans', sans-serif;
          font-size: .38em;
          letter-spacing: 0;
          vertical-align: super;
        }
        .public-site-links {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: .2rem;
          margin: 0;
          padding: 0;
          list-style: none;
        }
        .public-site-links a {
          display: inline-flex;
          border: 1px solid transparent;
          border-radius: 999px;
          padding: .52rem .7rem;
          color: var(--text-muted, #8A8670);
          font-size: .68rem;
          letter-spacing: .09em;
          line-height: 1.2;
          text-transform: uppercase;
          text-decoration: none;
          white-space: nowrap;
          transition: color .2s, border-color .2s, background .2s;
        }
        .public-site-links a:hover,
        .public-site-links a.active {
          color: var(--text, #E8E4D8);
          border-color: rgba(201,168,76,.28);
          background: rgba(201,168,76,.08);
        }
        .public-site-actions {
          display: flex;
          align-items: center;
          gap: .7rem;
          white-space: nowrap;
        }
        .public-language-toggle {
          display: inline-flex;
          align-items: center;
          gap: .15rem;
          padding: .18rem;
          border: 1px solid var(--rule, rgba(201,168,76,.18));
          border-radius: 999px;
        }
        .public-language-toggle button {
          border: 0;
          border-radius: 999px;
          padding: .4rem .52rem;
          background: transparent;
          color: var(--text-muted, #8A8670);
          font: inherit;
          font-size: .66rem;
          letter-spacing: .08em;
          cursor: pointer;
        }
        .public-language-toggle button.active {
          background: rgba(201,168,76,.12);
          color: var(--gold, #C9A84C);
        }
        .public-subscribe-button {
          border: 1px solid var(--gold, #C9A84C);
          border-radius: 999px;
          padding: .62rem 1rem;
          background: var(--gold, #C9A84C);
          color: #0A0A08;
          font: inherit;
          font-size: .7rem;
          font-weight: 600;
          letter-spacing: .08em;
          text-transform: uppercase;
          cursor: pointer;
        }
        .public-subscribe-button:disabled { opacity: .65; cursor: wait; }
        .public-site-nav a:focus-visible,
        .public-site-nav button:focus-visible {
          outline: 2px solid var(--gold-light, #E8C97A);
          outline-offset: 3px;
        }
        @media (max-width: 1380px) {
          .public-site-nav { padding: .75rem 20px; flex-wrap: wrap; }
          .public-site-links { order: 3; width: 100%; overflow-x: auto; justify-content: flex-start; padding-bottom: .15rem; }
        }
        @media (max-width: 620px) {
          .public-site-nav { padding: .7rem 14px; }
          .public-subscribe-button { padding: .56rem .72rem; }
          .public-site-logo { font-size: 19px; }
        }
      `}</style>
      <nav className="public-site-nav" aria-label={text.navigation}>
        <Link className="public-site-logo" to="/" onClick={handleLogoClick} aria-label={text.home}>
          <span>Auro</span>Ratio<sup aria-hidden="true">®</sup>
        </Link>

        <ul className="public-site-links">
          <li><Link className={sectionClass("how")} to="/#how">{text.how}</Link></li>
          <li><Link className={sectionClass("features")} to="/#features">{text.benefits}</Link></li>
          <li><Link className={sectionClass("why-auroratio")} to="/#why-auroratio">{text.whyAuroRatio}</Link></li>
          <li><Link className={pageClass("platform")} to="/platform">{text.methodology}</Link></li>
          <li><Link className={pageClass("performance")} to="/performance">{text.research}</Link></li>
          <li><Link className={sectionClass("pricing")} to="/#pricing">{text.pricing}</Link></li>
          <li><Link className={sectionClass("faq")} to="/#faq">{text.faq}</Link></li>
          <li><Link className={pageClass("contact")} to="/contact">{text.contact}</Link></li>
        </ul>

        <div className="public-site-actions">
          <div className="public-language-toggle" role="group" aria-label={text.language}>
            <button type="button" className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")} aria-pressed={language === "en"}>EN</button>
            <button type="button" className={language === "fr" ? "active" : ""} onClick={() => setLanguage("fr")} aria-pressed={language === "fr"}>FR</button>
          </div>
          <button type="button" className="public-subscribe-button" onClick={onSubscribe} disabled={checkoutLoading}>
            {checkoutLoading ? text.opening : text.subscribe}
          </button>
        </div>
      </nav>
    </>
  );
}
