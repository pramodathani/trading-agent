import { useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { CheckpointEntry } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';
import { useSelectedTrader } from '../layout/selectedTraderStore';
import { formatter } from '../utilities/formatter';

const REFRESH_MILLISECONDS = 30000;

/**
 * Snapshots of the chosen trader's own files, taken before every change, and a way to go back to one.
 * @returns The page.
 */
export function CheckpointsPage() {
  const traderName = useSelectedTrader();
  const checkpoints = usePolled(() => apiClient.checkpoints(traderName), REFRESH_MILLISECONDS, traderName);
  const [restoring, setRestoring] = useState<CheckpointEntry | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  /**
   * Restores a checkpoint.
   * @param checkpoint The checkpoint.
   */
  async function restore(checkpoint: CheckpointEntry): Promise<void> {
    const result = await apiClient.restoreCheckpoint(traderName, checkpoint.checkpoint_id);
    setNotice(`Restored ${result.restored}. To undo this, restore ${result.undo_checkpoint_id}, which holds the files as they were just before.`);
    checkpoints.refresh();
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Checkpoints of {traderName}</h1>
        <p className="muted">A snapshot of Memory.md, memory/, notes/ and the trader&apos;s own skills is taken before every change the trader, the curator or you make. Your own files are not part of it.</p>
      </div>
      {notice !== null && (
        <div className="notice" role="status">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      <section className="panel">
        <Loadable data={checkpoints.data} error={checkpoints.error}>
          {(document) => (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Taken</th>
                    <th>Why</th>
                    <th>Checkpoint</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {document.checkpoints.length === 0 && (
                    <tr>
                      <td colSpan={4} className="muted">
                        No checkpoints yet.
                      </td>
                    </tr>
                  )}
                  {document.checkpoints.map((checkpoint, index) => (
                    <tr key={checkpoint.checkpoint_id}>
                      <td className="small">{formatter.dayTime(checkpoint.created_at)}</td>
                      <td className="wrap">{checkpoint.reason}</td>
                      <td className="mono small">{checkpoint.checkpoint_id}</td>
                      <td>{index > 0 && <button type="button" onClick={() => setRestoring(checkpoint)}>Restore</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Loadable>
      </section>
      {restoring !== null && (
        <ConfirmDialog
          title={`Restore ${restoring.checkpoint_id}`}
          explanation={`The trader's own files go back to how they were at ${formatter.dayTime(restoring.created_at)} (${restoring.reason}). The current files are snapshotted first, so this can be undone.`}
          confirmLabel="Restore"
          onConfirm={() => restore(restoring)}
          onClose={() => setRestoring(null)}
        />
      )}
    </div>
  );
}
