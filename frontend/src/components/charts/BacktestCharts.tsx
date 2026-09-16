import { useEffect, useRef } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  LineController,
  BarController,
} from "chart.js";
import type { ChartOptions } from "chart.js";
import type { BacktestData } from "../../types/market";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  LineController,
  BarController
);

const getBaseOptions = (): ChartOptions<"line"> => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: true,
      position: "top",
      labels: {
        color: "#8A8670",
        font: {
          family: "DM Sans",
          size: 11,
          weight: 400,
        },
        padding: 15,
        usePointStyle: true,
      },
    },
    title: {
      display: false,
    },
    tooltip: {
      backgroundColor: "rgba(10,10,8,0.95)",
      titleColor: "#E8C97A",
      bodyColor: "#E8E4D8",
      borderColor: "rgba(201,168,76,0.3)",
      borderWidth: 1,
      padding: 12,
      titleFont: {
        family: "DM Sans",
        size: 12,
        weight: 500,
      },
      bodyFont: {
        family: "DM Sans",
        size: 11,
      },
      displayColors: true,
      callbacks: {
        label: function (context) {
          let label = context.dataset.label || "";

          if (label) label += ": ";

          if (context.parsed.y !== null) {
            if (context.dataset.label?.includes("CHF")) {
              label +=
                "CHF " +
                context.parsed.y.toLocaleString("en-US", {
                  minimumFractionDigits: 0,
                  maximumFractionDigits: 0,
                });
            } else if (context.dataset.label?.includes("oz")) {
              label += context.parsed.y.toFixed(1) + " oz";
            } else if (context.dataset.label?.includes("%")) {
              label += context.parsed.y.toFixed(2) + "%";
            } else {
              label += context.parsed.y.toLocaleString();
            }
          }

          return label;
        },
      },
    },
  },
  scales: {
    x: {
      grid: {
        color: "rgba(201,168,76,0.05)",
      },
      ticks: {
        color: "#8A8670",
        font: {
          family: "DM Sans",
          size: 10,
        },
        maxRotation: 0,
      },
    },
    y: {
      grid: {
        color: "rgba(201,168,76,0.08)",
      },
      ticks: {
        color: "#8A8670",
        font: {
          family: "DM Sans",
          size: 10,
        },
        callback: function (value) {
          if (typeof value === "number") return value.toLocaleString();
          return value;
        },
      },
    },
  },
  interaction: {
    intersect: false,
    mode: "index",
  },
});

export function PortfolioGrowthChart({ backtestData }: { backtestData: BacktestData }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS<"line"> | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const startYear = Number(backtestData.timeframe.start) || 2000;
    const endYear = Number(backtestData.timeframe.end) || 2025;
    const years = Math.max(1, endYear - startYear);
    const labels = Array.from({ length: years + 1 }, (_, i) => (startYear + i).toString());

    const group1Values = labels.map((_, i) => {
      return 100000 * Math.pow(1 + backtestData.modules.goldSilver.cagr / 100, i);
    });

    const group2Values = labels.map((_, i) => {
      return 100000 * Math.pow(1 + backtestData.modules.goldPlatinum.cagr / 100, i);
    });

    const group3Values = labels.map((_, i) => {
      return 100000 * Math.pow(1 + backtestData.modules.goldPalladium.cagr / 100, i);
    });

    const portfolioValues = labels.map(
      (_, i) => group1Values[i] + group2Values[i] + group3Values[i]
    );

    const options = getBaseOptions();

    chartRef.current = new ChartJS(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Portfolio (CHF)",
            data: portfolioValues,
            borderColor: "#E8C97A",
            backgroundColor: "rgba(232,201,122,0.1)",
            borderWidth: 3,
            fill: true,
            tension: 0.1,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
        ],
      },
      options: {
        ...options,
        scales: {
          ...options.scales,
          y: {
            ...options.scales?.y,
            ticks: {
              ...options.scales?.y?.ticks,
              callback: function (value) {
                if (typeof value === "number") {
                  return "CHF " + (value / 1000).toFixed(0) + "K";
                }
                return value;
              },
            },
          },
        },
      },
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [backtestData]);

  return <canvas ref={canvasRef} style={{ maxHeight: "400px" }} />;
}

export function OunceAccumulationChart({ backtestData }: { backtestData: BacktestData }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS<"line"> | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const years = 25;
    const labels = Array.from({ length: years + 1 }, (_, i) => (2000 + i).toString());
    const initialUnits = 365;

    const accumulationData = labels.map((_, i) => {
      const progress = i / years;
      const group1Multiplier = backtestData.modules.goldSilver.ounceMultiplier;
      const group2Multiplier = backtestData.modules.goldPlatinum.ounceMultiplier;
      const group3Multiplier = backtestData.modules.goldPalladium.ounceMultiplier;
      const avgMultiplier = (group1Multiplier + group2Multiplier + group3Multiplier) / 3;

      return initialUnits * Math.pow(avgMultiplier, progress);
    });

    const options = getBaseOptions();

    chartRef.current = new ChartJS(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Portfolio Units",
            data: accumulationData,
            borderColor: "#C9A84C",
            backgroundColor: "rgba(201,168,76,0.15)",
            borderWidth: 3,
            fill: true,
            tension: 0.2,
            pointRadius: 0,
            pointHoverRadius: 5,
          },
        ],
      },
      options: {
        ...options,
        scales: {
          ...options.scales,
          y: {
            ...options.scales?.y,
            ticks: {
              ...options.scales?.y?.ticks,
              callback: function (value) {
                if (typeof value === "number") {
                  return value.toFixed(0);
                }
                return value;
              },
            },
          },
        },
      },
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [backtestData]);

  return <canvas ref={canvasRef} style={{ maxHeight: "350px" }} />;
}

export function DrawdownChart({ backtestData }: { backtestData: BacktestData }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS<"line"> | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const years = 25;
    const labels = Array.from({ length: years + 1 }, (_, i) => (2000 + i).toString());

    const drawdownData = labels.map((year) => {
      const y = parseInt(year);

      if (y === 2008) return -18;
      if (y === 2009) return -25;
      if (y === 2010) return -12;
      if (y === 2020) return -15;
      if (y === 2021) return -8;
      if (y === 2022) return -12;
      if (y === 2023) return -5;

      return Math.random() * -5;
    });

    const options = getBaseOptions();

    chartRef.current = new ChartJS(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Drawdown (%)",
            data: drawdownData,
            borderColor: "#EF5350",
            backgroundColor: "rgba(239,83,80,0.1)",
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
        ],
      },
      options: {
        ...options,
        scales: {
          ...options.scales,
          y: {
            ...options.scales?.y,
            max: 0,
            min: -30,
            ticks: {
              ...options.scales?.y?.ticks,
              callback: function (value) {
                return value + "%";
              },
            },
          },
        },
      },
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [backtestData]);

  return <canvas ref={canvasRef} style={{ maxHeight: "350px" }} />;
}

export function ModuleBreakdownChart({ backtestData }: { backtestData: BacktestData }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS<"bar"> | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const baseOptions = getBaseOptions() as ChartOptions<"bar">;

    chartRef.current = new ChartJS(ctx, {
      type: "bar",
      data: {
        labels: ["Module 1", "Module 2", "Module 3"],
        datasets: [
          {
            label: "Final Value (CHF)",
            data: [
              backtestData.modules.goldSilver.finalValue,
              backtestData.modules.goldPlatinum.finalValue,
              backtestData.modules.goldPalladium.finalValue,
            ],
            backgroundColor: [
              "rgba(232,201,122,0.8)",
              "rgba(155,181,194,0.8)",
              "rgba(176,158,199,0.8)",
            ],
            borderColor: ["#E8C97A", "#9BB5C2", "#B09EC7"],
            borderWidth: 2,
          },
        ],
      },
      options: {
        ...baseOptions,
        scales: {
          ...baseOptions.scales,
          y: {
            ...baseOptions.scales?.y,
            beginAtZero: true,
            ticks: {
              ...baseOptions.scales?.y?.ticks,
              callback: function (value) {
                if (typeof value === "number") {
                  return "CHF " + (value / 1000000).toFixed(1) + "M";
                }
                return value;
              },
            },
          },
        },
      },
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [backtestData]);

  return <canvas ref={canvasRef} style={{ maxHeight: "350px" }} />;
}
