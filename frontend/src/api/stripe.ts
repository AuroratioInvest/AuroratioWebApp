import client from "./client";

export const createCheckoutSession = async (promoCode?: string) => {
  const { data } = await client.post("/stripe/create-checkout-session", {
    promo_code: promoCode?.trim() || null,
  });

  return data;
};

export const getPlan = async () => (await client.get("/stripe/plan")).data;

export const validatePromoCode = async (promoCode: string) => {
  const { data } = await client.post("/stripe/validate-promo-code", {
    promo_code: promoCode.trim(),
  });

  return data;
};