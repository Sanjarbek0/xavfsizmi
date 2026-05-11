interface SparklinePoint {
  day: string;
  request_count: number;
}

interface UsageSparklineProps {
  data: SparklinePoint[];
  width?: number;
  height?: number;
  className?: string;
}

/**
 * Tiny inline SVG bar chart. We deliberately avoid pulling in a charting library
 * — a 30-point per-key sparkline only needs a handful of `<rect>`s and one
 * `<path>` to be readable, and keeps the bundle lean.
 */
export function UsageSparkline({
  data,
  width = 240,
  height = 56,
  className,
}: UsageSparklineProps) {
  if (data.length === 0) {
    return (
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role="img"
        aria-label="usage sparkline empty"
        className={className}
      >
        <line
          x1={0}
          y1={height - 1}
          x2={width}
          y2={height - 1}
          stroke="currentColor"
          strokeOpacity={0.25}
        />
      </svg>
    );
  }

  // The API returns newest-first; flip to chronological so the bars read left→right.
  const series = [...data].reverse();
  const max = Math.max(1, ...series.map((p) => p.request_count));
  const slot = Math.max(1, Math.floor(width / series.length));
  const barWidth = Math.max(1, slot - 2);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role="img"
      aria-label={`usage sparkline, max ${max} requests/day`}
      className={className}
    >
      <line
        x1={0}
        y1={height - 1}
        x2={width}
        y2={height - 1}
        stroke="currentColor"
        strokeOpacity={0.2}
      />
      {series.map((point, idx) => {
        const ratio = point.request_count / max;
        const barHeight = Math.max(1, Math.round(ratio * (height - 2)));
        const x = idx * slot + (slot - barWidth) / 2;
        const y = height - 1 - barHeight;
        return (
          <rect
            key={point.day}
            data-testid="sparkline-bar"
            data-day={point.day}
            data-count={point.request_count}
            x={x}
            y={y}
            width={barWidth}
            height={barHeight}
            fill="currentColor"
            fillOpacity={0.7}
          />
        );
      })}
    </svg>
  );
}
