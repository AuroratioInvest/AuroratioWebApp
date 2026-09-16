import axios from "axios";

type PublicLanguage = "en" | "fr";

const publicBillingClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export async function createPublicCheckoutSession(input: {
  planCode: string;
  locale: PublicLanguage;
  requestId: string;
}): Promise<{ url: string }> {
  const response = await publicBillingClient.post(
    "/public/billing/checkout-session",
    {
      plan_code: input.planCode,
      locale: input.locale,
      request_id: input.requestId,
    }
  );
  return response.data;
}

export async function requestBillingManagementLink(input: {
  email: string;
  locale: PublicLanguage;
}): Promise<{ message: string }> {
  const response = await publicBillingClient.post(
    "/public/billing/portal-link",
    input
  );
  return response.data;
}

export async function exchangeBillingManagementToken(
  token: string
): Promise<{ url: string }> {
  const response = await publicBillingClient.post(
    "/public/billing/portal-session",
    { token }
  );
  return response.data;
}
