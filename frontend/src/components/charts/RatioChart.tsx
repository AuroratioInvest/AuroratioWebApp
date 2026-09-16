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
  Filler
} from 'chart.js';

import type {
  ChartDataset,
  ChartOptions
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface RatioChartProps {
  title: string;
  dates: string[];
  ratios: number[];
  buyThreshold?: number;
  sellThreshold?: number;
  color: string;
}

export default function RatioChart({ title, dates, ratios, buyThreshold, sellThreshold, color }: RatioChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<ChartJS | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;

    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    // Destroy existing chart
    if (chartRef.current) {
      chartRef.current.destroy();
    }

    const options: ChartOptions<'line'> = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        title: { display: false, text: title },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: 'rgba(17,17,9,0.95)',
          titleColor: '#E8E4D8',
          bodyColor: '#8A8670',
          borderColor: 'rgba(201,168,76,0.3)',
          borderWidth: 1,
          padding: 12,
          displayColors: false
        }
      },
      scales: {
        y: {
          ticks: { 
            color: '#8A8670',
            font: { family: 'DM Mono, monospace', size: 10 }
          },
          grid: { color: 'rgba(201,168,76,0.08)' },
          border: { color: 'rgba(201,168,76,0.18)' }
        },
        x: {
          ticks: { 
            color: '#8A8670',
            maxRotation: 0,
            autoSkipPadding: 50,
            font: { family: 'DM Mono, monospace', size: 10 }
          },
          grid: { color: 'rgba(201,168,76,0.05)' },
          border: { color: 'rgba(201,168,76,0.18)' }
        }
      },
      interaction: {
        mode: 'index',
        intersect: false
      }
    };

    const datasets: ChartDataset<'line', number[]>[] = [
      {
        label: 'Ratio',
        data: ratios,
        borderColor: color,
        backgroundColor: `${color}20`,
        borderWidth: 1.5,
        fill: true,
        tension: 0.1,
        pointRadius: 0,
        pointHoverRadius: 4
      }
    ];

    if (buyThreshold) {
      datasets.push({
        label: 'Buy Threshold',
        data: new Array(dates.length).fill(buyThreshold),
        borderColor: '#9E5A5A',
        borderWidth: 1,
        borderDash: [5, 5],
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 0
      });
    }

    if (sellThreshold) {
      datasets.push({
        label: 'Sell Threshold',
        data: new Array(dates.length).fill(sellThreshold),
        borderColor: '#5A9E72',
        borderWidth: 1,
        borderDash: [5, 5],
        fill: false,
        pointRadius: 0,
        pointHoverRadius: 0
      });
    }

    chartRef.current = new ChartJS(ctx, {
      type: 'line',
      data: {
        labels: dates,
        datasets
      },
      options
    });

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy();
      }
    };
  }, [title, dates, ratios, buyThreshold, sellThreshold, color]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <canvas ref={canvasRef} />
    </div>
  );
}
