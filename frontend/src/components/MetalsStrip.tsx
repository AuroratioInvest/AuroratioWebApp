import { useState } from "react";
import type { MarketData } from "../types/market";

interface MetalsStripProps {
  marketData: MarketData;
}

export default function MetalsStrip({ marketData }: MetalsStripProps) {
  const { metals } = marketData;
  const [currency, setCurrency] = useState<"USD" | "EUR" | "CHF">("EUR");

  const formatPrice = (data: (typeof metals)[keyof typeof metals]) => {
    const price =
      currency === "USD"
        ? data.priceUSD
        : currency === "CHF"
          ? data.priceCHF
          : data.priceEUR;

    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(price);
  };

  const metalCards = [
    {
      symbol: "XAU",
      name: "Gold",
      data: metals.gold,
    },
    {
      symbol: "XAG",
      name: "Silver",
      data: metals.silver,
    },
    {
      symbol: "XPT",
      name: "Platinum",
      data: metals.platinum,
    },
    {
      symbol: "XPD",
      name: "Palladium",
      data: metals.palladium,
    },
  ];

  return (
    <div className="metals-strip-wrap">
      <style>{`
        .metals-strip-wrap {
          position: relative;
          z-index: 1;
          width: 100%;
          background: #111109;
          border-top: 1px solid rgba(201,168,76,.18);
          border-bottom: 1px solid rgba(201,168,76,.18);
          overflow-x: auto;
          scrollbar-width: none;
        }
        
        .metals-strip-wrap::-webkit-scrollbar {
          display: none;
        }

        .metals-strip {
          display: grid;
          grid-template-columns: repeat(4, minmax(180px, 1fr));
          min-width: 720px;
          background: #111109;
        }

        .metals-currency-picker {
          display: flex;
          justify-content: flex-end;
          gap: 4px;
          padding: 8px 24px;
          border-bottom: 1px solid rgba(201,168,76,.12);
        }

        .metals-currency-picker button {
          border: 1px solid rgba(201,168,76,.22);
          border-radius: 999px;
          background: transparent;
          color: #8A8670;
          padding: 4px 9px;
          font: 500 10px 'DM Sans', sans-serif;
          letter-spacing: .1em;
          cursor: pointer;
        }

        .metals-currency-picker button.active {
          background: rgba(201,168,76,.12);
          color: #E8C97A;
        }

        .metal-card {
          padding: 18px 24px;
          border-right: 1px solid rgba(201,168,76,.18);
          display: flex;
          flex-direction: column;
          gap: 4px;
          background: rgba(255,255,255,.01);
        }

        .metal-card:last-child {
          border-right: none;
        }

        .metal-symbol {
          font-family: 'DM Sans', sans-serif;
          font-size: 10px;
          letter-spacing: .16em;
          text-transform: uppercase;
          color: #8A8670;
        }

        .metal-name {
          font-family: 'Cormorant Garamond', serif;
          font-size: 20px;
          line-height: 1.15;
          font-weight: 500;
          color: #E8E4D8;
        }

        .metal-price {
          font-family: 'DM Sans', sans-serif;
          font-size: 17px;
          line-height: 1.2;
          font-weight: 500;
          color: #C9A84C;
        }

        .metal-change {
          font-family: 'DM Sans', sans-serif;
          font-size: 12px;
          line-height: 1.25;
        }

        .metal-change.pos {
          color: #5A9E72;
        }

        .metal-change.neg {
          color: #9E5A5A;
        }

        @media (max-width: 760px) {
          .metal-card {
            padding: 16px 20px;
          }
        }
      `}</style>

      <div className="metals-currency-picker" aria-label="Quote currency">
        {(["EUR", "CHF", "USD"] as const).map((option) => (
          <button
            type="button"
            className={currency === option ? "active" : ""}
            aria-pressed={currency === option}
            onClick={() => setCurrency(option)}
            key={option}
          >
            {option}
          </button>
        ))}
      </div>

      <div className="metals-strip">
        {metalCards.map((metal) => (
          <div key={metal.symbol} className="metal-card">
            <div className="metal-symbol">
              {metal.symbol} · {metal.name}
            </div>
            <div className="metal-name">{metal.name}</div>
            <div className="metal-price">{formatPrice(metal.data)}</div>
            <div className={`metal-change ${metal.data.changePercent >= 0 ? "pos" : "neg"}`}>
              {metal.data.changePercent >= 0 ? "↑" : "↓"}{" "}
              {metal.data.changePercent >= 0 ? "+" : ""}
              {metal.data.changePercent.toFixed(2)}% today
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
