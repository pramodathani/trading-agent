import { useSyncExternalStore } from 'react';

import type { AgentEvent } from '../api/types';
import type { ConnectionState } from '../live/eventSocket';
import { eventSocket } from '../live/eventSocket';

/**
 * The events received live since the page opened.
 * @returns The events, oldest first.
 */
export function useLiveEvents(): AgentEvent[] {
  return useSyncExternalStore(
    (listener) => eventSocket.subscribe(listener),
    () => eventSocket.received(),
  );
}

/**
 * The live connection's state.
 * @returns "connecting", "open" or "closed".
 */
export function useConnectionState(): ConnectionState {
  return useSyncExternalStore(
    (listener) => eventSocket.subscribe(listener),
    () => eventSocket.connectionState(),
  );
}
