import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { isTrustedStripeHostedUrl } from "../src/utils/billingSecurity.ts";

const appSource = await readFile(
  new URL("../src/App.tsx", import.meta.url),
  "utf8"
);
const landingSource = await readFile(
  new URL("../src/pages/Landing.tsx", import.meta.url),
  "utf8"
);
const outcomeSource = await readFile(
  new URL("../src/pages/SubscriptionOutcome.tsx", import.meta.url),
  "utf8"
);
const manageSource = await readFile(
  new URL("../src/pages/ManageSubscription.tsx", import.meta.url),
  "utf8"
);
const billingApiSource = await readFile(
  new URL("../src/api/publicBilling.ts", import.meta.url),
  "utf8"
);
const checkoutHookSource = await readFile(
  new URL("../src/hooks/usePublicCheckout.ts", import.meta.url),
  "utf8"
);
const billingSecuritySource = await readFile(
  new URL("../src/utils/billingSecurity.ts", import.meta.url),
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
const publicCheckoutErrorSource = await readFile(
  new URL("../src/components/PublicCheckoutError.tsx", import.meta.url),
  "utf8"
);
const indexSource = await readFile(
  new URL("../index.html", import.meta.url),
  "utf8"
);
const phase5Source = await readFile(
  new URL("./phase5-public-messaging.test.ts", import.meta.url),
  "utf8"
);

test("Stripe-hosted redirect validation rejects lookalike and insecure URLs", () => {
  assert.equal(
    isTrustedStripeHostedUrl(
      "https://checkout.stripe.com/c/pay/session",
      "checkout.stripe.com"
    ),
    true
  );
  assert.equal(
    isTrustedStripeHostedUrl(
      "https://billing.stripe.com/p/session/secure",
      "billing.stripe.com"
    ),
    true
  );

  for (const value of [
    "http://checkout.stripe.com/c/pay/session",
    "https://checkout.stripe.com.attacker.test/session",
    "https://user@checkout.stripe.com/session",
    "javascript:alert(1)",
    "",
  ]) {
    assert.equal(
      isTrustedStripeHostedUrl(value, "checkout.stripe.com"),
      false,
      value
    );
  }
});

test("public Checkout uses a controlled plan and never submits a Stripe Price ID", () => {
  assert.match(billingApiSource, /\/public\/billing\/checkout-session/);
  assert.match(billingApiSource, /plan_code: input\.planCode/);
  assert.doesNotMatch(billingApiSource, /price_id|stripe_price_id/);
  assert.match(checkoutHookSource, /planCode: "monthly-signals"/);
  assert.match(checkoutHookSource, /createBillingRequestId/);
  assert.match(checkoutHookSource, /checkout\.stripe\.com/);
});

test("all public Subscribe controls share loading-safe Checkout behavior", () => {
  assert.match(checkoutHookSource, /if \(inFlight\.current\) return/);
  assert.match(checkoutHookSource, /inFlight\.current = true/);
  assert.match(checkoutHookSource, /setIsLoading\(true\)/);
  assert.match(landingSource, /onSubscribe=\{beginCheckout\}/);
  assert.ok(
    [...landingSource.matchAll(/onClick=\{beginCheckout\}/g)].length >= 3
  );
  assert.ok(
    [...landingSource.matchAll(/disabled=\{checkoutLoading\}/g)].length >= 3
  );
  assert.match(publicHeaderSource, /onClick=\{onSubscribe\}/);
  assert.match(publicHeaderSource, /disabled=\{checkoutLoading\}/);
  assert.match(publicCheckoutErrorSource, /role="alert"/);
  assert.match(landingSource, /We couldn’t open secure checkout/);
  assert.match(landingSource, /Impossible d’ouvrir le Checkout sécurisé/);
});

test("success and cancellation routes are honest and accountless", () => {
  assert.match(appSource, /path="\/subscription\/success"/);
  assert.match(appSource, /path="\/subscription\/cancelled"/);
  assert.match(outcomeSource, /Your payment has been submitted/);
  assert.match(outcomeSource, /If the subscription is confirmed, your private-channel access instructions will be sent to the email address used during checkout/);
  assert.match(outcomeSource, /Allow a few minutes for payment confirmation and email delivery/);
  assert.match(outcomeSource, /Si l’abonnement est confirmé, vos instructions d’accès au canal privé seront envoyées/);
  assert.match(outcomeSource, /This page does not confirm whether a payment was attempted/);
  assert.match(outcomeSource, /No AuroRatio account is required/);
  assert.match(outcomeSource, /manually (?:executing|placing) any trade/);
  assert.match(outcomeSource, /Your subscription was not completed/);
  assert.match(outcomeSource, /return to pricing and try again/);
  assert.match(outcomeSource, /searchParams\.delete\("session_id"\)/);
  assert.doesNotMatch(outcomeSource, /\{session_id\}/);
});

test("accountless billing management is generic, semantic, and replay-aware", () => {
  assert.match(appSource, /path="\/manage-subscription"/);
  assert.match(appSource, /path="\/manage-subscription\/access"/);
  assert.match(manageSource, /htmlFor="billing-email"/);
  assert.match(manageSource, /id="billing-email"/);
  assert.match(manageSource, /type="email"/);
  assert.match(manageSource, /role="status"/);
  assert.match(manageSource, /role="alert"/);
  assert.match(manageSource, /If an eligible subscription exists for that email/);
  assert.doesNotMatch(manageSource, /email not found/i);
  assert.match(manageSource, /window\.location\.hash\.slice\(1\)/);
  assert.match(manageSource, /window\.history\.replaceState/);
  assert.match(manageSource, /billing\.stripe\.com/);
  assert.match(footerSource, /to="\/manage-subscription"/);
});

test("Phase 6 preserves price, product boundaries, and Phase 5 accessibility", () => {
  assert.match(landingSource, /<sup>€<\/sup>14\.99/);
  assert.match(landingSource, /manually executing every trade/);
  assert.match(landingSource, /does not control or hold customer capital/);
  assert.match(landingSource, /Broker integrations/);
  assert.match(landingSource, /Optional automation/);
  assert.match(landingSource, /Advanced execution/);
  assert.match(landingSource, /Additional delivery channels/);
  assert.match(phase5Source, /prefers-reduced-motion: reduce/);
  assert.match(phase5Source, /aria-pressed/);
});

test("new public billing source remains provider-neutral and has no customer auth CTA", () => {
  const prohibitedProviderName = ["Tele", "gram"].join("");
  const prohibitedPattern = new RegExp(prohibitedProviderName, "i");
  const combined = [
    appSource,
    landingSource,
    outcomeSource,
    manageSource,
    billingApiSource,
    checkoutHookSource,
    billingSecuritySource,
    footerSource,
    publicHeaderSource,
    publicCheckoutErrorSource,
    indexSource,
  ].join("\n");

  assert.doesNotMatch(combined, prohibitedPattern);
  assert.doesNotMatch(
    `${outcomeSource}\n${manageSource}\n${footerSource}`,
    /to="\/(?:login|signup|dashboard|account)"/
  );
  assert.doesNotMatch(combined, /managed account|automatic trade execution/i);
});
