import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getPlan,
  createCheckoutSession,
  validatePromoCode as validatePromoCodeApi,
} from "../api/stripe";
import client from "../api/client";
import sharedStyles from "../styles/shared-styles";

type Plan = {
  price?: number | string;
  amount?: number | string;
  currency?: string;
  interval?: string;
};

type UserStatus = {
  is_active?: boolean;
};

function normalizePrice(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 100 ? value / 100 : value;
  }

  if (typeof value === "string") {
    const parsed = Number(value.replace(",", "."));
    if (Number.isFinite(parsed)) return parsed > 100 ? parsed / 100 : parsed;
  }

  return 14.99;
}

function clearSession() {
  const language = localStorage.getItem("language");

  localStorage.removeItem("access_token");
  localStorage.removeItem("user_email");
  localStorage.removeItem("user_id");
  localStorage.removeItem("membership_level");
  localStorage.removeItem("skipped_onboarding");
  localStorage.removeItem("broker_connect_started");
  localStorage.removeItem("broker_connect_time");

  sessionStorage.removeItem("stripe_checkout_started");

  if (language) localStorage.setItem("language", language);
}

export default function Subscribe() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [promoCode, setPromoCode] = useState("");
  const [promoApplied, setPromoApplied] = useState(false);
  const [discount, setDiscount] = useState(0);
  const [promoError, setPromoError] = useState("");
  const [promoLoading, setPromoLoading] = useState(false);

  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);

  const returnedFromStripe =
    sessionStorage.getItem("stripe_checkout_started") === "true" ||
    params.get("checkout") === "success" ||
    params.get("success") === "true" ||
    params.has("session_id");

  useEffect(() => {
    const token = localStorage.getItem("access_token");

    if (!token) {
      navigate("/login", { replace: true });
      return;
    }

    let cancelled = false;

    const checkSubscription = async () => {
      setChecking(true);
      setError("");

      const maxAttempts = returnedFromStripe ? 15 : 1;

      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        try {
          if (returnedFromStripe) {
            setStatusMessage(`Confirming your payment... ${attempt}/${maxAttempts}`);
          }

          const authRes = await client.get<UserStatus>("/auth/me", {
            params: returnedFromStripe ? { refresh: Date.now() } : undefined,
          });

          if (cancelled) return;

          if (authRes.data.is_active) {
            sessionStorage.removeItem("stripe_checkout_started");
            queryClient.invalidateQueries();
            navigate("/onboarding", { replace: true });
            return;
          }
        } catch (err: any) {
          if (cancelled) return;

          if (err.response?.status === 401) {
            clearSession();
            queryClient.clear();
            navigate("/login", { replace: true });
            return;
          }
        }

        if (attempt < maxAttempts) {
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
      }

      if (!cancelled) {
        setChecking(false);
        setStatusMessage("");

        if (returnedFromStripe) {
          setError(
            "Payment was completed, but your subscription is not active yet. This usually means the Stripe webhook has not updated the account. You can retry the check or restart the process."
          );
        }
      }
    };

    checkSubscription();

    return () => {
      cancelled = true;
    };
  }, [navigate, queryClient, returnedFromStripe]);

  const { data: plan } = useQuery<Plan>({
    queryKey: ["plan"],
    queryFn: getPlan,
  });

  const symbols: Record<string, string> = {
    EUR: "€",
    CHF: "CHF ",
    USD: "$",
  };

  const rawPrice = plan?.price ?? plan?.amount;
  const basePrice = normalizePrice(rawPrice);
  const finalPrice = promoApplied ? basePrice * (1 - discount / 100) : basePrice;
  const currency = String(plan?.currency ?? "EUR").toUpperCase();
  const currencySymbol = symbols[currency] ?? `${currency} `;
  const formattedBasePrice = `${currencySymbol}${basePrice.toFixed(2)}`;
  const formattedFinalPrice = `${currencySymbol}${finalPrice.toFixed(2)}`;
  const period = plan?.interval || "month";

  const validatePromoCode = async () => {
    if (!promoCode.trim()) {
      setPromoError("Please enter a promo code.");
      return;
    }

    setPromoLoading(true);
    setPromoError("");

    try {
      const result = await validatePromoCodeApi(promoCode);

      setDiscount(Number(result.discount_percent || 0));
      setPromoApplied(true);
      setPromoCode(result.promo_code || promoCode.toUpperCase());
    } catch (err: any) {
      setPromoError(err.response?.data?.detail || "Invalid promo code.");
      setPromoApplied(false);
      setDiscount(0);
    } finally {
      setPromoLoading(false);
    }
  };

  const handleSubscribe = async () => {
    setLoading(true);
    setError("");

    try {
      const { url, already_active } = await createCheckoutSession(
        promoApplied ? promoCode : undefined
      );

      if (already_active) {
        navigate("/onboarding", { replace: true });
        return;
      }

      if (!url) {
        throw new Error("Missing Stripe checkout URL.");
      }

      sessionStorage.setItem("stripe_checkout_started", "true");
      window.location.href = url;
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
          err.response?.data?.message ||
          err.message ||
          "Could not start checkout. Please try again."
      );
      setLoading(false);
    }
  };

  const restartProcess = async () => {
    clearSession();
    queryClient.clear();
    window.location.href = "/";
  };

  const retrySubscriptionCheck = () => {
    window.location.href = "/subscribe?checkout=success";
  };

  if (checking) {
    return (
      <div className="page-wrapper subscribe-loading">
        <style>{sharedStyles}</style>
        <style>{`
          .subscribe-loading {
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--ink);
            color: var(--text-muted);
            font-family: 'DM Sans', sans-serif;
          }

          .loading-card {
            border: 1px solid var(--rule);
            background: var(--ink-2);
            border-radius: 10px;
            padding: 2rem;
            max-width: 460px;
            text-align: center;
          }

          .loading-title {
            font-family: 'Cormorant Garamond', serif;
            font-size: 2rem;
            color: var(--text);
            margin-bottom: .5rem;
          }
        `}</style>

        <div className="loading-card">
          <div className="loading-title">Checking subscription</div>
          <p>{statusMessage || "Checking your account status..."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-wrapper">
      <style>{sharedStyles}</style>
      <style>{`
        .subscribe-page {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }

        .subscribe-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          padding: 1.5rem 3rem;
          border-bottom: 1px solid var(--rule);
          background: rgba(10,10,8,0.82);
          backdrop-filter: blur(12px);
        }

        .wordmark {
          font-family: 'Cormorant Garamond', serif;
          font-size: 1.7rem;
          text-decoration: none;
          color: var(--text);
        }

        .wordmark span {
          color: var(--gold-light);
        }

        .restart-button {
          background: transparent;
          border: 1px solid var(--rule);
          color: var(--text-muted);
          border-radius: 5px;
          padding: .75rem 1rem;
          font-family: 'DM Sans', sans-serif;
          cursor: pointer;
          transition: all .2s;
        }

        .restart-button:hover {
          color: var(--gold-light);
          border-color: rgba(201,168,76,.45);
          background: rgba(201,168,76,.06);
        }

        .subscribe-container {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 3rem 1.5rem;
        }

        .subscribe-card {
          background: var(--ink-2);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 3rem;
          width: 100%;
          max-width: 560px;
          box-shadow: 0 24px 80px rgba(0,0,0,.35);
        }

        .subscribe-eyebrow {
          font-family: 'Syncopate', sans-serif;
          text-transform: uppercase;
          font-size: .7rem;
          letter-spacing: .18em;
          color: var(--gold-light);
          margin-bottom: .75rem;
          font-weight: 700;
        }

        .subscribe-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 2.7rem;
          font-weight: 400;
          line-height: 1.05;
          color: var(--text);
          margin: 0 0 .5rem;
        }

        .subscribe-subtitle {
          font-size: .95rem;
          color: var(--text-muted);
          margin-bottom: 2.5rem;
          line-height: 1.6;
        }

        .pricing-display {
          background: rgba(201,168,76,.05);
          border: 1px solid var(--rule);
          border-radius: 8px;
          padding: 2rem;
          margin-bottom: 2rem;
          text-align: center;
        }

        .price-amount {
          font-family: 'Cormorant Garamond', serif;
          font-size: 3.5rem;
          color: var(--text);
          font-weight: 300;
        }

        .price-amount.discounted {
          color: var(--gold);
        }

        .price-original {
          font-size: 1.5rem;
          color: var(--text-muted);
          text-decoration: line-through;
          margin-right: 1rem;
        }

        .price-period {
          color: var(--text-muted);
        }

        .discount-badge {
          display: inline-block;
          margin-top: 1rem;
          background: rgba(201,168,76,.12);
          border: 1px solid rgba(201,168,76,.35);
          color: var(--gold-light);
          border-radius: 999px;
          padding: .45rem .8rem;
          font-size: .75rem;
          text-transform: uppercase;
          letter-spacing: .08em;
        }

        .features-list {
          list-style: none;
          padding: 0;
          margin: 0 0 2rem;
          display: grid;
          gap: .85rem;
        }

        .features-list li {
          color: var(--text-muted);
          padding-left: 1.6rem;
          position: relative;
        }

        .features-list li::before {
          content: '✓';
          position: absolute;
          left: 0;
          color: var(--gold-light);
        }

        .promo-section {
          border-top: 1px solid var(--rule);
          padding-top: 1.5rem;
          margin-bottom: 1.5rem;
        }

        .promo-label {
          color: var(--text-muted);
          font-size: .85rem;
          margin-bottom: .75rem;
          text-transform: uppercase;
          letter-spacing: .08em;
        }

        .promo-input-group {
          display: flex;
          gap: .75rem;
        }

        .form-input {
          flex: 1;
          background: var(--ink);
          border: 1px solid var(--rule);
          border-radius: 5px;
          padding: .9rem 1rem;
          color: var(--text);
          font-family: 'DM Sans', sans-serif;
        }

        .form-input:focus {
          outline: none;
          border-color: var(--gold);
          box-shadow: 0 0 0 3px rgba(201,168,76,.1);
        }

        .apply-button {
          background: transparent;
          border: 1px solid var(--gold);
          color: var(--gold-light);
          padding: .875rem 1.2rem;
          border-radius: 5px;
          font-weight: 600;
          cursor: pointer;
          white-space: nowrap;
        }

        .subscribe-button {
          background: var(--gold);
          color: var(--ink);
          border: none;
          border-radius: 5px;
          padding: 1rem 2rem;
          font-family: 'DM Sans', sans-serif;
          font-weight: 700;
          font-size: 1rem;
          text-transform: uppercase;
          letter-spacing: .05em;
          cursor: pointer;
          transition: background .2s, opacity .2s;
          width: 100%;
        }

        .subscribe-button:hover:not(:disabled) {
          background: var(--gold-light);
        }

        .subscribe-button:disabled,
        .apply-button:disabled {
          opacity: .55;
          cursor: not-allowed;
        }

        .error-message,
        .success-message {
          border-radius: 5px;
          padding: .85rem 1rem;
          font-size: .88rem;
          line-height: 1.5;
          margin-bottom: 1rem;
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

        .pending-actions {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: .75rem;
          margin-bottom: 1rem;
        }

        .secondary-button {
          background: transparent;
          color: var(--text-muted);
          border: 1px solid var(--rule);
          border-radius: 5px;
          padding: .9rem 1rem;
          font-family: 'DM Sans', sans-serif;
          cursor: pointer;
        }

        .secondary-button:hover {
          color: var(--gold-light);
          border-color: rgba(201,168,76,.45);
        }

        .security-note {
          margin-top: 1.5rem;
          padding-top: 1.5rem;
          border-top: 1px solid var(--rule);
          font-size: .8rem;
          color: var(--text-muted);
          text-align: center;
          line-height: 1.5;
        }

        .security-note strong {
          color: var(--text);
        }

        @media (max-width: 700px) {
          .subscribe-header {
            padding: 1.2rem 1.5rem;
          }

          .subscribe-card {
            padding: 2rem;
          }

          .promo-input-group,
          .pending-actions {
            grid-template-columns: 1fr;
            display: grid;
          }

          .price-amount {
            font-size: 3rem;
          }
        }
      `}</style>

      <div className="subscribe-page">
        <header className="subscribe-header">
          <Link to="/subscribe" className="wordmark">
            <span>Auro</span>Ratio
          </Link>

          <button type="button" className="restart-button" onClick={restartProcess}>
            Restart from landing
          </button>
        </header>

        <main className="subscribe-container">
          <section className="subscribe-card">
            <p className="subscribe-eyebrow">Step 2 of 3</p>

            <h1 className="subscribe-title">Activate your access</h1>

            <p className="subscribe-subtitle">
              Subscribe first. After Stripe confirms your payment, you will continue to onboarding.
            </p>

            <div className="pricing-display">
              {promoApplied ? (
                <div>
                  <span className="price-original">{formattedBasePrice}</span>
                  <span className="price-amount discounted">{formattedFinalPrice}</span>
                </div>
              ) : (
                <div className="price-amount">{formattedBasePrice}</div>
              )}

              <div className="price-period">per {period}</div>

              {promoApplied && (
                <div className="discount-badge">{discount}% off applied</div>
              )}
            </div>

            <ul className="features-list">
              <li>Automated portfolio monitoring</li>
              <li>Broker connection after subscription</li>
              <li>Live dashboard with portfolio tracking</li>
              <li>Portfolio activity history</li>
              <li>Email alerts and notifications</li>
              <li>Priority support</li>
            </ul>

            {error && (
              <>
                <div className="error-message">{error}</div>

                {returnedFromStripe && (
                  <div className="pending-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={retrySubscriptionCheck}
                    >
                      Retry check
                    </button>

                    <button
                      type="button"
                      className="secondary-button"
                      onClick={restartProcess}
                    >
                      Restart
                    </button>
                  </div>
                )}
              </>
            )}

            <div className="promo-section">
              <div className="promo-label">Have a promo code?</div>

              <div className="promo-input-group">
                <input
                  type="text"
                  className="form-input"
                  placeholder="Enter promo code"
                  value={promoCode}
                  onChange={(event) => {
                    setPromoCode(event.target.value.toUpperCase());
                    setPromoApplied(false);
                    setDiscount(0);
                    setPromoError("");
                  }}
                  disabled={promoApplied}
                />

                <button
                  type="button"
                  className="apply-button"
                  onClick={validatePromoCode}
                  disabled={promoLoading || promoApplied || !promoCode.trim()}
                >
                  {promoApplied ? "Applied" : promoLoading ? "Checking..." : "Apply"}
                </button>
              </div>

              {promoError && (
                <div className="error-message" style={{ marginTop: ".75rem" }}>
                  {promoError}
                </div>
              )}

              {promoApplied && (
                <div className="success-message" style={{ marginTop: ".75rem" }}>
                  Promo code “{promoCode}” applied successfully.
                </div>
              )}
            </div>

            <button onClick={handleSubscribe} disabled={loading} className="subscribe-button">
              {loading ? "Redirecting to Stripe..." : `Subscribe - ${formattedFinalPrice}/${period}`}
            </button>

            <div className="security-note">
              <strong>Secure payment</strong>
              <br />
              Secured by Stripe. Your payment information never touches AuroRatio servers.
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}