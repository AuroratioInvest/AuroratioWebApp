import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { companyInformation } from "../src/config/companyInformation.ts";

const landingSource = await readFile(
  new URL("../src/pages/Landing.tsx", import.meta.url),
  "utf8"
);
const platformSource = await readFile(
  new URL("../src/pages/Platform.tsx", import.meta.url),
  "utf8"
);
const performanceSource = await readFile(
  new URL("../src/pages/Performance.tsx", import.meta.url),
  "utf8"
);
const contactSource = await readFile(
  new URL("../src/pages/Contact.tsx", import.meta.url),
  "utf8"
);
const appSource = await readFile(
  new URL("../src/App.tsx", import.meta.url),
  "utf8"
);
const indexSource = await readFile(
  new URL("../index.html", import.meta.url),
  "utf8"
);
const footerSource = await readFile(
  new URL("../src/components/PublicFooter.tsx", import.meta.url),
  "utf8"
);
const publicHeaderSource = await readFile(
  new URL("../src/components/PublicHeader.tsx", import.meta.url),
  "utf8"
);
const companySource = await readFile(
  new URL("../src/config/companyInformation.ts", import.meta.url),
  "utf8"
);
const legalPlaceholderSource = await readFile(
  new URL("../src/pages/LegalPlaceholder.tsx", import.meta.url),
  "utf8"
);
const routePolicySource = await readFile(
  new URL("../src/routing/routePolicy.ts", import.meta.url),
  "utf8"
);
const motionSource = await readFile(
  new URL("../src/utils/motion.ts", import.meta.url),
  "utf8"
);
const subscriptionOutcomeSource = await readFile(
  new URL("../src/pages/SubscriptionOutcome.tsx", import.meta.url),
  "utf8"
);
const manageSubscriptionSource = await readFile(
  new URL("../src/pages/ManageSubscription.tsx", import.meta.url),
  "utf8"
);
const publicBillingApiSource = await readFile(
  new URL("../src/api/publicBilling.ts", import.meta.url),
  "utf8"
);
const publicCheckoutHookSource = await readFile(
  new URL("../src/hooks/usePublicCheckout.ts", import.meta.url),
  "utf8"
);
const metalsStripSource = await readFile(
  new URL("../src/components/MetalsStrip.tsx", import.meta.url),
  "utf8"
);
const billingSecuritySource = await readFile(
  new URL("../src/utils/billingSecurity.ts", import.meta.url),
  "utf8"
);

const prohibitedProviderName = ["Tele", "gram"].join("");
const publicSources = {
  "index.html": indexSource,
  "App.tsx": appSource,
  "Landing.tsx": landingSource,
  "Platform.tsx": platformSource,
  "Performance.tsx": performanceSource,
  "Contact.tsx": contactSource,
  "LegalPlaceholder.tsx": legalPlaceholderSource,
  "PublicFooter.tsx": footerSource,
  "PublicHeader.tsx": publicHeaderSource,
  "companyInformation.ts": companySource,
  "routePolicy.ts": routePolicySource,
  "motion.ts": motionSource,
  "SubscriptionOutcome.tsx": subscriptionOutcomeSource,
  "ManageSubscription.tsx": manageSubscriptionSource,
  "publicBilling.ts": publicBillingApiSource,
  "usePublicCheckout.ts": publicCheckoutHookSource,
  "billingSecurity.ts": billingSecuritySource,
};

test("public source and metadata do not expose the channel provider", () => {
  const prohibitedPattern = new RegExp(prohibitedProviderName, "i");

  for (const [fileName, source] of Object.entries(publicSources)) {
    assert.doesNotMatch(source, prohibitedPattern, fileName);
  }
});

test("public landing states the accountless private-channel signal journey", () => {
  for (const phrase of [
    "Professional signals · Private members channel",
    "Pay securely with Stripe",
    "Receive your invitation",
    "Join the members-only channel",
    "Receive signals",
    "Trade manually",
    "private members channel",
    "AuroRatio’s partner broker",
  ]) {
    assert.match(landingSource, new RegExp(phrase, "i"));
  }

  assert.match(
    landingSource,
    /Signaux professionnels · Canal privé réservé aux membres/
  );
  assert.match(landingSource, /invitation au canal privé/);
  assert.match(landingSource, /Tradez manuellement/);
});

test("public calls to action do not create accounts or enter legacy login", () => {
  assert.match(landingSource, /data-testid="pricing-subscribe"/);
  assert.match(landingSource, /beginCheckout/);
  assert.doesNotMatch(landingSource, /requestSubscriptionAccess/);
  assert.doesNotMatch(landingSource, /contact\?topic=subscription/);
  assert.doesNotMatch(landingSource, /navigate\("\/(?:login|signup|dashboard)"/);
  assert.doesNotMatch(landingSource, /legacyCustomerAppEnabled/);
});

test("roadmap features are retained and clearly unavailable today", () => {
  for (const phrase of [
    "Broker integrations",
    "Optional automation",
    "Advanced execution",
    "Coming Soon",
  ]) {
    assert.match(landingSource, new RegExp(phrase));
  }

  assert.match(platformSource, /Broker connectivity/);
  assert.match(platformSource, /La connectivité courtier/);
  assert.match(platformSource, /does not connect to brokerage accounts/);
  assert.match(platformSource, /Subscribers execute manually/);
  assert.match(platformSource, /Approved partner broker/);
  assert.match(platformSource, /ongoing technical support/);
  assert.match(platformSource, /assistance opening an account/);
  assert.match(platformSource, /Coming Soon/);
  for (const brokerName of [
    "Interactive Brokers",
    "eToro",
    "Swissquote",
    "Saxo Bank",
  ]) {
    assert.doesNotMatch(platformSource, new RegExp(brokerName));
  }
});

test("FAQ answers the required customer questions", () => {
  for (const question of [
    "Do I need a brokerage account?",
    "Does AuroRatio trade for me?",
    "How are signals delivered?",
    "Can I use any broker?",
    "What happens after payment?",
    "Can I cancel my subscription?",
    "Will more automation be available later?",
  ]) {
    assert.match(landingSource, new RegExp(question.replace("?", "\\?")));
  }
});

test("historical research is identified as hypothetical and under review", () => {
  assert.match(performanceSource, /Hypothetical backtest/);
  assert.match(performanceSource, /not subscriber results or actual trading performance/);
  assert.match(performanceSource, /methodology and source data remain under review/);
});

test("annotated public UI requirements remain represented", () => {
  assert.match(landingSource, /Pourquoi choisir la stratégie/);
  assert.match(landingSource, /AU \/ AG/);
  assert.match(landingSource, /AU \/ PT/);
  assert.match(landingSource, /AU \/ PD/);
  assert.match(landingSource, /33\.33%/);
  assert.match(landingSource, /Courtier partenaire/);
  assert.match(landingSource, /Vous devez utiliser le courtier partenaire d’AuroRatio/);
  assert.doesNotMatch(landingSource, /preferred broker|courtier de votre choix/i);
  assert.doesNotMatch(landingSource, /planFeature7/);
  assert.match(landingSource, /id="why-auroratio"/);
  assert.match(publicHeaderSource, /Pourquoi AuroRatio/);
  assert.match(publicHeaderSource, /\/#why-auroratio/);
  assert.match(metalsStripSource, /"EUR", "CHF", "USD"/);
  assert.match(performanceSource, /Groupe \/ Pot 1 · 33 % du portefeuille/);
  assert.doesNotMatch(performanceSource, /<DrawdownChart/);
  assert.doesNotMatch(performanceSource, /<OunceAccumulationChart/);
});

test("landing does not request backtest data and contact copy matches the product", () => {
  const landingRoute = appSource.slice(
    appSource.indexOf("function LandingRoute"),
    appSource.indexOf("function PlatformRoute")
  );

  assert.doesNotMatch(landingRoute, /useBacktestData/);
  assert.match(
    contactSource,
    /signal service, subscription launch, private-channel access/
  );
});

test("SEO metadata describes a private-channel signal subscription", () => {
  assert.match(indexSource, /Precious-Metals Trading Signals/);
  assert.match(indexSource, /trading-signal subscription service/);
  assert.match(indexSource, /private-channel delivery/);
  assert.match(indexSource, /subscriber-controlled brokerage accounts/);
  assert.doesNotMatch(indexSource, /automated trade execution/i);
  assert.doesNotMatch(
    indexSource,
    new RegExp(prohibitedProviderName, "i")
  );
});

test("company information is centralized without fictitious legal details", () => {
  assert.equal(companyInformation.brandName, "AuroRatio");
  assert.equal(companyInformation.contactEmail, "contact@auroratio.com");
  assert.equal(companyInformation.supportEmail, "support@auroratio.com");
  assert.equal(companyInformation.trademarkSymbol, "®");
  assert.equal(companyInformation.legalCompanyName, null);
  assert.equal(companyInformation.legalForm, null);
  assert.equal(companyInformation.registrationNumber, null);
  assert.equal(companyInformation.registeredOffice, null);

  assert.match(footerSource, /companyInformation\.legalCompanyName/);
  assert.match(footerSource, /companyInformation\.registrationNumber/);
  assert.match(footerSource, /field\.value !== null/);
  assert.doesNotMatch(footerSource, /Placeholder/);
  assert.match(companySource, /Legal company information to be completed/);
  assert.match(companySource, /Registration details to be completed/);
  assert.match(companySource, /Informations légales de la société à compléter/);
  assert.match(footerSource, /companyInformation\.brandName/);
  assert.match(footerSource, /companyInformation\.contactEmail/);
  assert.match(footerSource, /companyInformation\.supportEmail/);
  assert.match(footerSource, /companyInformation\.trademarkSymbol/);
  assert.match(contactSource, /companyInformation\.contactEmail/);
  assert.match(subscriptionOutcomeSource, /companyInformation\.supportEmail/);
  assert.match(manageSubscriptionSource, /companyInformation\.supportEmail/);
  assert.doesNotMatch(
    companySource,
    /AuroRatio\s+(?:Ltd|Limited|Inc|LLC|SAS|SARL|SA|GmbH|AG)\b/
  );
});

test("unresolved company rows are omitted without deleting future metadata", () => {
  for (const field of [
    "legalCompanyName",
    "legalForm",
    "registrationNumber",
    "registeredOffice",
  ]) {
    assert.match(companySource, new RegExp(`${field}: null`));
  }

  for (const completionNotice of [
    "Legal company information to be completed",
    "Legal form to be completed",
    "Registration details to be completed",
    "Registered office information to be completed",
    "Informations légales de la société à compléter",
    "Forme juridique à compléter",
    "Informations d’immatriculation à compléter",
    "Informations sur le siège social à compléter",
  ]) {
    assert.doesNotMatch(footerSource, new RegExp(completionNotice));
  }
});

test("professional footer includes product, legal, and company sections", () => {
  for (const label of [
    "Company",
    "Legal company name",
    "Legal form",
    "Company registration number",
    "Registered office",
    "Contact email",
    "Product",
    "Legal Notice",
    "Terms and Conditions",
    "Privacy Policy",
    "Cookie Policy",
    "Risk Disclaimer",
  ]) {
    assert.match(`${footerSource}\n${companySource}`, new RegExp(label));
  }

  assert.match(appSource, /"\/legal-notice"/);
  assert.match(appSource, /"\/cookie-policy"/);
  assert.match(routePolicySource, /"\/legal-notice"/);
  assert.match(routePolicySource, /"\/cookie-policy"/);
  assert.match(legalPlaceholderSource, /pending legal review/);
  assert.match(footerSource, /new Date\(\)\.getFullYear\(\)/);
});

test("footer risk disclaimer states subscriber responsibility in both languages", () => {
  assert.match(footerSource, /does not execute trades for subscribers/);
  assert.match(footerSource, /control brokerage accounts/);
  assert.match(footerSource, /past or hypothetical performance does not guarantee future results/);
  assert.match(footerSource, /making their own trading decisions/);

  assert.match(footerSource, /n’exécute pas d’ordres pour les abonnés/);
  assert.match(footerSource, /ne contrôle pas leurs comptes de courtage/);
  assert.match(footerSource, /performances passées ou hypothétiques ne garantissent pas les résultats futurs/);
  assert.match(footerSource, /ses propres décisions de trading/);
});

test("pricing and future roadmap positioning remain unchanged", () => {
  assert.match(landingSource, /<sup>€<\/sup>14\.99/);
  assert.match(landingSource, /Broker integrations/);
  assert.match(landingSource, /Optional automation/);
  assert.match(landingSource, /Advanced execution/);
  assert.match(landingSource, /Coming Soon/);
});

test("secondary-page navigation uses native links and accessible landmarks", () => {
  assert.match(publicHeaderSource, /import \{ Link, useLocation \} from "react-router-dom"/);
  assert.match(publicHeaderSource, /<nav className="public-site-nav" aria-label=\{text\.navigation\}>/);
  assert.match(publicHeaderSource, /<Link className="public-site-logo" to="\/"/);
  assert.match(publicHeaderSource, /to="\/platform"/);
  assert.match(publicHeaderSource, /to="\/performance"/);
  assert.match(publicHeaderSource, /to="\/#pricing"/);
  assert.match(publicHeaderSource, /to="\/contact"/);
  assert.match(publicHeaderSource, /role="group" aria-label=\{text\.language\}/);
  assert.match(publicHeaderSource, /aria-pressed=\{language === "en"\}/);
  assert.match(publicHeaderSource, /aria-pressed=\{language === "fr"\}/);
  assert.doesNotMatch(publicHeaderSource, /to="\/(?:login|signup|dashboard|subscribe)"/);

  for (const [source, activePage] of [
    [platformSource, "platform"],
    [performanceSource, "performance"],
    [contactSource, "contact"],
  ] as const) {
    assert.match(source, /import PublicHeader from "\.\.\/components\/PublicHeader"/);
    assert.match(source, /<PublicHeader/);
    assert.match(source, new RegExp(`activePage="${activePage}"`));
    assert.doesNotMatch(source, /<div className="nav-logo"[^>]*onClick/);
    for (const anchor of source.matchAll(/<a\b[^>]*>/g)) {
      assert.match(anchor[0], /\shref=/);
    }
  }
});

test("contact labels, controls, and feedback are programmatically associated", () => {
  const labelTargets = [
    ...contactSource.matchAll(/htmlFor="([^"]+)"/g),
  ].map((match) => match[1]);
  const controlIds = [
    ...contactSource.matchAll(/\bid="([^"]+)"/g),
  ].map((match) => match[1]);

  assert.deepEqual(labelTargets, [
    "contact-first-name",
    "contact-last-name",
    "contact-email",
    "contact-phone",
    "contact-message",
  ]);
  assert.equal(new Set(controlIds).size, controlIds.length);
  for (const target of labelTargets) {
    assert.equal(controlIds.filter((id) => id === target).length, 1);
  }

  assert.match(contactSource, /<PhoneInput\s+id="contact-phone"/);
  assert.match(contactSource, /className="error-message" role="alert"/);
  assert.match(contactSource, /className="success-message" role="status"/);
  assert.match(contactSource, /firstName: "First name"/);
  assert.match(contactSource, /firstName: "Prénom"/);
  assert.match(contactSource, /client\.post\("\/contact"/);
});

test("programmatic scrolling respects reduced-motion preference", () => {
  assert.match(motionSource, /prefers-reduced-motion: reduce/);
  assert.match(motionSource, /window\.matchMedia/);
  assert.match(motionSource, /return "auto"/);
  assert.match(motionSource, /return "smooth"/);
  assert.match(appSource, /scrollIntoView\(\{ behavior: getScrollBehavior\(\) \}\)/);
  assert.match(publicHeaderSource, /scrollTo\(\{ top: 0, behavior: getScrollBehavior\(\) \}\)/);
});

test("all animated public pages expose complete reduced-motion CSS", () => {
  for (const source of [landingSource, platformSource, performanceSource]) {
    const reducedMotionBlock = source.slice(
      source.indexOf("@media (prefers-reduced-motion: reduce)"),
      source.indexOf("`}</style>", source.indexOf("@media (prefers-reduced-motion: reduce)"))
    );

    assert.match(reducedMotionBlock, /animation: none !important/);
    assert.match(reducedMotionBlock, /transition: none !important/);
    assert.match(reducedMotionBlock, /\.reveal/);
    assert.match(reducedMotionBlock, /opacity: 1 !important/);
    assert.match(reducedMotionBlock, /transform: none !important/);
  }

  for (const source of [platformSource, performanceSource]) {
    const reducedMotionBlock = source.slice(
      source.indexOf("@media (prefers-reduced-motion: reduce)"),
      source.indexOf("`}</style>", source.indexOf("@media (prefers-reduced-motion: reduce)"))
    );
    assert.match(reducedMotionBlock, /\.hero-line/);
    assert.match(reducedMotionBlock, /\.hero-eyebrow/);
  }
});
