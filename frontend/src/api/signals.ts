import client from "./client";

export const getState  = async () => (await client.get("/signals/state")).data;
export const getRatios = async () => (await client.get("/signals/ratios")).data;
export const getHistory = async () => (await client.get("/signals/history")).data;
export const getRatiosHistory = async () => (await client.get("/signals/ratios/history")).data;