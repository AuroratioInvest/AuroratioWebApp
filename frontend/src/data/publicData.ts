import type { BacktestData, MarketData } from "../types/market";

export const EMPTY_MARKET_DATA: MarketData = {
  metals: {
    gold: {
      symbol: "XAU",
      name: "Gold",
      priceUSD: 0,
      priceCHF: 0,
      priceEUR: 0,
      change24h: 0,
      changePercent: 0,
      performance: 0,
    },
    silver: {
      symbol: "XAG",
      name: "Silver",
      priceUSD: 0,
      priceCHF: 0,
      priceEUR: 0,
      change24h: 0,
      changePercent: 0,
      performance: 0,
    },
    platinum: {
      symbol: "XPT",
      name: "Platinum",
      priceUSD: 0,
      priceCHF: 0,
      priceEUR: 0,
      change24h: 0,
      changePercent: 0,
      performance: 0,
    },
    palladium: {
      symbol: "XPD",
      name: "Palladium",
      priceUSD: 0,
      priceCHF: 0,
      priceEUR: 0,
      change24h: 0,
      changePercent: 0,
      performance: 0,
    },
  },
  ratios: { AU_AG: 0, AU_PT: 0, AU_PD: 0 },
  signal: "HOLD",
  signalMetal: "",
};

export const EMPTY_BACKTEST_DATA: BacktestData = {
  finalValueCHF: 0,
  initialValueCHF: 0,
  modules: {
    goldSilver: {
      name: "Gold / Silver",
      finalValue: 0,
      cagr: 0,
      ounceMultiplier: 0,
      switches: 0,
    },
    goldPlatinum: {
      name: "Gold / Platinum",
      finalValue: 0,
      cagr: 0,
      ounceMultiplier: 0,
      switches: 0,
    },
    goldPalladium: {
      name: "Gold / Palladium",
      finalValue: 0,
      cagr: 0,
      ounceMultiplier: 0,
      switches: 0,
    },
  },
  totalSwitches: 0,
  timeframe: { start: "", end: "" },
};

export async function loadPublicResource<T>(
  loader: () => Promise<T>
): Promise<T | null> {
  try {
    return await loader();
  } catch {
    return null;
  }
}
