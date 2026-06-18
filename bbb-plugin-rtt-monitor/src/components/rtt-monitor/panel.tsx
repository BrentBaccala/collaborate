import * as React from 'react';
import { useEffect, useRef, useState } from 'react';
import { RttChart } from './chart';
import { ConnectionStatusRow, UserSeries, RttSample } from './types';

interface PanelProps {
  // Latest rows from the user_connectionStatusHistory subscription. The
  // server retains only the last `lastEntriesCap` samples per user-session
  // (default 20 ≈ 3.3 min at 10 s cadence); the panel keeps its own rolling
  // buffer so the window can grow past whatever the server retains while open.
  rows: ConnectionStatusRow[];
  windowMinutes: number;
  onClose: () => void;
}

// Tick interval for re-rendering "now" so the x-axis scrolls and points age
// out even when no new sample has arrived.
const REDRAW_MS = 2000;

export function RttPanel({ rows, windowMinutes, onClose }: PanelProps): React.ReactElement {
  // Rolling per-user buffer, keyed by userId. Survives across subscription
  // pushes; trimmed to the window on each render.
  const bufferRef = useRef<Map<string, UserSeries>>(new Map());
  const [now, setNow] = useState<number>(Date.now());

  // Merge incoming rows into the rolling buffer. Dedup by (userId, t) so the
  // same retained sample arriving in successive subscription pushes is not
  // double-counted.
  useEffect(() => {
    const buf = bufferRef.current;
    for (const r of rows) {
      if (r.networkRttInMs == null || r.networkRttInMs <= 0) continue;
      const t = Date.parse(r.statusUpdatedAt);
      if (Number.isNaN(t)) continue;
      let s = buf.get(r.userId);
      if (!s) {
        s = {
          userId: r.userId,
          name: r.user?.name || r.userId,
          role: r.user?.role || '',
          samples: [],
        };
        buf.set(r.userId, s);
      }
      // keep name/role fresh
      if (r.user?.name) s.name = r.user.name;
      if (r.user?.role) s.role = r.user.role;
      const sample: RttSample = { t, rtt: r.networkRttInMs };
      // Insert if we don't already have a sample at this exact timestamp.
      if (!s.samples.some((p) => p.t === t)) {
        s.samples.push(sample);
      }
    }
  }, [rows]);

  // Periodic redraw so the time axis advances and stale points drop off.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), REDRAW_MS);
    return () => clearInterval(id);
  }, []);

  const windowMs = windowMinutes * 60 * 1000;
  const windowStart = now - windowMs;

  // Build the sorted, trimmed series list for the chart. Drop users with no
  // in-window samples so the legend stays clean, but keep the buffer intact.
  const series: UserSeries[] = [];
  for (const s of Array.from(bufferRef.current.values())) {
    const inWindow = s.samples
      .filter((p) => p.t >= windowStart - 1000)
      .sort((a, b) => a.t - b.t);
    // prune very old samples from the buffer (keep a little slack past window)
    s.samples = s.samples.filter((p) => p.t >= windowStart - 60 * 1000);
    if (inWindow.length > 0) {
      series.push({ ...s, samples: inWindow });
    }
  }
  series.sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div
      style={{
        width: 640,
        padding: '10px 12px',
        boxSizing: 'border-box',
        fontFamily: 'sans-serif',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 6,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 700, color: '#222' }}>
          Connection RTT — last
          {' '}
          {windowMinutes}
          {' '}
          min
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            border: 'none',
            background: '#eee',
            borderRadius: 4,
            padding: '2px 9px',
            cursor: 'pointer',
            fontSize: 12,
          }}
        >
          ✕
        </button>
      </div>
      <RttChart
        series={series}
        windowStart={windowStart}
        now={now}
        width={616}
        height={300}
      />
    </div>
  );
}
