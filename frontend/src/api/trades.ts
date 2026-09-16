import client from "./client";

export async function getTradeHistory(page = 1, limit = 50) {
  const res = await client.get("/trades/history", {
    params: { page, limit },
  });

  return res.data;
}