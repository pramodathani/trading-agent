import { useEffect, useState } from 'react';

import type { ChatTurn, ToolStep } from '../utilities/chatTurnBuilder';
import { toolDescriber } from '../utilities/toolDescriber';

const THINKING_WORDS = [
  'Thinking',
  'Pondering',
  'Reading the tape',
  'Weighing it up',
  'Mulling it over',
  'Crunching the numbers',
  'Considering',
  'Sizing it up',
];
const TICK_MILLISECONDS = 1000;

/** What the progress line shows. */
interface TurnProgressProperties {
  turn: ChatTurn;
  streamingText: string;
}

/**
 * The live line under a running turn, as in Claude Code: an animated spark, shimmering words saying what the trader is doing, and the time it has taken so far.
 * @param properties The running turn and the text it has streamed so far.
 * @returns The line.
 */
export function TurnProgress(properties: TurnProgressProperties) {
  const turn = properties.turn;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MILLISECONDS);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const since = turn.startedAt ?? turn.receivedAt;
  const elapsedSeconds = Math.max(0, Math.floor((now - Date.parse(since)) / 1000));
  const running = runningTool(turn);
  let label = thinkingWord(turn.triggerId);
  let detail = '';
  if (!turn.started) {
    label = 'Waiting in the queue';
  } else if (running !== null) {
    label = toolDescriber.activity(running);
    detail = toolDescriber.detail(running);
  } else if (properties.streamingText.length > 0) {
    label = 'Writing the answer';
  }
  return (
    <div className="turn-progress" role="status" aria-live="polite">
      <span className="spark" aria-hidden="true" />
      <span className="shimmer">{label}…</span>
      {detail.length > 0 && <span className="turn-progress-detail mono">{detail}</span>}
      <span className="turn-progress-time">{elapsedText(elapsedSeconds)}</span>
    </div>
  );
}

/**
 * The tool call still waiting for its result, if any.
 * @param turn The turn.
 * @returns The newest tool call without a result, or null.
 */
function runningTool(turn: ChatTurn): ToolStep | null {
  for (let index = turn.steps.length - 1; index >= 0; index -= 1) {
    const step = turn.steps[index];
    if (step.type === 'tool') {
      return step.resultText === null ? step : null;
    }
  }
  return null;
}

/**
 * A word for thinking, the same one for the whole turn.
 * @param triggerId The turn's trigger id.
 * @returns One of the thinking words.
 */
function thinkingWord(triggerId: string): string {
  let total = 0;
  for (const character of triggerId) {
    total += character.charCodeAt(0);
  }
  return THINKING_WORDS[total % THINKING_WORDS.length];
}

/**
 * A duration the way Claude Code shows it.
 * @param seconds The duration in seconds.
 * @returns Such as "12s" or "2m 17s".
 */
export function elapsedText(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
