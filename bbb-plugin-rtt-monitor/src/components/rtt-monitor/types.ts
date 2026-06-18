export interface RttMonitorPluginProps {
  pluginUuid: string;
  pluginName: string;
}

// One row of the user_connectionStatusHistory GraphQL view, joined with the
// user_ref relationship for name/role.
export interface ConnectionStatusRow {
  userId: string;
  networkRttInMs: number | null;
  status: string | null;
  statusUpdatedAt: string; // ISO timestamp
  user?: {
    name: string | null;
    role: string | null;
  } | null;
}

export interface ConnectionStatusHistoryData {
  user_connectionStatusHistory: ConnectionStatusRow[];
}

// A single plotted RTT sample.
export interface RttSample {
  t: number; // epoch ms
  rtt: number; // ms
}

// Per-user accumulated rolling buffer of samples.
export interface UserSeries {
  userId: string;
  name: string;
  role: string;
  samples: RttSample[];
}

// BBB public.stats.rtt thresholds (ms). Matches settings.yml and rtt-plot.
export const WARNING = 500;
export const DANGER = 1000;
export const CRITICAL = 2000;
