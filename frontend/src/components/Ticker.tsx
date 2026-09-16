import type { MarketData } from "../types/market";

interface TickerProps {
  marketData: MarketData;
}

export default function Ticker({ marketData }: TickerProps) {
  const { metals } = marketData;

  const tickerItems = [
    {
      label: "XAU/USD",
      price: `$${metals.gold.priceUSD.toFixed(2)}`,
      change: metals.gold.changePercent,
      isUp: metals.gold.changePercent >= 0,
    },
    {
      label: "XAU/CHF",
      price: `CHF ${metals.gold.priceCHF.toFixed(2)}`,
      change: metals.gold.changePercent,
      isUp: metals.gold.changePercent >= 0,
    },
    {
      label: "XAG/USD",
      price: `$${metals.silver.priceUSD.toFixed(2)}`,
      change: metals.silver.changePercent,
      isUp: metals.silver.changePercent >= 0,
    },
    {
      label: "XAG/CHF",
      price: `CHF ${metals.silver.priceCHF.toFixed(2)}`,
      change: metals.silver.changePercent,
      isUp: metals.silver.changePercent >= 0,
    },
    {
      label: "XPT/USD",
      price: `$${metals.platinum.priceUSD.toFixed(2)}`,
      change: metals.platinum.changePercent,
      isUp: metals.platinum.changePercent >= 0,
    },
    {
      label: "XPT/CHF",
      price: `CHF ${metals.platinum.priceCHF.toFixed(2)}`,
      change: metals.platinum.changePercent,
      isUp: metals.platinum.changePercent >= 0,
    },
    {
      label: "XPD/USD",
      price: `$${metals.palladium.priceUSD.toFixed(2)}`,
      change: metals.palladium.changePercent,
      isUp: metals.palladium.changePercent >= 0,
    },
    {
      label: "XPD/CHF",
      price: `CHF ${metals.palladium.priceCHF.toFixed(2)}`,
      change: metals.palladium.changePercent,
      isUp: metals.palladium.changePercent >= 0,
    },
  ];

  return (
    <div className="ticker-bar">
      <style>{`
        body {
          padding-top: 36px;
        }
        
        .ticker-bar {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          z-index: 120;
          background: #111109;
          border-bottom: 1px solid rgba(201,168,76,.18);
          overflow: hidden;
          height: 36px;
          display: flex;
          align-items: center;
        }

        .ticker-track {
          display: flex;
          width: max-content;
          animation: ticker 38s linear infinite;
          white-space: nowrap;
        }

        .ticker-loop {
          display: flex;
          flex-shrink: 0;
        }

        .ticker-item {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 0 32px;
          font-family: 'DM Sans', sans-serif;
          font-size: 11px;
          letter-spacing: 0.08em;
          border-right: 1px solid rgba(201,168,76,.18);
          height: 36px;
        }

        .ticker-label {
          color: #8A8670;
          text-transform: uppercase;
          letter-spacing: 0.12em;
        }

        .ticker-price {
          color: #C9A84C;
          font-weight: 500;
        }

        .ticker-change.up {
          color: #5A9E72;
        }

        .ticker-change.dn {
          color: #9E5A5A;
        }

        @keyframes ticker {
          0% {
            transform: translateX(0);
          }

          100% {
            transform: translateX(-50%);
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .ticker-track {
            animation: none;
          }
        }
      `}</style>

      <div className="ticker-track">
        {[...Array(2)].map((_, idx) => (
          <div key={idx} className="ticker-loop">
            {tickerItems.map((item) => (
              <div key={`${idx}-${item.label}`} className="ticker-item">
                <span className="ticker-label">{item.label}</span>
                <span className="ticker-price">{item.price}</span>
                <span className={`ticker-change ${item.isUp ? "up" : "dn"}`}>
                  {item.isUp ? "↑" : "↓"} {item.isUp ? "+" : ""}
                  {item.change.toFixed(2)}%
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}