import { useCallback, useEffect, useRef, useState } from 'react';

/** What usePolled returns: the latest answer, the latest error, and a way to ask again at once that settles when the answer is shown. */
export interface PolledState<Answer> {
  data: Answer | null;
  error: string | null;
  refresh: () => Promise<void>;
}

/**
 * Asks for something now and again every few seconds while the component is shown.
 * @param load The request.
 * @param intervalMilliseconds How long to wait between requests.
 * @param key Asks again at once when this changes, such as the selected trader.
 * @returns The latest answer and error, and a refresh function.
 */
export function usePolled<Answer>(
  load: () => Promise<Answer>,
  intervalMilliseconds: number,
  key: string = '',
): PolledState<Answer> {
  const [data, setData] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadReference = useRef(load);
  const latestRequest = useRef(0);
  loadReference.current = load;

  const refresh = useCallback(async () => {
    latestRequest.current += 1;
    const request = latestRequest.current;
    try {
      const answer = await loadReference.current();
      if (request === latestRequest.current) {
        setData(answer);
        setError(null);
      }
    } catch (failure) {
      if (request === latestRequest.current) {
        setError(failure instanceof Error ? failure.message : String(failure));
      }
    }
  }, []);

  useEffect(() => {
    setData(null);
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, intervalMilliseconds);
    return () => {
      window.clearInterval(timer);
    };
  }, [
    refresh,
    intervalMilliseconds,
    key,
  ]);

  return {
    data,
    error,
    refresh,
  };
}
