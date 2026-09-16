import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import axios from "axios";
import { login } from "../api/auth";

type Language = "en" | "fr";

const copy = {
  en: {
    createAccount: "Create an account",
    welcome: "Welcome back",
    title: "Sign In",
    subtitle: "Access your AuroRatio dashboard and portfolio.",
    email: "Email",
    password: "Password",
    signingIn: "Signing in...",
    signIn: "Sign in",
    forgotPassword: "Forgot your password?",
    noAccount: "Don’t have an account?",
    signUp: "Sign up",
    language: "Language",
    invalid: "Invalid email or password.",
  },
  fr: {
    createAccount: "Créer un compte",
    welcome: "Bon retour",
    title: "Connexion",
    subtitle: "Accédez à votre tableau de bord et à votre portefeuille AuroRatio.",
    email: "Email",
    password: "Mot de passe",
    signingIn: "Connexion...",
    signIn: "Se connecter",
    forgotPassword: "Mot de passe oublié ?",
    noAccount: "Vous n’avez pas encore de compte ?",
    signUp: "S’inscrire",
    language: "Langue",
    invalid: "Email ou mot de passe invalide.",
  },
} satisfies Record<Language, Record<string, string>>;

function getStoredLanguage(): Language {
  return localStorage.getItem("language") === "fr" ? "fr" : "en";
}

function BrandName() {
  // return (
  //   <span className="brand-inline">
  //     <span>Auro</span>Ratio
  //   </span>
  // );
  return "AuroRatio";
}

export default function Login({ adminOnly = false }: { adminOnly?: boolean }) {
  const [language, setLanguage] = useState<Language>(getStoredLanguage());
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();
  const text = copy[language];

  const handleLanguageChange = (nextLanguage: Language) => {
    setLanguage(nextLanguage);
    localStorage.setItem("language", nextLanguage);
    window.dispatchEvent(new Event("languagechange"));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(email, password);
      navigate(adminOnly ? "/admin" : "/dashboard", { replace: true });
    } catch (error: unknown) {
      const detail = axios.isAxiosError(error)
        ? error.response?.data?.detail
        : undefined;
      setError(detail || text.invalid);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;0,700;1,300;1,400&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

        .auth-page {
          --gold: #C9A84C;
          --gold-light: #E8C97A;
          --ink: #0A0A08;
          --ink-2: #111109;
          --text: #E8E4D8;
          --text-muted: #8A8670;
          --rule: rgba(201,168,76,.18);
          min-height: 100vh;
          background: var(--ink);
          color: var(--text);
          display: flex;
          flex-direction: column;
          font-family: 'DM Sans', sans-serif;
          position: relative;
        }

        .auth-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: radial-gradient(circle at top, rgba(201,168,76,.08), transparent 32rem);
          pointer-events: none;
        }

        .auth-header {
          position: relative;
          z-index: 2;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
          padding: 1.5rem 3rem;
          border-bottom: 1px solid var(--rule);
          background: rgba(10,10,8,.82);
          backdrop-filter: blur(12px);
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 1rem;
        }

        .wordmark {
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.7rem;
          text-decoration: none;
          color: var(--text);
        }

        .wordmark span,
        .brand-inline span {
          color: var(--gold-light);
        }

        .brand-inline {
          color: var(--text);
        }

        .header-link,
        .text-link {
          color: var(--text-muted);
          text-decoration: none;
          transition: color .2s;
        }

        .header-link:hover,
        .text-link:hover {
          color: var(--gold-light);
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
        }

        .language-option.active {
          background: rgba(201,168,76,.12);
          color: var(--gold);
        }

        .auth-container {
          position: relative;
          z-index: 1;
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 2rem;
        }

        .auth-card {
          width: 100%;
          max-width: 440px;
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 3rem;
          box-shadow: 0 24px 80px rgba(0,0,0,.35);
        }

        .auth-eyebrow {
          font-family: 'Syncopate', sans-serif;
          text-transform: uppercase;
          font-size: .7rem;
          letter-spacing: .18em;
          color: var(--gold-light);
          margin-bottom: .75rem;
          font-weight: 700;
        }

        .auth-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 2.75rem;
          font-weight: 400;
          line-height: 1.05;
          margin: 0 0 .6rem;
          color: var(--text);
        }

        .auth-subtitle {
          color: var(--text-muted);
          line-height: 1.6;
          margin: 0 0 2rem;
          font-size: .95rem;
        }

        .auth-form {
          display: grid;
          gap: 1.1rem;
        }

        .form-group {
          display: grid;
          gap: .45rem;
        }

        .form-label {
          font-size: .75rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: .08em;
        }

        .form-input {
          width: 100%;
          box-sizing: border-box;
          background: var(--ink);
          border: 1px solid var(--rule);
          border-radius: 5px;
          padding: .95rem 1rem;
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          font-size: 1rem;
          transition: border-color .2s, box-shadow .2s;
        }

        .form-input::placeholder {
          color: var(--text-muted);
          opacity: .5;
        }

        .form-input:focus {
          outline: none;
          border-color: var(--gold);
          box-shadow: 0 0 0 3px rgba(201,168,76,.1);
        }

        .error-message {
          background: rgba(239,83,80,.1);
          border: 1px solid rgba(239,83,80,.28);
          border-radius: 5px;
          padding: .85rem 1rem;
          color: #EF8A85;
          font-size: .88rem;
          line-height: 1.5;
        }

        .auth-button {
          border-radius: 5px;
          padding: 1rem 1.3rem;
          font-family: 'DM Sans', sans-serif;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: .06em;
          cursor: pointer;
          border: 0;
          background: var(--gold);
          color: var(--ink);
          transition: background .2s, opacity .2s;
          margin-top: .25rem;
        }

        .auth-button:hover:not(:disabled) {
          background: var(--gold-light);
        }

        .auth-button:disabled {
          opacity: .55;
          cursor: not-allowed;
        }

        .auth-footer {
          margin-top: 1.5rem;
          padding-top: 1.5rem;
          border-top: 1px solid var(--rule);
          text-align: center;
          color: var(--text-muted);
          font-size: .9rem;
          display: grid;
          gap: .75rem;
        }

        .auth-text {
          color: var(--text-muted);
          font-size: .9rem;
        }

        @media (max-width: 720px) {
          .auth-header {
            padding: 1.2rem 1.5rem;
            flex-wrap: wrap;
          }

          .auth-card {
            padding: 2rem;
          }

          .auth-title {
            font-size: 2.3rem;
          }
        }
      `}</style>

      <header className="auth-header">
        <Link to="/" className="wordmark">
          <span>Auro</span>Ratio
        </Link>

        <div className="header-actions">
          <div className="language-toggle" aria-label={text.language}>
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

          {!adminOnly && (
            <Link to="/signup" className="header-link">
              {text.createAccount}
            </Link>
          )}
        </div>
      </header>

      <main className="auth-container">
        <section className="auth-card">
          <p className="auth-eyebrow">{text.welcome}</p>
          <h1 className="auth-title">{text.title}</h1>
          <p className="auth-subtitle">
            {language === "fr" ? (
              <>
                Accédez à votre tableau de bord et à votre portefeuille <BrandName />.
              </>
            ) : (
              <>
                Access your <BrandName /> dashboard and portfolio.
              </>
            )}
          </p>

          <form onSubmit={handleSubmit} className="auth-form">
            {error && <div className="error-message">{error}</div>}

            <div className="form-group">
              <label className="form-label">{text.email}</label>
              <input
                type="email"
                className="form-input"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">{text.password}</label>
              <input
                type="password"
                className="form-input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <button type="submit" className="auth-button" disabled={loading}>
              {loading ? text.signingIn : text.signIn}
            </button>
          </form>

          {!adminOnly && (
            <div className="auth-footer">
              <Link to="/forgot-password" className="text-link">
                {text.forgotPassword}
              </Link>

              <div className="auth-text">
                {text.noAccount}{" "}
                <Link to="/signup" className="text-link">
                  {text.signUp}
                </Link>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
