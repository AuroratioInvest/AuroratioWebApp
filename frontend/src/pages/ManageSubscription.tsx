import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";

import {
  exchangeBillingManagementToken,
  requestBillingManagementLink,
} from "../api/publicBilling";
import PublicFooter from "../components/PublicFooter";
import PublicHeader from "../components/PublicHeader";
import { companyInformation } from "../config/companyInformation";
import { usePublicLanguage } from "../context/PublicLanguageContext";
import { usePublicCheckout } from "../hooks/usePublicCheckout";
import { isTrustedStripeHostedUrl } from "../utils/billingSecurity";

const copy = {
  en: {
    checkoutError: "We couldn’t open secure checkout. Nothing has been charged. Please try again.",
    eyebrow: "Secure billing management",
    title: "Manage your subscription",
    body:
      "Use the billing email entered during checkout. If an eligible subscription exists, we will email a short-lived, single-use link to the secure billing portal.",
    optionsTitle: "From the secure portal you can",
    options: [
      "Update your payment method.",
      "Review invoices and billing details.",
      "Cancel or manage renewal when available.",
    ],
    email: "Billing email",
    emailHint: "Use the exact email address entered during checkout.",
    submit: "Email my secure link",
    submitting: "Sending request…",
    generic:
      "Request received. If an eligible subscription exists for that email, a secure billing-management link will be sent shortly.",
    deliveryHelp:
      "Check your inbox and spam folder. For security, we show the same confirmation whether or not an email matches a subscription.",
    error:
      "We could not submit your request. Nothing was changed. Please try again or contact support.",
    portalReturn:
      "You have returned from secure billing management. You may request a fresh link whenever needed.",
    opening: "Opening secure billing management…",
    openingNote: "Please keep this page open while we verify the single-use link.",
    invalid:
      "This billing-management link is invalid, expired, or already used. Request a new secure link below.",
    requestAnother: "Request another link",
    contact: "Contact support",
    home: "Return home",
    noAccount:
      "No AuroRatio login or password is required. Billing access is verified through your email and a single-use secure link.",
  },
  fr: {
    checkoutError: "Impossible d’ouvrir le Checkout sécurisé. Aucun débit n’a été effectué. Veuillez réessayer.",
    eyebrow: "Gestion sécurisée de la facturation",
    title: "Gérez votre abonnement",
    body:
      "Utilisez l’adresse email de facturation saisie lors du Checkout. Si un abonnement éligible existe, nous enverrons un lien temporaire et à usage unique vers le portail de facturation sécurisé.",
    optionsTitle: "Depuis le portail sécurisé, vous pouvez",
    options: [
      "Mettre à jour votre moyen de paiement.",
      "Consulter vos factures et informations de facturation.",
      "Annuler ou gérer le renouvellement lorsque l’option est disponible.",
    ],
    email: "Email de facturation",
    emailHint: "Utilisez exactement l’adresse email saisie lors du Checkout.",
    submit: "M’envoyer le lien sécurisé",
    submitting: "Envoi de la demande…",
    generic:
      "Demande reçue. Si un abonnement éligible existe pour cette adresse, un lien sécurisé de gestion sera envoyé sous peu.",
    deliveryHelp:
      "Vérifiez votre boîte de réception et les courriers indésirables. Pour des raisons de sécurité, la confirmation est identique qu’une adresse corresponde ou non à un abonnement.",
    error:
      "Nous n’avons pas pu transmettre votre demande. Aucune modification n’a été effectuée. Réessayez ou contactez le support.",
    portalReturn:
      "Vous êtes revenu du portail de facturation sécurisé. Vous pouvez demander un nouveau lien à tout moment.",
    opening: "Ouverture de la gestion sécurisée de la facturation…",
    openingNote: "Gardez cette page ouverte pendant la vérification du lien à usage unique.",
    invalid:
      "Ce lien de gestion est invalide, expiré ou déjà utilisé. Demandez un nouveau lien sécurisé ci-dessous.",
    requestAnother: "Demander un autre lien",
    contact: "Contacter le support",
    home: "Retour à l’accueil",
    noAccount:
      "Aucun identifiant ni mot de passe AuroRatio n’est requis. L’accès à la facturation est vérifié par email et par un lien sécurisé à usage unique.",
  },
} as const;

export default function ManageSubscription({ accessLink = false }: { accessLink?: boolean }) {
  const location = useLocation();
  const { language } = usePublicLanguage();
  const text = copy[language];
  const { beginCheckout, checkoutLoading } = usePublicCheckout(language, { error: text.checkoutError });
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [confirmation, setConfirmation] = useState(false);
  const [error, setError] = useState(() => {
    if (!accessLink) return "";
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    return fragment.get("token") ? "" : "invalid";
  });
  const exchangeStarted = useRef(false);

  useEffect(() => {
    if (!accessLink || exchangeStarted.current) return;
    exchangeStarted.current = true;

    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const token = fragment.get("token");
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    if (!token) return;

    void exchangeBillingManagementToken(token)
      .then((response) => {
        if (!isTrustedStripeHostedUrl(response.url, "billing.stripe.com")) {
          throw new Error("Unexpected Portal URL");
        }
        window.location.assign(response.url);
      })
      .catch(() => setError("invalid"));
  }, [accessLink]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError("");
    setConfirmation(false);
    try {
      await requestBillingManagementLink({ email, locale: language });
      setConfirmation(true);
      setEmail("");
    } catch {
      setError("request");
    } finally {
      setSubmitting(false);
    }
  };

  const portalReturned = new URLSearchParams(location.search).get("portal") === "return";

  return (
    <div className="manage-subscription">
      <style>{`
        .manage-subscription { min-height: 100vh; background: #0A0A08; color: #E8E4D8; font-family: 'DM Sans', sans-serif; }
        .manage-subscription__main { display: grid; place-items: center; min-height: 68vh; padding: 72px 24px 96px; }
        .manage-subscription__card { width: min(760px, 100%); border: 1px solid rgba(201,168,76,.24); background: #111109; padding: clamp(32px, 7vw, 64px); }
        .manage-subscription__eyebrow { margin: 0; color: #C9A84C; font-size: 11px; letter-spacing: .16em; text-transform: uppercase; }
        .manage-subscription h1 { margin: 14px 0 18px; font-family: 'Cormorant Garamond', serif; font-size: clamp(40px, 7vw, 60px); line-height: 1.05; }
        .manage-subscription__body, .manage-subscription__note { color: #B7B1A2; line-height: 1.75; }
        .manage-subscription__note { margin-top: 20px; color: #8A8670; font-size: 14px; }
        .manage-subscription__options { margin: 28px 0 0; padding: 22px 24px; border: 1px solid rgba(201,168,76,.16); background: rgba(201,168,76,.04); }
        .manage-subscription__options h2 { margin: 0 0 10px; font-family: 'Cormorant Garamond', serif; font-size: 24px; }
        .manage-subscription__options ul { margin: 0; padding-left: 20px; color: #B7B1A2; line-height: 1.7; }
        .manage-subscription__form { display: grid; gap: 10px; margin-top: 28px; }
        .manage-subscription__form label { font-size: 13px; color: #C8C3B5; }
        .manage-subscription__hint { margin: 0 0 4px; color: #8A8670; font-size: 12px; }
        .manage-subscription__form input { width: 100%; box-sizing: border-box; border: 1px solid rgba(201,168,76,.35); background: #0A0A08; color: #E8E4D8; padding: 13px 14px; font: inherit; }
        .manage-subscription__form button { border: 1px solid #C9A84C; background: #C9A84C; color: #0A0A08; padding: 13px 18px; font: inherit; font-weight: 600; cursor: pointer; }
        .manage-subscription__form button:disabled { cursor: wait; opacity: .65; }
        .manage-subscription__feedback { margin-top: 18px; padding: 16px; border-left: 2px solid #C9A84C; background: rgba(201,168,76,.05); color: #D5CEB9; line-height: 1.6; }
        .manage-subscription__feedback--error { border-left-color: #D97960; background: rgba(217,121,96,.06); color: #F0B7A7; }
        .manage-subscription__delivery-help { display: block; margin-top: 8px; color: #8A8670; font-size: 13px; }
        .manage-subscription__links { display: flex; flex-wrap: wrap; gap: 18px; margin-top: 28px; }
        .manage-subscription__links a { color: #E8C97A; }
        .manage-subscription a:focus-visible, .manage-subscription button:focus-visible, .manage-subscription input:focus-visible { outline: 2px solid #E8C97A; outline-offset: 4px; }
        @media (max-width: 620px) { .manage-subscription__main { padding: 48px 16px 72px; } .manage-subscription__card { padding: 28px 22px; } }
        @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
      `}</style>

      <PublicHeader onSubscribe={beginCheckout} checkoutLoading={checkoutLoading} />

      <main className="manage-subscription__main">
        <section className="manage-subscription__card">
          <p className="manage-subscription__eyebrow">{text.eyebrow}</p>
          <h1>{accessLink ? text.opening : text.title}</h1>

          {accessLink && !error && (
            <div className="manage-subscription__feedback" role="status">
              {text.opening}
              <span className="manage-subscription__delivery-help">{text.openingNote}</span>
            </div>
          )}

          {!accessLink && (
            <>
              <p className="manage-subscription__body">{text.body}</p>
              <section className="manage-subscription__options">
                <h2>{text.optionsTitle}</h2>
                <ul>{text.options.map((option) => <li key={option}>{option}</li>)}</ul>
              </section>

              {portalReturned && <p className="manage-subscription__feedback" role="status">{text.portalReturn}</p>}

              <form className="manage-subscription__form" onSubmit={handleSubmit}>
                <label htmlFor="billing-email">{text.email}</label>
                <p className="manage-subscription__hint" id="billing-email-hint">{text.emailHint}</p>
                <input
                  id="billing-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  aria-describedby="billing-email-hint"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
                <button type="submit" disabled={submitting}>
                  {submitting ? text.submitting : text.submit}
                </button>
              </form>

              {confirmation && (
                <div className="manage-subscription__feedback" role="status">
                  {text.generic}
                  <span className="manage-subscription__delivery-help">{text.deliveryHelp}</span>
                </div>
              )}
            </>
          )}

          {error && (
            <p className="manage-subscription__feedback manage-subscription__feedback--error" role="alert">
              {error === "invalid" ? text.invalid : text.error}
            </p>
          )}

          {!accessLink && <p className="manage-subscription__note">{text.noAccount}</p>}

          <div className="manage-subscription__links">
            {accessLink && <Link to="/manage-subscription">{text.requestAnother}</Link>}
            <a href={`mailto:${companyInformation.supportEmail}`}>{text.contact}</a>
            <Link to="/">{text.home}</Link>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
