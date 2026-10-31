import { useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { Attachment } from '../api/types';
import { appFiles } from '../utilities/appFiles';
import { formatter } from '../utilities/formatter';
import { platform } from '../utilities/platform';
import { PictureThumbnail } from './PictureThumbnail';

/** What an attachment list shows. */
interface AttachmentListProperties {
  traderName: string;
  attachments: Attachment[];
  large?: boolean;
}

/**
 * The pictures and documents sent with a message: pictures as thumbnails, documents as labels that open the file.
 * @param properties The trader, its attachments, and whether pictures are shown large, as for a picture the trader sent.
 * @returns The list, or nothing when there are none.
 */
export function AttachmentList(properties: AttachmentListProperties) {
  if (properties.attachments.length === 0) {
    return null;
  }
  return (
    <div className={properties.large === true ? 'attachment-list large' : 'attachment-list'}>
      {properties.attachments.map((attachment) =>
        attachment.kind === 'image' ? (
          <AttachmentPicture key={attachment.attachment_id} traderName={properties.traderName} attachment={attachment} />
        ) : (
          <AttachmentDocument key={attachment.attachment_id} traderName={properties.traderName} attachment={attachment} />
        ),
      )}
    </div>
  );
}

/** What one attachment's view shows. */
interface AttachmentProperties {
  traderName: string;
  attachment: Attachment;
}

/**
 * One uploaded picture, shown as a thumbnail that opens full size.
 * @param properties The trader and the picture.
 * @returns The thumbnail.
 */
function AttachmentPicture(properties: AttachmentProperties) {
  const traderName = properties.traderName;
  const attachmentId = properties.attachment.attachment_id;
  return <PictureThumbnail fileName={properties.attachment.file_name} loadKey={`${traderName}/${attachmentId}`} load={() => apiClient.attachmentFile(traderName, attachmentId)} />;
}

/**
 * One document: its name, size and pages, opening the file in a new tab when pressed.
 * @param properties The trader and the document.
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
