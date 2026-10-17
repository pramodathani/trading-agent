import { useEffect, useState } from 'react';

/** What a picture thumbnail shows, and how it fetches the picture. */
interface PictureThumbnailProperties {
  fileName: string;
  loadKey: string;
  load: () => Promise<Blob>;
}

/**
 * A picture fetched with the access token and shown as a thumbnail that opens full size.
 * @param properties The picture's name, a key that changes when it is a different picture, and how to fetch it.
 * @returns The thumbnail, a loading line, or a line saying the picture is gone.
 */
export function PictureThumbnail(properties: PictureThumbnailProperties) {
  const [address, setAddress] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const load = properties.load;

  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    load()
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
  }, [properties.loadKey]);

  if (failed) {
    return <span className="attachment-document muted small">{properties.fileName} (the picture is no longer there)</span>;
  }
  if (address === null) {
    return <span className="attachment-picture loading muted small">Loading {properties.fileName}…</span>;
  }
  return (
    <a className="attachment-picture" href={address} target="_blank" rel="noreferrer" title={`${properties.fileName}: open full size`}>
      <img src={address} alt={properties.fileName} />
    </a>
  );
}
