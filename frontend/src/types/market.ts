// src/types/market.ts

export interface MetalPrice {
  symbol: string;
  name: string;
  priceUSD: number;
  priceCHF: number;
  priceEUR: number;
  change24h: number;
  changePercent: number;
  performance: number;
}

export interface MarketData {
  metals: {
    gold: MetalPrice;
    silver: MetalPrice;
    platinum: MetalPrice;
    palladium: MetalPrice;
  };
  ratios: {
    AU_AG: number;
    AU_PT: number;
    AU_PD: number;
  };
  signal: 'BUY' | 'SELL' | 'HOLD';
  signalMetal: string;
}

export interface ModulePerformance {
  name: string;
  finalValue: number;
  cagr: number;
  ounceMultiplier: number;
  switches: number;
}

export interface BacktestData {
  finalValueCHF: number;
  initialValueCHF: number;
  modules: {
    goldSilver: ModulePerformance;
    goldPlatinum: ModulePerformance;
    goldPalladium: ModulePerformance;
  };
  totalSwitches: number;
  timeframe: {
    start: string;
    end: string;
  };
}