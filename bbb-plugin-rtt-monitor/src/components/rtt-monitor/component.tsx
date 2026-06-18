import * as React from 'react';
import { useEffect, useRef, useState } from 'react';
import * as ReactDOM from 'react-dom/client';
import {
  BbbPluginSdk,
  PluginApi,
  FloatingWindow,
  OptionsDropdownOption,
  OptionsDropdownSeparator,
} from 'bigbluebutton-html-plugin-sdk';

import { RttMonitorPluginProps, ConnectionStatusHistoryData } from './types';
import { RttPanel } from './panel';

// Moderator-scoped subscription on the connection-status history view. A
// moderator's GraphQL session auto-scopes these rows to ALL users in the
// meeting (Hasura select_permission on X-Hasura-ModeratorInMeeting); a viewer
// would see only their own rows. The `user` object relationship (→ v_user_ref)
// supplies name + role, both readable by role bbb_client.
const RTT_SUBSCRIPTION = `
  subscription ModeratorRttHistory {
    user_connectionStatusHistory(order_by: { statusUpdatedAt: asc }) {
      userId
      networkRttInMs
      status
      statusUpdatedAt
      user {
        name
        role
      }
    }
  }
`;

function RttMonitorPlugin({ pluginUuid }: RttMonitorPluginProps): React.ReactElement {
  BbbPluginSdk.initialize(pluginUuid);
  const pluginApi: PluginApi = BbbPluginSdk.getPluginApi(pluginUuid);

  const { data: currentUser } = pluginApi.useCurrentUser();
  const { data: settings } = pluginApi.usePluginSettings();
  const windowMinutes = Number((settings as any)?.windowMinutes) || 10;

  const isModerator = currentUser?.role === 'MODERATOR';

  // Run the subscription unconditionally (rules of hooks). The server-side
  // Hasura permission is what enforces scoping: a moderator's session returns
  // every meeting user's rows, a viewer's returns only their own. The UI is
  // separately gated on moderator role below, so a viewer never sees a panel —
  // but even if they did, they would only ever receive their own RTT.
  const subResult = pluginApi.useCustomSubscription<ConnectionStatusHistoryData>(
    RTT_SUBSCRIPTION,
  );
  const rows = (subResult?.data as any)?.user_connectionStatusHistory || [];

  const [open, setOpen] = useState(false);

  // The floating window content lives in its own React root (separate from
  // this plugin root), so we re-render it imperatively whenever the data,
  // window size, or open state change.
  const fwRootRef = useRef<ReactDOM.Root | null>(null);

  const renderPanel = (root: ReactDOM.Root) => {
    root.render(
      <RttPanel
        rows={rows}
        windowMinutes={windowMinutes}
        onClose={() => setOpen(false)}
      />,
    );
  };

  // Options-dropdown launcher (moderator only). Lives in the top-right
  // "..." options menu, next to the built-in connection-status entry.
  useEffect(() => {
    if (isModerator) {
      pluginApi.setOptionsDropdownItems([
        new OptionsDropdownSeparator(),
        new OptionsDropdownOption({
          label: open ? 'Hide connection RTT monitor' : 'Connection RTT monitor',
          icon: 'network',
          onClick: () => setOpen((v) => !v),
        }),
      ]);
    } else {
      pluginApi.setOptionsDropdownItems([]);
    }
    return () => {
      pluginApi.setOptionsDropdownItems([]);
    };
  }, [isModerator, open]);

  // Mount / unmount the floating window.
  useEffect(() => {
    if (isModerator && open) {
      pluginApi.setFloatingWindows([
        new FloatingWindow({
          top: 80,
          left: 80,
          movable: true,
          backgroundColor: '#ffffff',
          boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
          contentFunction: (element: HTMLElement) => {
            const root = ReactDOM.createRoot(element);
            fwRootRef.current = root;
            renderPanel(root);
            return root;
          },
        }),
      ]);
    } else {
      pluginApi.setFloatingWindows([]);
      fwRootRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isModerator, open]);

  // Push fresh data into the already-mounted floating window root whenever the
  // subscription updates (without tearing down the window).
  useEffect(() => {
    if (open && fwRootRef.current) {
      renderPanel(fwRootRef.current);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, windowMinutes]);

  return <></>;
}

export default RttMonitorPlugin;
