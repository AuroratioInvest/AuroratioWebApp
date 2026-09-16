import { useState } from "react";
import PhoneInput from "react-phone-number-input";
import "react-phone-number-input/style.css";
import { isValidPhoneNumber } from "libphonenumber-js";
import axios from "axios";
import client from "../api/client";
import PublicFooter from "../components/PublicFooter";
import PublicHeader from "../components/PublicHeader";
import PublicCheckoutError from "../components/PublicCheckoutError";
import Ticker from "../components/Ticker";
import type { MarketData } from "../types/market";
import { usePublicCheckout } from "../hooks/usePublicCheckout";
import { usePublicLanguage } from "../context/PublicLanguageContext";
import { companyInformation } from "../config/companyInformation";


interface ContactProps {
  marketData: MarketData;
  marketDataAvailable: boolean;
}

export default function Contact({ marketData, marketDataAvailable }: ContactProps) {

  const { language } = usePublicLanguage();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState<string | undefined>();
  const [description, setDescription] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const text = {
    en: {
      how: "How it works",
      features: "Benefits",
      methodology: "Methodology",
      research: "Historical research",
      pricing: "Pricing",
      contact: "Contact",
      eyebrow: "Contact us",
      title: "How can we help?",
      subtitle:
        "Ask about the signal service, subscription launch, private-channel access, or the methodology.",
      directEmail: "Or email us directly at",
      firstName: "First name",
      lastName: "Last name",
      email: "Email",
      phone: "Phone number optional",
      description: "Description",
      submit: "Send message",
      sending: "Sending...",
      success: "Your message has been sent successfully.",
      errRequired: "Please fill in all required fields.",
      errPhone: "Please enter a valid phone number.",
      errGeneric: "Could not send your message. Please try again.",
    },
    fr: {
      how: "Fonctionnement",
      features: "Avantages",
      methodology: "Méthodologie",
      research: "Recherche historique",
      pricing: "Tarifs",
      contact: "Contact",
      eyebrow: "Contact",
      title: "Comment pouvons-nous vous aider ?",
      subtitle:
        "Posez vos questions sur le service de signaux, le lancement, l’accès au canal privé ou la méthodologie.",
      directEmail: "Ou écrivez-nous directement à",
      firstName: "Prénom",
      lastName: "Nom",
      email: "Email",
      phone: "Numéro de téléphone optionnel",
      description: "Description",
      submit: "Envoyer le message",
      sending: "Envoi...",
      success: "Votre message a bien été envoyé.",
      errRequired: "Veuillez remplir tous les champs obligatoires.",
      errPhone: "Veuillez entrer un numéro de téléphone valide.",
      errGeneric: "Impossible d’envoyer votre message. Veuillez réessayer.",
    },
  }[language];

  const { beginCheckout, checkoutError, checkoutLoading } = usePublicCheckout(language, {
    error:
      language === "fr"
        ? "Impossible d’ouvrir le paiement sécurisé. Veuillez réessayer ou contacter le support."
        : "We couldn’t open secure checkout. Please try again or contact support.",
  });

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (!firstName.trim() || !lastName.trim() || !email.trim() || !description.trim()) {
      setError(text.errRequired);
      return;
    }

    if (phone && !isValidPhoneNumber(phone)) {
      setError(text.errPhone);
      return;
    }

    setLoading(true);

    try {
      await client.post("/contact", {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim().toLowerCase(),
        phone: phone || null,
        description: description.trim(),
      });

      setSuccess(text.success);
      setFirstName("");
      setLastName("");
      setEmail("");
      setPhone(undefined);
      setDescription("");
    } catch (error: unknown) {
      const detail = axios.isAxiosError(error)
        ? error.response?.data?.detail
        : undefined;
      setError(detail || text.errGeneric);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="contact-page">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600&family=Syncopate:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

        .contact-page {
          --gold: #C9A84C;
          --gold-light: #E8C97A;
          --ink: #0A0A08;
          --ink-2: #111109;
          --text: #E8E4D8;
          --text-muted: #8A8670;
          --rule: rgba(201,168,76,.18);
          --r: 4px;

          min-height: 100vh;
          background: var(--ink);
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          overflow-x: hidden;
        }

        .contact-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: radial-gradient(circle at top, rgba(201,168,76,.08), transparent 34rem);
          pointer-events: none;
        }

        .site-nav {
          position: sticky;
          top: 0;
          z-index: 100;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 40px;
          height: 64px;
          background: rgba(10,10,8,.78);
          backdrop-filter: blur(18px);
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
          border: 1px solid transparent;
          background: transparent;
          color: var(--text-muted);
          border-radius: 999px;
          padding: .55rem .85rem;
          font-size: .72rem;
          letter-spacing: .11em;
          text-transform: uppercase;
          text-decoration: none;
          cursor: pointer;
          transition: color .2s, border-color .2s, background .2s;
          white-space: nowrap;
        }

        .nav-links a:hover,
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
        }

        .language-option.active {
          background: rgba(201,168,76,.12);
          color: var(--gold);
        }

        .btn-ghost {
          font-size: 13px;
          color: var(--text-muted);
          background: none;
          border: none;
          cursor: pointer;
        }

        .btn-ghost:hover { color: var(--text); }

        .btn-primary {
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
        }

        .btn-primary:hover { background: var(--gold-light); }

        .contact-main {
          position: relative;
          z-index: 1;
          max-width: 1040px;
          margin: 0 auto;
          padding: 6rem 2rem;
          display: grid;
          grid-template-columns: .9fr 1.1fr;
          gap: 3rem;
          align-items: start;
        }

        .contact-eyebrow {
          font-family: 'Syncopate', sans-serif;
          color: var(--gold-light);
          font-size: .72rem;
          letter-spacing: .16em;
          text-transform: uppercase;
          margin-bottom: 1rem;
          font-weight: 700;
        }

        .contact-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: clamp(3rem, 6vw, 5rem);
          line-height: .95;
          font-weight: 300;
          margin-bottom: 1.25rem;
        }

        .contact-title em {
          color: var(--gold-light);
          font-style: italic;
        }

        .contact-subtitle {
          color: var(--text-muted);
          line-height: 1.75;
          max-width: 460px;
        }

        .contact-direct-email {
          margin-top: 1rem;
          color: var(--text-muted);
          font-size: .9rem;
          line-height: 1.65;
        }

        .contact-direct-email a {
          color: var(--gold-light);
          text-underline-offset: .22em;
        }

        .contact-card {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 2.5rem;
          box-shadow: 0 24px 80px rgba(0,0,0,.35);
        }

        .contact-form {
          display: grid;
          gap: 1.1rem;
        }

        .form-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1rem;
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

        .form-input,
        .form-textarea {
          width: 100%;
          box-sizing: border-box;
          background: var(--ink);
          border: 1px solid var(--rule);
          border-radius: 5px;
          padding: .95rem 1rem;
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          font-size: 1rem;
        }

        .form-textarea {
          min-height: 150px;
          resize: vertical;
        }

        .form-input:focus,
        .form-textarea:focus {
          outline: none;
          border-color: var(--gold);
          box-shadow: 0 0 0 3px rgba(201,168,76,.1);
        }

        .phone-input {
          width: 100%;
          background: var(--ink);
          border: 1px solid var(--rule);
          border-radius: 5px;
          padding: .95rem 1rem;
          color: var(--text);
        }

        .phone-input:focus-within {
          border-color: var(--gold);
          box-shadow: 0 0 0 3px rgba(201,168,76,.1);
        }

        .phone-input input {
          background: transparent;
          border: 0;
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
          font-size: 1rem;
          outline: none;
        }

        .phone-input select {
          background: var(--ink);
          color: var(--text);
        }

        .submit-button {
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
        }

        .submit-button:hover:not(:disabled) {
          background: var(--gold-light);
        }

        .submit-button:disabled {
          opacity: .55;
          cursor: not-allowed;
        }

        .error-message,
        .success-message {
          border-radius: 5px;
          padding: .85rem 1rem;
          font-size: .88rem;
          line-height: 1.5;
        }

        .error-message {
          background: rgba(239,83,80,.1);
          border: 1px solid rgba(239,83,80,.28);
          color: #EF8A85;
        }

        .success-message {
          background: rgba(201,168,76,.08);
          border: 1px solid rgba(201,168,76,.24);
          color: var(--gold-light);
        }
        @media (max-width: 860px) {
          .contact-main {
            grid-template-columns: 1fr;
            padding: 4rem 1.5rem;
          }

          .form-grid {
            grid-template-columns: 1fr;
          }

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
          }

          .nav-cta {
            margin-left: auto;
          }

          .contact-card {
            padding: 2rem;
          }
        }
      `}</style>

      {marketDataAvailable && <Ticker marketData={marketData} />}

      <PublicHeader
        onSubscribe={beginCheckout}
        checkoutLoading={checkoutLoading}
        activePage="contact"
      />

      <PublicCheckoutError message={checkoutError} showSupportLink={false} />

      <main className="contact-main">
        <section>
          <p className="contact-eyebrow">{text.eyebrow}</p>
          <h1 className="contact-title">
            {language === "fr" ? (
              <>
                Contactez <em>nous</em>
              </>
            ) : (
              <>
                Get in <em>touch</em>
              </>
            )}
          </h1>
          <p className="contact-subtitle">{text.subtitle}</p>
          <p className="contact-direct-email">
            {text.directEmail}{" "}
            <a href={`mailto:${companyInformation.contactEmail}`}>
              {companyInformation.contactEmail}
            </a>
          </p>
        </section>

        <section className="contact-card">
          <form className="contact-form" onSubmit={handleSubmit}>
            {error && (
              <div className="error-message" role="alert">
                {error}
              </div>
            )}
            {success && (
              <div className="success-message" role="status">
                {success}
              </div>
            )}

            <div className="form-grid">
              <div className="form-group">
                <label className="form-label" htmlFor="contact-first-name">
                  {text.firstName}
                </label>
                <input
                  id="contact-first-name"
                  name="firstName"
                  className="form-input"
                  value={firstName}
                  onChange={(event) => setFirstName(event.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="contact-last-name">
                  {text.lastName}
                </label>
                <input
                  id="contact-last-name"
                  name="lastName"
                  className="form-input"
                  value={lastName}
                  onChange={(event) => setLastName(event.target.value)}
                  required
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="contact-email">
                {text.email}
              </label>
              <input
                id="contact-email"
                name="email"
                className="form-input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="contact-phone">
                {text.phone}
              </label>
              <PhoneInput
                id="contact-phone"
                name="phone"
                international
                defaultCountry="FR"
                value={phone}
                onChange={setPhone}
                className="phone-input"
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="contact-message">
                {text.description}
              </label>
              <textarea
                id="contact-message"
                name="message"
                className="form-textarea"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                required
              />
            </div>

            <button className="submit-button" type="submit" disabled={loading}>
              {loading ? text.sending : text.submit}
            </button>
          </form>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
