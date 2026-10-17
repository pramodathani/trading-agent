import { useEffect, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { Attachment } from '../api/types';
import { formatter } from '../utilities/formatter';

/** What an attachment list shows. */
interface AttachmentListProperties {
  deskName: string;
  attachments: Attachment[];
}

/**
 * The pictures and documents sent with a message: pictures as thumbnails, documents as labels that open the file.
 * @param properties The desk and its attachments.
 * @returns The list, or nothing when there are none.
 */
export function AttachmentList(properties: AttachmentListProperties) {
  if (properties.attachments.length === 0) {
    return null;
  }
  return (
    <div className="attachment-list">
      {properties.attachments.map((attachment) =>
        attachment.kind === 'image' ? (
          <AttachmentPicture key={attachment.attachment_id} deskName={properties.deskName} attachment={attachment} />
        ) : (
          <AttachmentDocument key={attachment.attachment_id} deskName={properties.deskName} attachment={attachment} />
        ),
      )}
    </div>
  );
}

/** What one attachment's view shows. */
interface AttachmentProperties {
  deskName: string;
  attachment: Attachment;
}

/**
 * One picture, fetched with the access token and shown as a thumbnail that opens full size.
 * @param properties The desk and the picture.
 * @returns The thumbnail.
 */
function AttachmentPicture(properties: AttachmentProperties) {
  const [address, setAddress] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const deskName = properties.deskName;
  const attachmentId = properties.attachment.attachment_id;

  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    apiClient
      .attachmentFile(deskName, attachmentId)
      .then((blob) => {
        if (!cancelled) {
          created = URL.createObjectURL(blob);
          setAddress(created);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true);
        }
      });
    return () => {
      cancelled = true;
      if (created !== null) {
        URL.revokeObjectURL(created);
      }
    };
  }, [
    deskName,
    attachmentId,
  ]);

  if (failed) {
    return <span className="attachment-document muted small">{properties.attachment.file_name} (the picture is no longer there)</span>;
  }
  if (address === null) {
    return <span className="attachment-picture loading muted small">Loading {properties.attachment.file_name}…</span>;
  }
  return (
    <a className="attachment-picture" href={address} target="_blank" rel="noreferrer" title={`${properties.attachment.file_name}: open full size`}>
      <img src={address} alt={properties.attachment.file_name} />
    </a>
  );
}

/**
 * One document: its name, size and pages, opening the file in a new tab when pressed.
 * @param properties The desk and the document.
 * @returns The label.
 */
function AttachmentDocument(properties: AttachmentProperties) {
  const attachment = properties.attachment;
  const [error, setError] = useState<string | null>(null);
  const details = [
    formatter.fileSize(attachment.size_bytes),
  ];
  if (attachment.page_count !== null) {
    details.push(`${attachment.page_count} ${attachment.page_count === 1 ? 'page' : 'pages'}`);
  }
  if (attachment.text_characters === null) {
    details.push('text not readable');
  }

  /** Opens the document in a new tab. */
  async function open(): Promise<void> {
    setError(null);
    const opened = window.open('', '_blank');
    try {
      const blob = await apiClient.attachmentFile(properties.deskName, attachment.attachment_id);
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
    <button type="button" className="attachment-document" onClick={() => void open()} title={attachment.problem || `Open ${attachment.file_name}`}>
      <span className="attachment-badge" aria-hidden="true">
        {fileEnding(attachment.file_name)}
      </span>
      <span className="attachment-name">{attachment.file_name}</span>
      <span className="muted small">{details.join(' · ')}</span>
      {error !== null && <span className="error-text small">{error}</span>}
    </button>
  );
}

/**
 * A file's ending in capitals, for its badge.
 * @param fileName The file's name.
 * @returns Such as "PDF", or "FILE" when it has no ending.
 */
function fileEnding(fileName: string): string {
  const dot = fileName.lastIndexOf('.');
  if (dot < 0 || dot === fileName.length - 1) {
    return 'FILE';
  }
  return fileName.slice(dot + 1).toUpperCase();
}
