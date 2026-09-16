import { useEffect, useRef } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  LineController
} from 'chart.js';
import type { ChartOptions } from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  LineController
);

const generateRatioData = (mean: number, rangeMin: number, rangeMax: number, volatility: number = 0.15) => {
  const years = 25;
  const dataPoints = years * 12;
  const data: number[] = [];
  let current = mean;

  for (let i = 0; i < dataPoints; i++) {
    const meanReversion = (mean - current) * 0.02;
    const randomChange = (Math.random() - 0.5) * volatility * mean;
    const spike = Math.random() > 0.98 ? (Math.random() - 0.5) * mean * 0.3 : 0;
    
    current = current + meanReversion + randomChange + spike;
    current = Math.max(rangeMin, Math.min(rangeMax, current));
    data.push(current);
  }
  
  return data;
};

const getBaseRatioOptions = (mean: number): ChartOptions<'line'> => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: false
    },
    title: {
      display: false
    },
    tooltip: {
      backgroundColor: 'rgba(10,10,8,0.95)',
      titleColor: '#E8C97A',
      bodyColor: '#E8E4D8',
      borderColor: 'rgba(201,168,76,0.3)',
      borderWidth: 1,
      padding: 12,
      titleFont: {
        family: 'DM Sans',
        size: 12,
        weight: 500
      },
      bodyFont: {
        family: 'DM Sans',
        size: 11
      },
      displayColors: false,
      callbacks: {
        title: function(context) {
          const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
          const index = context[0].dataIndex;
          const year = 2000 + Math.floor(index / 12);
          const month = monthNames[index % 12];
          return `${month} ${year}`;
        },
        label: function(context) {
          const value = context.parsed.y;
          if (value === null) return '';
          return 'Ratio: ' + value.toFixed(2);
        },
        afterLabel: function() {
          return `Mean: ${mean.toFixed(2)}`;
        }
      }
    }
  },
  scales: {
    x: {
      display: true,
      grid: {
        color: 'rgba(201,168,76,0.05)'
      },
      ticks: {
        color: '#8A8670',
        font: {
          family: 'DM Sans',
          size: 10
        },
        maxRotation: 0,
        autoSkip: true,
        maxTicksLimit: 10
      }
    },
    y: {
      grid: {
        color: 'rgba(201,168,76,0.08)'
      },
      ticks: {
        color: '#8A8670',
        font: {
          family: 'DM Sans',
          size: 10
        },
        callback: function(value) {
          if (typeof value === 'number') {
            return value.toFixed(1);
          }
          return value;
        }
      }
    }
  },
  interaction: {
    intersect: false,
    mode: 'index'
  }
});

export function GoldSilverRatioChart() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS<'line'> | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const ratioData = generateRatioData(67, 31, 124, 0.12);
    const labels = ratioData.map((_, i) => {
      const year = 2000 + Math.floor(i / 12);
      const month = i % 12;
      return month === 0 ? year.toString() : '';
    });

    const options = getBaseRatioOptions(67);

    chartRef.current = new ChartJS(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'AU/AG Ratio',
            data: ratioData,
            borderColor: '#E8C97A',
            backgroundColor: 'rgba(232,201,122,0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.2,
            pointRadius: 0,
            pointHoverRadius: 4
          }
        ]
      },
      options
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, []);

  // CRITICAL: Match BacktestCharts structure - use maxHeight on canvas, NOT container
  return <canvas ref={canvasRef} style={{ maxHeight: '350px' }} />;
}

export function GoldPlatinumRatioChart() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS<'line'> | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const ratioData = generateRatioData(1.42, 0.47, 2.87, 0.18);
    const labels = ratioData.map((_, i) => {
      const year = 2000 + Math.floor(i / 12);
      const month = i % 12;
      return month === 0 ? year.toString() : '';
    });

    const options = getBaseRatioOptions(1.42);

    chartRef.current = new ChartJS(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'AU/PT Ratio',
            data: ratioData,
            borderColor: '#9BB5C2',
            backgroundColor: 'rgba(155,181,194,0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.2,
            pointRadius: 0,
            pointHoverRadius: 4
          }
        ]
      },
      options
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, []);

  return <canvas ref={canvasRef} style={{ maxHeight: '350px' }} />;
}

export function GoldPalladiumRatioChart() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS<'line'> | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    if (chartRef.current) {
      chartRef.current.destroy();
      chartRef.current = null;
    }

    const ratioData = generateRatioData(2.14, 0.52, 5.29, 0.22);
    const labels = ratioData.map((_, i) => {
      const year = 2000 + Math.floor(i / 12);
      const month = i % 12;
      return month === 0 ? year.toString() : '';
    });

    const options = getBaseRatioOptions(2.14);

    chartRef.current = new ChartJS(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'AU/PD Ratio',
            data: ratioData,
            borderColor: '#B09EC7',
            backgroundColor: 'rgba(176,158,199,0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.2,
            pointRadius: 0,
            pointHoverRadius: 4
          }
        ]
      },
      options
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, []);

  return <canvas ref={canvasRef} style={{ maxHeight: '350px' }} />;
}