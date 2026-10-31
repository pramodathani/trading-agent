import { useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { AgentEvent, Attachment } from '../api/types';
import { appFiles } from '../utilities/appFiles';
import { formatter } from '../utilities/formatter';
import { platform } from '../utilities/platform';
import { SideCard } from './SideCard';

/** What the outputs card shows. */
interface OutputsCardProperties {
  traderName: string;
  events: AgentEvent[];
}

/** One file the trader sent, with when it sent it. */
interface Output {
  attachment: Attachment;
  sentAt: string;
}

/**
 * The pictures and documents the trader sent today, newest first; each opens in a new tab.
 * @param properties The trader and today's events.
 * @returns The card.
 */
export function OutputsCard(properties: OutputsCardProperties) {
  const outputs: Output[] = [];
  for (const event of properties.events) {
    if (event.kind !== 'message' || !Array.isArray(event.payload.attachments)) {
      continue;
    }
    for (const attachment of event.payload.attachments as Attachment[]) {
      outputs.push({
        attachment,
        sentAt: event.created_at,
      });
    }
  }
  outputs.reverse();
  return (
    <SideCard cardId="outputs" title="Outputs" aside={outputs.length}>
      {outputs.length === 0 && <p className="side-empty">Pictures and documents the trader sends appear here.</p>}
      <ul className="output-list">
        {outputs.map((output) => (
          <OutputRow key={output.attachment.attachment_id} traderName={properties.traderName} output={output} />
        ))}
      </ul>
    </SideCard>
  );
}

/**
 * One file: an icon, its name and the time it was sent.
 * @param properties The trader and the file.
 * @returns The row.
 */
function OutputRow(properties: { traderName: string; output: Output }) {
  const attachment = properties.output.attachment;
  const [error, setError] = useState<string | null>(null);

  /** Opens the file in a new tab. */
  async function open(): Promise<void> {
    setError(null);
    if (platform.isApp()) {
      try {
        const blob = await apiClient.attachmentFile(properties.traderName, attachment.attachment_id);
        await appFiles.open(blob, attachment.file_name);
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : String(failure));
      }
      return;
    }
    const opened = window.open('', '_blank');
    try {
      const blob = await apiClient.attachmentFile(properties.traderName, attachment.attachment_id);
      const address = URL.createObjectURL(blob);
      if (opened !== null) {
        opened.location.href = address;
      }
    } catch (failure) {
      opened?.close();
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  return (
    <li>
      <button type="button" className="output-row" onClick={() => void open()} title={error ?? `Open ${attachment.file_name}`}>
        {attachment.kind === 'image' ? <PictureIcon /> : <DocumentIcon />}
        <span className="output-name">{attachment.file_name}</span>
        <span className="muted">{formatter.time(properties.output.sentAt).slice(0, 5)}</span>
      </button>
      {error !== null && <span className="error-text small">{error}</span>}
    </li>
  );
}

/**
 * A small picture icon.
 * @returns The icon.
 */
function PictureIcon() {
  return (
    <svg className="output-icon" viewBox="0 0 16 16" aria-hidden="true">
      <rect x="2" y="3" width="12" height="10" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="6" cy="6.5" r="1.2" fill="currentColor" />
      <path d="M3 12l3.5-3.5 2.5 2.5 2-2 2 2" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * A small document icon.
 * @returns The icon.
 */
function DocumentIcon() {
  return (
    <svg className="output-icon" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M4 2h5l3 3v9H4z" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M9 2v3h3M6 8h4M6 10.5h4" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}
