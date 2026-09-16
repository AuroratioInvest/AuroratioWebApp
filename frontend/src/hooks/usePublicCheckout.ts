import { useCallback, useRef, useState } from "react";

import { createPublicCheckoutSession } from "../api/publicBilling";
import {
  createBillingRequestId,
  isTrustedStripeHostedUrl,
} from "../utils/billingSecurity";

type PublicLanguage = "en" | "fr";

type CheckoutMessages = {
  error: string;
};

export function usePublicCheckout(
  language: PublicLanguage,
  messages: CheckoutMessages
) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const requestId = useRef<string | null>(null);

  const beginCheckout = useCallback(async () => {
    if (inFlight.current) return;

    inFlight.current = true;
    setIsLoading(true);
    setError("");
    let redirectStarted = false;
    try {
      requestId.current ??= createBillingRequestId();
      const response = await createPublicCheckoutSession({
        planCode: "monthly-signals",
        locale: language,
        requestId: requestId.current,
      });
      if (
        !isTrustedStripeHostedUrl(
          response.url,
          "checkout.stripe.com"
        )
      ) {
        throw new Error("Unexpected Checkout URL");
      }
      window.location.assign(response.url);
      redirectStarted = true;
    } catch {
      setError(messages.error);
    } finally {
      if (!redirectStarted) {
        inFlight.current = false;
        setIsLoading(false);
      }
    }
  }, [language, messages.error]);

  return {
    beginCheckout,
    checkoutError: error,
    checkoutLoading: isLoading,
  };
}
