import { Link } from "react-router-dom";
import {
  companyInformation,
  companyInformationCopy,
} from "../config/companyInformation";
import { usePublicLanguage, type PublicLanguage } from "../context/PublicLanguageContext";

const footerCopy = {
  en: {
    productHeading: "Product",
    howItWorks: "How it works",
    benefits: "Benefits",
    whyAuroRatio: "Why AuroRatio?",
    pricing: "Pricing",
    faq: "FAQ",
    contact: "Contact",
    manageSubscription: "Manage subscription",
    legalHeading: "Legal",
    legalNotice: "Legal Notice",
    terms: "Terms and Conditions",
    privacy: "Privacy Policy",
    cookies: "Cookie Policy",
    riskDisclaimerLink: "Risk Disclaimer",
    riskHeading: "Risk information",
    riskDisclaimer:
      "AuroRatio provides trading signals and market information. It does not execute trades for subscribers, control brokerage accounts, or manage subscriber assets. Trading involves risk, and past or hypothetical performance does not guarantee future results. Subscribers remain responsible for evaluating signals and making their own trading decisions.",
    rights: "All rights reserved.",
  },
  fr: {
    productHeading: "Produit",
    howItWorks: "Fonctionnement",
    benefits: "Avantages",
    whyAuroRatio: "Pourquoi AuroRatio ?",
    pricing: "Tarifs",
    faq: "FAQ",
    contact: "Contact",
    manageSubscription: "Gérer l’abonnement",
    legalHeading: "Informations juridiques",
    legalNotice: "Mentions légales",
    terms: "Conditions générales",
    privacy: "Politique de confidentialité",
    cookies: "Politique relative aux cookies",
    riskDisclaimerLink: "Avertissement sur les risques",
    riskHeading: "Information sur les risques",
    riskDisclaimer:
      "AuroRatio fournit des signaux de trading et des informations de marché. Il n’exécute pas d’ordres pour les abonnés, ne contrôle pas leurs comptes de courtage et ne gère pas leurs actifs. Le trading comporte des risques, et les performances passées ou hypothétiques ne garantissent pas les résultats futurs. Chaque abonné reste responsable de l’évaluation des signaux et de ses propres décisions de trading.",
    rights: "Tous droits réservés.",
  },
} as const satisfies Record<PublicLanguage, Record<string, string>>;

export default function PublicFooter() {
  const { language } = usePublicLanguage();
  const text = footerCopy[language];
  const companyText = companyInformationCopy[language];
  const currentYear = new Date().getFullYear();

  const companyFields: Array<{ label: string; value: string | null }> = [
    {
      label: companyText.legalCompanyNameLabel,
      value: companyInformation.legalCompanyName,
    },
    {
      label: companyText.legalFormLabel,
      value: companyInformation.legalForm,
    },
    {
      label: companyText.registrationNumberLabel,
      value: companyInformation.registrationNumber,
    },
    {
      label: companyText.registeredOfficeLabel,
      value: companyInformation.registeredOffice,
    },
  ];
  const verifiedCompanyFields = companyFields.filter(
    (field): field is { label: string; value: string } =>
      field.value !== null
  );

  return (
    <footer className="public-footer">
      <style>{`
        .public-footer {
          position: relative;
          z-index: 1;
          display: block;
          border-top: 1px solid rgba(201,168,76,.18);
          background: #080806;
          padding: 56px 40px 28px;
          color: #E8E4D8;
          font-family: 'DM Sans', sans-serif;
        }

        .public-footer__grid {
          display: grid;
          grid-template-columns: minmax(280px, 1.6fr) minmax(150px, .7fr) minmax(190px, .9fr);
          gap: 48px;
          max-width: 1180px;
          margin: 0 auto;
        }

        .public-footer__section {
          min-width: 0;
        }

        .public-footer__heading {
          margin: 0 0 20px;
          color: #C9A84C;
          font-family: 'DM Sans', sans-serif;
          font-size: 11px;
          font-weight: 600;
          letter-spacing: .14em;
          line-height: 1.4;
          text-transform: uppercase;
        }

        .public-footer__brand {
          margin: 0 0 20px;
          font-family: 'Cormorant Garamond', serif;
          font-size: 24px;
          letter-spacing: .08em;
          font-weight: 500;
          color: var(--gold, #C9A84C);
          letter-spacing: .12em;
          text-transform: uppercase;
          text-decoration: none;
          white-space: nowrap;
        }
        
        .public-footer__brand span { color: var(--text, #E8E4D8); }
        .public-footer__brand sup {
          margin-left: .14em;
          font-family: 'DM Sans', sans-serif;
          font-size: .38em;
          letter-spacing: 0;
          vertical-align: super;
        }

        .public-footer__company {
          display: grid;
          gap: 12px;
          margin: 0;
        }

        .public-footer__company-row {
          display: grid;
          grid-template-columns: minmax(130px, .8fr) minmax(150px, 1.2fr);
          gap: 16px;
        }

        .public-footer__company dt {
          color: #8A8670;
          font-size: 12px;
          line-height: 1.55;
        }

        .public-footer__company dd {
          margin: 0;
          color: #C8C3B5;
          font-size: 12px;
          line-height: 1.55;
        }

        .public-footer__company a,
        .public-footer__links a {
          color: #C8C3B5;
          text-decoration: none;
          transition: color .2s ease;
        }

        .public-footer__company a:hover,
        .public-footer__links a:hover {
          color: #E8C97A;
        }

        .public-footer__company a:focus-visible,
        .public-footer__links a:focus-visible {
          border-radius: 2px;
          outline: 2px solid #E8C97A;
          outline-offset: 4px;
        }

        .public-footer__links {
          display: grid;
          gap: 12px;
          margin: 0;
          padding: 0;
          list-style: none;
        }

        .public-footer__links a {
          font-size: 13px;
          line-height: 1.45;
        }

        .public-footer__risk {
          max-width: 1180px;
          margin: 42px auto 0;
          padding: 24px 0;
          border-top: 1px solid rgba(201,168,76,.18);
          border-bottom: 1px solid rgba(201,168,76,.18);
        }

        .public-footer__risk .public-footer__heading {
          margin-bottom: 10px;
        }

        .public-footer__risk p {
          max-width: 980px;
          margin: 0;
          color: #A5A08E;
          font-size: 12px;
          line-height: 1.75;
        }

        .public-footer__copyright {
          max-width: 1180px;
          margin: 0 auto;
          padding-top: 24px;
          color: #77735F;
          font-size: 11px;
          letter-spacing: .03em;
        }

        @media (max-width: 860px) {
          .public-footer {
            padding: 48px 24px 24px;
          }

          .public-footer__grid {
            grid-template-columns: 1fr 1fr;
            gap: 40px 28px;
          }

          .public-footer__section--company {
            grid-column: 1 / -1;
          }
        }

        @media (max-width: 560px) {
          .public-footer__grid {
            grid-template-columns: 1fr;
            gap: 36px;
          }

          .public-footer__section--company {
            grid-column: auto;
          }

          .public-footer__company-row {
            grid-template-columns: 1fr;
            gap: 3px;
          }
        }
      `}</style>

      <div className="public-footer__grid">
        <section
          className="public-footer__section public-footer__section--company"
          aria-labelledby="footer-company-heading"
        >
          <h2 className="public-footer__heading" id="footer-company-heading">
            {companyText.companyHeading}
          </h2>
          <p className="public-footer__brand">
            <span>{companyInformation.brandName_p1}</span>{companyInformation.brandName_p2}
            <sup aria-hidden="true">{companyInformation.trademarkSymbol}</sup>
          </p>
          <dl className="public-footer__company">
            {verifiedCompanyFields.map((field) => (
              <div className="public-footer__company-row" key={field.label}>
                <dt>{field.label}</dt>
                <dd>{field.value}</dd>
              </div>
            ))}
            <div className="public-footer__company-row">
              <dt>{companyText.contactEmailLabel}</dt>
              <dd>
                <a href={`mailto:${companyInformation.contactEmail}`}>
                  {companyInformation.contactEmail}
                </a>
              </dd>
            </div>
            <div className="public-footer__company-row">
              <dt>{companyText.supportEmailLabel}</dt>
              <dd>
                <a href={`mailto:${companyInformation.supportEmail}`}>
                  {companyInformation.supportEmail}
                </a>
              </dd>
            </div>
          </dl>
        </section>

        <nav
          className="public-footer__section"
          aria-labelledby="footer-product-heading"
        >
          <h2 className="public-footer__heading" id="footer-product-heading">
            {text.productHeading}
          </h2>
          <ul className="public-footer__links">
            <li><Link to="/#how">{text.howItWorks}</Link></li>
            <li><Link to="/#features">{text.benefits}</Link></li>
            <li><Link to="/#why-auroratio">{text.whyAuroRatio}</Link></li>
            <li><Link to="/#pricing">{text.pricing}</Link></li>
            <li><Link to="/#faq">{text.faq}</Link></li>
            <li><Link to="/contact">{text.contact}</Link></li>
            <li><Link to="/manage-subscription">{text.manageSubscription}</Link></li>
          </ul>
        </nav>

        <nav
          className="public-footer__section"
          aria-labelledby="footer-legal-heading"
        >
          <h2 className="public-footer__heading" id="footer-legal-heading">
            {text.legalHeading}
          </h2>
          <ul className="public-footer__links">
            <li><Link to="/legal-notice">{text.legalNotice}</Link></li>
            <li><Link to="/terms">{text.terms}</Link></li>
            <li><Link to="/privacy">{text.privacy}</Link></li>
            <li><Link to="/cookie-policy">{text.cookies}</Link></li>
            <li><Link to="/risk-disclosure">{text.riskDisclaimerLink}</Link></li>
          </ul>
        </nav>
      </div>

      <section className="public-footer__risk" aria-labelledby="footer-risk-heading">
        <h2 className="public-footer__heading" id="footer-risk-heading">
          {text.riskHeading}
        </h2>
        <p>{text.riskDisclaimer}</p>
      </section>

      <p className="public-footer__copyright">
        © {currentYear} {companyInformation.brandName}{companyInformation.trademarkSymbol}. {text.rights}
      </p>
    </footer>
  );
}
