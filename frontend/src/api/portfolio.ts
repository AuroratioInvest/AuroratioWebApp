import client from "./client";

export const getSnapshots = async () =>
  (await client.get("/portfolio/snapshots")).data;

export const getPosition = async () =>
  (await client.get("/portfolio/position")).data;

export const getPositions = async () =>
  (await client.get("/portfolio/positions")).data;

export const getBalance = async () =>
  (await client.get("/portfolio/balance")).data;

export const getModulePositions = async () =>
  (await client.get("/portfolio/modules")).data;