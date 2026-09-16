import { useEffect, useRef } from "react";
import { createChart, ColorType, LineSeries } from "lightweight-charts";

interface RatioChartProps2 {
  data: { time: string; value: number }[];
  buyThreshold:  number;
  sellThreshold: number;
  label: string;
  color: string;
}

export default function RatioChart2({
  data, buyThreshold, sellThreshold, label, color
}: RatioChartProps2) {
  const chartRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!chartRef.current || !data.length) return;

    const chart = createChart(chartRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor:  "#ffffff60",
      },
      grid: {
        vertLines: { color: "#ffffff10" },
        horzLines: { color: "#ffffff10" },
      },
      width:  chartRef.current.clientWidth,
      height: 200,
      timeScale: { borderColor: "#ffffff20" },
      rightPriceScale: { borderColor: "#ffffff20" },
    });

    // Ratio line
    const ratioSeries = chart.addSeries(LineSeries, {
      color,
      lineWidth: 2,
    });
    ratioSeries.setData(data);

    // Buy threshold line
    // const buyLine = chart.addSeries(LineSeries, {
    //   color:     "#ef4444",
    //   lineWidth: 1,
    //   lineStyle: LineStyle.Dashed,
    // });
    // buyLine.setData(data.map(d => ({ time: d.time, value: buyThreshold })));

    // Sell threshold line
    // const sellLine = chart.addSeries(LineSeries, {
    //   color:     "#22c55e",
    //   lineWidth: 1,
    //   lineStyle: LineStyle.Dashed,
    // });
    // sellLine.setData(data.map(d => ({ time: d.time, value: sellThreshold })));

    chart.timeScale().fitContent();
    chart.timeScale().applyOptions({
        lockVisibleTimeRangeOnResize: true,
        rightBarStaysOnScroll: true,
        fixLeftEdge: true,
        fixRightEdge: true,
    })

    const handleResize = () => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data, buyThreshold, sellThreshold, color]);

  return (
    <div>
      <p className="text-white/40 text-xs uppercase tracking-widest mb-2">
        {label}
      </p>
      <div ref={chartRef} className="w-full" />
    </div>
  );
}
