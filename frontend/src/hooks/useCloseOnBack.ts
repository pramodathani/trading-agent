import { useEffect } from 'react';

import { backButton } from '../utilities/backButton';

type CloseHandler = () => void;

/**
 * Lets the back button close something while it is open.
 * @param open Whether it is open now.
 * @param close Closes it.
 */
export function useCloseOnBack(open: boolean, close: CloseHandler): void {
  useEffect(() => {
    if (!open) {
      return undefined;
    }
    return backButton.register(close);
  }, [
    open,
    close,
  ]);
}
