import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { UsageSparkline } from '../components/UsageSparkline';

describe('<UsageSparkline />', () => {
  it('renders one bar per data point and flips them into chronological order', () => {
    // API returns newest-first; we expect the chart to render oldest -> newest.
    const { container } = render(
      <UsageSparkline
        data={[
          { day: '2026-05-03', request_count: 5 },
          { day: '2026-05-02', request_count: 0 },
          { day: '2026-05-01', request_count: 10 },
        ]}
      />,
    );
    const bars = container.querySelectorAll('[data-testid="sparkline-bar"]');
    expect(bars).toHaveLength(3);
    expect(bars[0]!.getAttribute('data-day')).toBe('2026-05-01');
    expect(bars[2]!.getAttribute('data-day')).toBe('2026-05-03');
  });

  it('renders the baseline only when there is no traffic yet', () => {
    const { container } = render(<UsageSparkline data={[]} />);
    expect(container.querySelectorAll('[data-testid="sparkline-bar"]')).toHaveLength(0);
    expect(container.querySelector('line')).not.toBeNull();
  });

  it('scales bar heights against the per-series max', () => {
    const { container } = render(
      <UsageSparkline
        data={[
          { day: '2026-05-02', request_count: 100 },
          { day: '2026-05-01', request_count: 50 },
        ]}
        height={100}
      />,
    );
    const bars = container.querySelectorAll<SVGRectElement>('[data-testid="sparkline-bar"]');
    const tallest = bars[1]!.getAttribute('height')!;
    const shorter = bars[0]!.getAttribute('height')!;
    expect(Number(tallest)).toBeGreaterThan(Number(shorter));
  });
});
