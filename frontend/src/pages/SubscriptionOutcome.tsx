import { useEffect } from "react";
import { Link } from "react-router-dom";

import PublicFooter from "../components/PublicFooter";
import PublicHeader from "../components/PublicHeader";
import { companyInformation } from "../config/companyInformation";
import { usePublicLanguage } from "../context/PublicLanguageContext";
import { usePublicCheckout } from "../hooks/usePublicCheckout";

type Outcome = "success" | "cancelled";

const copy = {
  en: {
    checkoutError:
      "We couldn’t open secure checkout. Nothing has been charged. Please try again.",
    success: {
      eyebrow: "Payment submitted",
      title: "Your payment has been submitted",
      body:
        "Stripe has received your payment submission. If the subscription is confirmed, your private-channel access instructions will be sent to the email address used during checkout.",
      note:
        "No AuroRatio account is required. You remain responsible for reviewing every signal and manually placing any trade through AuroRatio’s partner broker.",
      steps: [
        ["done", "Payment submitted"],
      ],
      helpTitle: "Haven’t received your access instructions?",
      helpItems: [
        "Allow a few minutes for payment confirmation and email delivery.",
        "Check the inbox and spam folder for the email used during checkout.",
        "Contact support if nothing arrives after a reasonable delay.",
      ],
    },
    cancelled: {
      eyebrow: "Checkout closed",
      title: "Your subscription was not completed",
      body:
        "The checkout flow ended before your subscription was completed. You can safely return to pricing and try again.",
      note:
        "This page does not confirm whether a payment was attempted. Check your payment provider if you are uncertain, or contact support before retrying.",
      steps: [],
      helpTitle: "Need help completing checkout?",
      helpItems: [
        "Return to pricing and start a new secure checkout.",
        "Use the same email address you want to receive access instructions on.",
        "Contact support if checkout repeatedly fails.",
      ],
    },
    home: "Return home",
    pricing: "Return to pricing",
    contact: "Contact support",
    manage: "Manage subscription",
    retry: "Try checkout again",
  },
  fr: {
    checkoutError:
      "Impossible d’ouvrir le Checkout sécurisé. Aucun débit n’a été effectué. Veuillez réessayer.",
    success: {
      eyebrow: "Paiement transmis",
      title: "Votre paiement a été transmis",
      body:
        "Stripe a reçu votre paiement. Si l’abonnement est confirmé, vos instructions d’accès au canal privé seront envoyées à l’adresse email utilisée lors du Checkout.",
      note:
        "Aucun compte AuroRatio n’est requis. Vous restez responsable de l’évaluation de chaque signal et de l’exécution manuelle de tout trade auprès du courtier partenaire d’AuroRatio.",
      steps: [
        ["done", "Paiement transmis"],
      ],
      helpTitle: "Vous n’avez pas reçu vos instructions d’accès ?",
      helpItems: [
        "Patientez quelques minutes pour la confirmation du paiement et l’envoi de l’email.",
        "Vérifiez la boîte de réception et les courriers indésirables de l’adresse utilisée lors du Checkout.",
        "Contactez le support si rien n’arrive après un délai raisonnable.",
      ],
    },
    cancelled: {
      eyebrow: "Checkout fermé",
      title: "Votre abonnement n’a pas été finalisé",
      body:
        "Le Checkout s’est terminé avant la finalisation de votre abonnement. Vous pouvez revenir aux tarifs et réessayer en toute sécurité.",
      note:
        "Cette page ne confirme pas si une tentative de paiement a eu lieu. Vérifiez auprès de votre moyen de paiement en cas de doute, ou contactez le support avant de réessayer.",
      steps: [],
      helpTitle: "Besoin d’aide pour finaliser le Checkout ?",
      helpItems: [
        "Revenez aux tarifs et lancez un nouveau Checkout sécurisé.",
        "Utilisez l’adresse email sur laquelle vous souhaitez recevoir les instructions d’accès.",
        "Contactez le support si le Checkout échoue à plusieurs reprises.",
      ],
    },
    home: "Retour à l’accueil",
    pricing: "Retour aux tarifs",
    contact: "Contacter le support",
    manage: "Gérer l’abonnement",
    retry: "Réessayer le Checkout",
  },
} as const;

export default function SubscriptionOutcome({ outcome }: { outcome: Outcome }) {
  const { language } = usePublicLanguage();
  const text = copy[language];
  const outcomeText = text[outcome];
  const { beginCheckout, checkoutError, checkoutLoading } = usePublicCheckout(
    language,
    { error: text.checkoutError }
  );

  useEffect(() => {
    if (outcome !== "success") return;
    const currentUrl = new URL(window.location.href);
    if (!currentUrl.searchParams.has("session_id")) return;
    currentUrl.searchParams.delete("session_id");
    window.history.replaceState(
      null,
      "",
      `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`
    );
  }, [outcome]);

  return (
    <div className="subscription-outcome">
      <style>{`
        .subscription-outcome { min-height: 100vh; background: #0A0A08; color: #E8E4D8; font-family: 'DM Sans', sans-serif; }
        .subscription-outcome__main { display: grid; place-items: center; min-height: 68vh; padding: 72px 24px 96px; }
        .subscription-outcome__card { width: min(820px, 100%); border: 1px solid rgba(201,168,76,.24); background: #111109; padding: clamp(32px, 7vw, 68px); }
        .subscription-outcome__eyebrow { margin: 0; color: #C9A84C; font-size: 11px; letter-spacing: .16em; text-transform: uppercase; }
        .subscription-outcome h1 { max-width: 680px; margin: 18px 0; font-family: 'Cormorant Garamond', serif; font-size: clamp(38px, 7vw, 64px); line-height: 1.02; }
        .subscription-outcome__body, .subscription-outcome__note { max-width: 670px; color: #C8C3B5; line-height: 1.75; }
        .subscription-outcome__note { margin-top: 20px; color: #8A8670; font-size: 14px; }
        .subscription-outcome__steps { display: grid; gap: 12px; margin: 34px 0 0; padding: 0; list-style: none; }
        .subscription-outcome__step { display: grid; grid-template-columns: 28px 1fr; align-items: center; gap: 12px; padding: 14px 16px; border: 1px solid rgba(201,168,76,.16); background: rgba(255,255,255,.015); color: #A5A08E; }
        .subscription-outcome__step-marker { display: grid; place-items: center; width: 24px; height: 24px; border: 1px solid rgba(201,168,76,.35); border-radius: 50%; color: #C9A84C; font-size: 12px; }
        .subscription-outcome__step--done { color: #D8D1BD; }
        .subscription-outcome__step--current { border-color: rgba(201,168,76,.5); color: #E8E4D8; }
        .subscription-outcome__step--current .subscription-outcome__step-marker { background: #C9A84C; color: #0A0A08; }
        .subscription-outcome__help { margin-top: 34px; padding: 24px; border-left: 2px solid #C9A84C; background: rgba(201,168,76,.05); }
        .subscription-outcome__help h2 { margin: 0 0 12px; font-family: 'Cormorant Garamond', serif; font-size: 25px; }
        .subscription-outcome__help ul { margin: 0; padding-left: 20px; color: #B7B1A2; line-height: 1.7; }
        .subscription-outcome__actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 34px; }
        .subscription-outcome__actions a, .subscription-outcome__actions button { border: 1px solid #C9A84C; background: transparent; color: #E8E4D8; padding: 12px 18px; font: inherit; text-decoration: none; cursor: pointer; }
        .subscription-outcome__actions a:first-child, .subscription-outcome__actions button:first-child { background: #C9A84C; color: #0A0A08; }
        .subscription-outcome__actions button:disabled { cursor: wait; opacity: .65; }
        .subscription-outcome__error { margin-top: 18px; color: #F0B7A7; line-height: 1.6; }
        .subscription-outcome a:focus-visible, .subscription-outcome button:focus-visible { outline: 2px solid #E8C97A; outline-offset: 4px; }
        @media (max-width: 620px) { .subscription-outcome__main { padding: 48px 16px 72px; } .subscription-outcome__card { padding: 28px 22px; } }
        @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
      `}</style>

      <PublicHeader onSubscribe={beginCheckout} checkoutLoading={checkoutLoading} />

      <main className="subscription-outcome__main">
        <section className="subscription-outcome__card">
          <p className="subscription-outcome__eyebrow">{outcomeText.eyebrow}</p>
          <h1>{outcomeText.title}</h1>
          <p className="subscription-outcome__body">{outcomeText.body}</p>

          {outcomeText.steps.length > 0 && (
            <ol className="subscription-outcome__steps" aria-label={outcomeText.title}>
              {outcomeText.steps.map(([status, label], index) => (
                <li className={`subscription-outcome__step subscription-outcome__step--${status}`} key={label}>
                  <span className="subscription-outcome__step-marker" aria-hidden="true">
                    {status === "done" ? "✓" : index + 1}
                  </span>
                  <span>{label}</span>
                </li>
              ))}
            </ol>
          )}

          <p className="subscription-outcome__note">{outcomeText.note}</p>

          <aside className="subscription-outcome__help">
            <h2>{outcomeText.helpTitle}</h2>
            <ul>
              {outcomeText.helpItems.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </aside>

          {checkoutError && <p className="subscription-outcome__error" role="alert">{checkoutError}</p>}

          <div className="subscription-outcome__actions">
            {outcome === "cancelled" ? (
              <button type="button" onClick={beginCheckout} disabled={checkoutLoading}>
                {checkoutLoading ? "…" : text.retry}
              </button>
            ) : (
              <Link to="/">{text.home}</Link>
            )}
            <a href={`mailto:${companyInformation.supportEmail}`}>{text.contact}</a>
            {outcome === "success" && <Link to="/manage-subscription">{text.manage}</Link>}
            {outcome === "cancelled" && <Link to="/#pricing">{text.pricing}</Link>}
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
