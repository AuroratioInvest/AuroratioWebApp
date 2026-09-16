import { companyInformation } from "../config/companyInformation";
import { usePublicLanguage } from "../context/PublicLanguageContext";

interface PublicCheckoutErrorProps {
  message: string | null;
  showSupportLink?: boolean;
}

export default function PublicCheckoutError({
  message,
  showSupportLink = true,
}: PublicCheckoutErrorProps) {
  const { language } = usePublicLanguage();

  if (!message) return null;

  return (
    <div className="public-checkout-error" role="alert">
      <style>{`
        .public-checkout-error {
          padding: 1.25rem 1.5rem;
          background: rgba(10, 10, 8, 0.96);
          border-bottom: 1px solid rgba(201, 168, 76, 0.14);
        }
        .public-checkout-error__content {
          width: min(900px, 100%);
          margin: 0 auto;
          padding: 0.9rem 1.25rem;
          border: 1px solid rgba(201, 168, 76, 0.42);
          background: rgba(201, 168, 76, 0.055);
          color: #e8e4d8;
          text-align: center;
          font-size: 0.9rem;
          line-height: 1.55;
        }
        .public-checkout-error__link {
          display: inline-block;
          margin-left: 0.55rem;
          color: var(--gold-light, #e8c97a);
          font-weight: 500;
          text-underline-offset: 0.2em;
        }
        .public-checkout-error__link:focus-visible {
          outline: 2px solid var(--gold-light, #e8c97a);
          outline-offset: 3px;
        }
        @media (max-width: 620px) {
          .public-checkout-error {
            padding: 0.85rem 1rem;
          }
          .public-checkout-error__content {
            padding: 0.85rem 1rem;
            text-align: left;
          }
          .public-checkout-error__link {
            display: block;
            width: fit-content;
            margin: 0.45rem 0 0;
          }
        }
      `}</style>
      <div className="public-checkout-error__content">
        <span>{message}</span>
        {showSupportLink && (
          <a className="public-checkout-error__link" href={`mailto:${companyInformation.supportEmail}`}>
            {language === "fr" ? "Contacter le support" : "Contact support"}
          </a>
        )}
      </div>
    </div>
  );
}
