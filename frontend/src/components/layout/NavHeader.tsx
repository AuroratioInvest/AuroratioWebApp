import { useNavigate, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { legacyCustomerAppEnabled } from "../../config/features";

type Language = "en" | "fr";

const labels = {
  en: {
    account: "Account",
    dashboard: "Dashboard",
    activity: "Activity",
    settings: "Settings",
    admin: "Admin",
    // contact: "Contact",
    signOut: "Sign out",
    goToDashboard: "Go to dashboard",
    mainNavigation: "Main navigation",
  },
  fr: {
    account: "Compte",
    dashboard: "Tableau de bord",
    activity: "Activité",
    settings: "Paramètres",
    admin: "Admin",
    // contact: "Contact",
    signOut: "Déconnexion",
    goToDashboard: "Aller au tableau de bord",
    mainNavigation: "Navigation principale",
  },
} satisfies Record<Language, Record<string, string>>;

function getStoredLanguage(): Language {
  const language = localStorage.getItem("language");
  return language === "fr" ? "fr" : "en";
}

export default function NavHeader() {
  const navigate = useNavigate();
  const location = useLocation();

  const [language, setLanguage] = useState<Language>(getStoredLanguage());

  const text = labels[language];
  const email = localStorage.getItem("user_email") || text.account;
  const isAurum = localStorage.getItem("membership_level") === "aurum";

  useEffect(() => {
    localStorage.setItem("language", language);
  }, [language]);

  const handleLanguageChange = (nextLanguage: Language) => {
    setLanguage(nextLanguage);
    localStorage.setItem("language", nextLanguage);
    window.dispatchEvent(new Event("languagechange"));
  };

  const handleLogout = () => {
    const lang = localStorage.getItem("language");
    localStorage.clear();
    if (lang) localStorage.setItem("language", lang);
    navigate("/", { replace: true });
  };

  const navBtn = (path: string, label: string) => {
    const active = location.pathname === path;

    return (
      <button
        key={path}
        onClick={() => navigate(path)}
        className={`nav-link ${active ? "active" : ""}`}
      >
        {label}
      </button>
    );
  };

  return (
    <header className="auroratio-header">
      <style>{`
        .auroratio-header {
          position: relative;
          z-index: 10;
          border-bottom: 1px solid var(--rule, rgba(201,168,76,.18));
          background: rgba(10,10,8,.78);
          backdrop-filter: blur(18px);
          -webkit-backdrop-filter: blur(18px);
        }

        .auroratio-header-inner {
          max-width: 1180px;
          margin: 0 auto;
          padding: 1.05rem 3rem;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 2rem;
        }

        .auroratio-header-left {
          display: flex;
          align-items: center;
          gap: 2.5rem;
          min-width: 0;
        }

        .brand-button {
          display: inline-flex;
          align-items: center;
          gap: .75rem;
          background: transparent;
          border: 0;
          padding: 0;
          cursor: pointer;
          color: inherit;
        }

        .brand-name {
          font-family: 'Cormorant Garamond', serif;
          color: var(--gold, #C9A84C);
          font-size: 1.45rem;
          line-height: 1;
          font-weight: 500;
          letter-spacing: .12em;
          text-transform: uppercase;
        }

        .brand-name span {
          color: var(--text, #E8E4D8);
        }

        .nav-links {
          display: flex;
          align-items: center;
          gap: .35rem;
        }

        .nav-link {
          position: relative;
          border: 1px solid transparent;
          background: transparent;
          color: var(--text-muted, #8A8670);
          border-radius: 999px;
          padding: .55rem .85rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .72rem;
          letter-spacing: .11em;
          text-transform: uppercase;
          cursor: pointer;
          transition: color .2s, border-color .2s, background .2s;
          white-space: nowrap;
        }

        .nav-link:hover {
          color: var(--text, #E8E4D8);
          border-color: rgba(201,168,76,.18);
          background: rgba(201,168,76,.04);
        }

        .nav-link.active {
          color: var(--text, #E8E4D8);
          border-color: rgba(201,168,76,.28);
          background: rgba(201,168,76,.08);
        }

        .auroratio-header-right {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 1rem;
          min-width: 0;
        }

        .account-email {
          max-width: 220px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          color: var(--text-muted, #8A8670);
          font-size: .82rem;
        }

        .language-toggle {
          display: inline-flex;
          align-items: center;
          gap: .2rem;
          border: 1px solid var(--rule, rgba(201,168,76,.18));
          border-radius: 999px;
          background: rgba(255,255,255,.018);
          padding: .2rem;
        }

        .language-option {
          border: 0;
          background: transparent;
          color: var(--text-muted, #8A8670);
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
          color: var(--text, #E8E4D8);
        }

        .language-option.active {
          background: rgba(201,168,76,.12);
          color: var(--gold, #C9A84C);
        }

        .signout-button {
          border: 1px solid var(--rule, rgba(201,168,76,.18));
          background: rgba(255,255,255,.018);
          color: var(--text-muted, #8A8670);
          border-radius: 999px;
          padding: .62rem .95rem;
          font-family: 'DM Sans', sans-serif;
          font-size: .72rem;
          letter-spacing: .1em;
          text-transform: uppercase;
          cursor: pointer;
          transition: color .2s, border-color .2s, background .2s, transform .15s;
          white-space: nowrap;
        }

        .signout-button:hover {
          color: var(--text, #E8E4D8);
          border-color: rgba(201,168,76,.36);
          background: rgba(201,168,76,.06);
          transform: translateY(-1px);
        }

        @media (max-width: 900px) {
          .auroratio-header-inner {
            padding: 1rem 1.5rem;
            align-items: flex-start;
            flex-direction: column;
          }

          .auroratio-header-left {
            width: 100%;
            justify-content: space-between;
            gap: 1rem;
          }

          .nav-links {
            overflow-x: auto;
            max-width: 100%;
            padding-bottom: .2rem;
          }

          .auroratio-header-right {
            width: 100%;
            justify-content: space-between;
            flex-wrap: wrap;
          }
        }

        @media (max-width: 640px) {
          .auroratio-header-left {
            align-items: flex-start;
            flex-direction: column;
          }

          .brand-name {
            font-size: 1.5rem;
          }
        }
      `}</style>

      <div className="auroratio-header-inner">
        <div className="auroratio-header-left">
          <button
            className="brand-button"
            onClick={() => navigate(legacyCustomerAppEnabled ? "/dashboard" : "/")}
            aria-label={text.goToDashboard}
          >
            <span className="brand-name">
              <span>Auro</span>Ratio
            </span>
          </button>

          <nav className="nav-links" aria-label={text.mainNavigation}>
            {legacyCustomerAppEnabled && navBtn("/dashboard", text.dashboard)}
            {legacyCustomerAppEnabled && navBtn("/history", text.activity)}
            {legacyCustomerAppEnabled && navBtn("/settings", text.settings)}
            {/* {navBtn("/contact", text.contact)} */}
            {isAurum && navBtn("/admin", text.admin)}
          </nav>
        </div>

        <div className="auroratio-header-right">
          <span className="account-email" title={email}>
            {email}
          </span>

          <div className="language-toggle" aria-label="Language selector">
            <button
              type="button"
              onClick={() => handleLanguageChange("en")}
              className={`language-option ${language === "en" ? "active" : ""}`}
            >
              EN
            </button>

            <button
              type="button"
              onClick={() => handleLanguageChange("fr")}
              className={`language-option ${language === "fr" ? "active" : ""}`}
            >
              FR
            </button>
          </div>

          <button onClick={handleLogout} className="signout-button">
            {text.signOut}
          </button>
        </div>
      </div>
    </header>
  );
}
