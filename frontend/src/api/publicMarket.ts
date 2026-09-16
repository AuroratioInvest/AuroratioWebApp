import axios from "axios";
import type { BacktestData, MarketData } from "../types/market";

const publicMarketClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { "Content-Type": "application/json" },
});

export const getPublicMarketData = async () =>
  (await publicMarketClient.get<MarketData>("/market/data")).data;

export const getPublicBacktestData = async () =>
  (await publicMarketClient.get<BacktestData>("/market/backtest/results")).data;
