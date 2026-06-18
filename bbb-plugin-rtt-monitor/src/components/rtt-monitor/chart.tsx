import * as React from 'react';
import {
  UserSeries, WARNING, DANGER, CRITICAL,
} from './types';

// One color per user. Same palette as ~/collaborate/scripts/rtt-plot so the
// in-meeting view and the after-the-fact report read consistently.
const COLORS = [
  '#c62828', '#1565c0', '#2e7d32', '#6a1b9a',
  '#e65100', '#00838f', '#5d4037', '#283593',
];

export function colorForIndex(i: number): string {
  return COLORS[i % COLORS.length];
}

interface ChartProps {
  series: UserSeries[];
  // Plot window: [windowStart, now] in epoch ms.
  windowStart: number;
  now: number;
  width: number;
  height: number;
}

// Fixed log-scale RTT bounds, matching rtt-plot's ax.set_ylim(10, 15000).
const Y_MIN = 10;
const Y_MAX = 15000;

function median(xs: number[]): number {
  if (xs.length === 0) return 0;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function fmtRtt(v: number): string {
  return v >= 1000 ? `${(v / 1000).toPrecision(2).replace(/\.?0+$/, '')} s` : `${Math.round(v)} ms`;
}

// Chart margins (px).
const M = {
  top: 12, right: 150, bottom: 28, left: 52,
};

export function RttChart({
  series, windowStart, now, width, height,
}: ChartProps): React.ReactElement {
  const plotW = Math.max(50, width - M.left - M.right);
  const plotH = Math.max(50, height - M.top - M.bottom);

  // x: linear in time across the window.
  const xScale = (t: number): number => {
    const span = Math.max(1, now - windowStart);
    return M.left + ((t - windowStart) / span) * plotW;
  };
  // y: log scale, clamped to [Y_MIN, Y_MAX], inverted (top = high RTT).
  const logMin = Math.log10(Y_MIN);
  const logMax = Math.log10(Y_MAX);
  const yScale = (v: number): number => {
    const clamped = Math.min(Y_MAX, Math.max(Y_MIN, v));
    const frac = (Math.log10(clamped) - logMin) / (logMax - logMin);
    return M.top + (1 - frac) * plotH;
  };

  // Y gridlines / labels at decade + threshold marks.
  const yTicks = [10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000];

  // X ticks anchored to wall-clock minute boundaries. Each tick is a fixed
  // clock time mapped through xScale, so as `now` advances the tick and its
  // label slide left together and eventually scroll off the left edge — rather
  // than ticks sitting at fixed pixel positions while only their labels change.
  const MIN_MS = 60_000;
  const spanMin = Math.max(1, (now - windowStart) / MIN_MS);
  const maxTicks = Math.max(2, Math.min(7, Math.floor(plotW / 80)));
  // Smallest "nice" minute step that keeps the tick count within maxTicks.
  const STEP_MIN = [1, 2, 5, 10, 15, 30, 60];
  const stepMs = (STEP_MIN.find((s) => spanMin / s <= maxTicks) ?? 60) * MIN_MS;
  // First minute boundary at/after windowStart, then step across to now.
  const firstTick = Math.ceil(windowStart / stepMs) * stepMs;
  const xTicks: number[] = [];
  for (let t = firstTick; t <= now; t += stepMs) xTicks.push(t);
  const fmtTime = (t: number): string => {
    const d = new Date(t);
    let h = d.getHours();
    const m = d.getMinutes().toString().padStart(2, '0');
    const ampm = h >= 12 ? 'PM' : 'AM';
    h %= 12;
    if (h === 0) h = 12;
    return `${h}:${m} ${ampm}`;
  };

  const thresholds = [
    { y: WARNING, label: 'warning 500 ms', color: '#f9a825' },
    { y: DANGER, label: 'danger 1 s', color: '#ef6c00' },
    { y: CRITICAL, label: 'critical 2 s', color: '#c62828' },
  ];

  return (
    <div style={{ fontFamily: 'sans-serif', color: '#222' }}>
      <svg width={width} height={height} style={{ background: '#fff' }}>
        {/* plot border */}
        <rect
          x={M.left}
          y={M.top}
          width={plotW}
          height={plotH}
          fill="none"
          stroke="#ccc"
          strokeWidth={1}
        />

        {/* y gridlines + labels */}
        {yTicks.map((v) => {
          const y = yScale(v);
          return (
            <g key={`y${v}`}>
              <line
                x1={M.left}
                x2={M.left + plotW}
                y1={y}
                y2={y}
                stroke="#eee"
                strokeWidth={1}
              />
              <text
                x={M.left - 6}
                y={y + 3}
                fontSize={9}
                textAnchor="end"
                fill="#666"
              >
                {fmtRtt(v)}
              </text>
            </g>
          );
        })}

        {/* threshold reference lines */}
        {thresholds.map((th) => {
          const y = yScale(th.y);
          return (
            <g key={th.label}>
              <line
                x1={M.left}
                x2={M.left + plotW}
                y1={y}
                y2={y}
                stroke={th.color}
                strokeWidth={0.9}
                strokeDasharray="4 3"
                opacity={0.8}
              />
              <text
                x={M.left + plotW + 4}
                y={y + 3}
                fontSize={8}
                fill={th.color}
              >
                {th.label}
              </text>
            </g>
          );
        })}

        {/* x ticks + labels */}
        {xTicks.map((t, i) => {
          const x = xScale(t);
          return (
            <g key={`x${i}`}>
              <line
                x1={x}
                x2={x}
                y1={M.top + plotH}
                y2={M.top + plotH + 4}
                stroke="#999"
                strokeWidth={1}
              />
              <text
                x={x}
                y={M.top + plotH + 16}
                fontSize={9}
                textAnchor="middle"
                fill="#666"
              >
                {fmtTime(t)}
              </text>
            </g>
          );
        })}

        {/* y axis title */}
        <text
          x={12}
          y={M.top + plotH / 2}
          fontSize={9}
          fill="#666"
          textAnchor="middle"
          transform={`rotate(-90 12 ${M.top + plotH / 2})`}
        >
          network RTT (log)
        </text>

        {/* scatter points, one color per user */}
        {series.map((s, idx) => {
          const color = colorForIndex(idx);
          return (
            <g key={s.userId}>
              {s.samples
                .filter((p) => p.t >= windowStart - 1000)
                .map((p, j) => (
                  <circle
                    // eslint-disable-next-line react/no-array-index-key
                    key={j}
                    cx={xScale(p.t)}
                    cy={yScale(p.rtt)}
                    r={2.6}
                    fill={color}
                    opacity={0.75}
                  />
                ))}
            </g>
          );
        })}
      </svg>

      {/* legend with name + median + peak, mirroring rtt-plot */}
      <div style={{ fontSize: 11, lineHeight: '1.5em', marginTop: 4 }}>
        {series.length === 0 && (
          <span style={{ color: '#888' }}>No RTT samples yet…</span>
        )}
        {series.map((s, idx) => {
          const ys = s.samples.map((p) => p.rtt);
          const med = median(ys);
          const peak = ys.length ? Math.max(...ys) : 0;
          return (
            <div key={s.userId} style={{ display: 'inline-block', marginRight: 14 }}>
              <span
                style={{
                  display: 'inline-block',
                  width: 9,
                  height: 9,
                  borderRadius: '50%',
                  background: colorForIndex(idx),
                  marginRight: 5,
                }}
              />
              <span style={{ fontWeight: 600 }}>{s.name}</span>
              {' '}
              <span style={{ color: '#666' }}>
                (n=
                {ys.length}
                , med=
                {fmtRtt(med)}
                , peak=
                {fmtRtt(peak)}
                )
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
