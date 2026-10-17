import type { UserRequest } from '../../api/types';
import { PermissionCard } from './PermissionCard';
import { PlanCard } from './PlanCard';
import { QuestionCard } from './QuestionCard';

/** What the dock shows. */
interface RequestDockProperties {
  requests: UserRequest[];
  onDone: () => void;
}

/**
 * The desk's waiting request, docked above the message box as Claude Code docks its prompts: permission requests first, because they lapse, then the oldest question or plan, with a count of the others.
 * @param properties The desk's pending requests, oldest first, and what to call after one is answered.
 * @returns The dock, or nothing when no request waits.
 */
export function RequestDock(properties: RequestDockProperties) {
  const waiting = [...properties.requests.filter((request) => request.kind === 'permission'), ...properties.requests.filter((request) => request.kind !== 'permission')];
  if (waiting.length === 0) {
    return null;
  }
  const request = waiting[0];
  let card = <QuestionCard key={request.request_id} request={request} onDone={properties.onDone} />;
  if (request.kind === 'plan') {
    card = <PlanCard key={request.request_id} request={request} onDone={properties.onDone} />;
  } else if (request.kind === 'permission') {
    card = <PermissionCard key={request.request_id} request={request} onDone={properties.onDone} />;
  }
  return (
    <div className="request-dock">
      {waiting.length > 1 && <div className="request-dock-count">1 of {waiting.length} waiting for you</div>}
      {card}
    </div>
  );
}
