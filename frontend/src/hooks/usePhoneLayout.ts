import { useSyncExternalStore } from 'react';

import { phoneLayout } from '../utilities/phoneLayout';

/**
 * Whether the phone layout is in use, kept up to date as the window is resized.
 * @returns True on a narrow window.
 */
export function usePhoneLayout(): boolean {
  return useSyncExternalStore(
    (listener) => phoneLayout.subscribe(listener),
    () => phoneLayout.isActive(),
  );
}
