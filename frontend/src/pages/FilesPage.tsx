import { useEffect, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { EditableFile } from '../api/types';
import { DiffView } from '../components/DiffView';
import { Loadable } from '../components/Loadable';
import { usePolled } from '../hooks/usePolled';
import { formatter } from '../utilities/formatter';

const REFRESH_MILLISECONDS = 30000;

/** Which file is open in the editor. */
interface OpenFile {
  name: string;
  desk: string | null;
}

/**
 * Edit your own files, read and correct each desk's Memory.md, and accept or reject the desks' proposals.
 * @returns The page.
 */
export function FilesPage() {
  const files = usePolled(() => apiClient.files(), REFRESH_MILLISECONDS);
  const proposals = usePolled(() => apiClient.proposals(), REFRESH_MILLISECONDS);
  const [open, setOpen] = useState<OpenFile | null>(null);
  const [savedText, setSavedText] = useState('');
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDecided, setShowDecided] = useState(false);
  const [waitingToOpen, setWaitingToOpen] = useState<OpenFile | null>(null);
  const changed = draft !== savedText;

  useEffect(() => {
    if (open === null) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setMessage(null);
    setError(null);
    apiClient
      .fileText(open.name, open.desk)
      .then((document) => {
        if (!cancelled) {
          setSavedText(document.text);
          setDraft(document.text);
        }
      })
      .catch((failure: unknown) => {
        if (!cancelled) {
          setError(failure instanceof Error ? failure.message : String(failure));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    open,
  ]);

  /**
   * Opens a file, unless the open one has unsaved changes the user wants to keep.
   * @param file The file to open.
   */
  function openFile(file: EditableFile): void {
    const wanted = {
      name: file.name,
      desk: file.desk,
    };
    if (changed) {
      setWaitingToOpen(wanted);
      return;
    }
    setOpen(wanted);
  }

  /** Opens the file the user chose after agreeing to discard the unsaved changes. */
  function discardAndOpen(): void {
    setOpen(waitingToOpen);
    setWaitingToOpen(null);
  }

  /** Saves the open file. */
  async function save(): Promise<void> {
    if (open === null) {
      return;
    }
    setError(null);
    setMessage(null);
    try {
      await apiClient.saveFile(open.name, open.desk, draft);
      setSavedText(draft);
      setMessage(open.name === 'Memory.md' ? 'Saved. A checkpoint was taken first, so this edit can be undone on the Checkpoints page.' : 'Saved. The desks read it at their next turn.');
      files.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Accepts or rejects a proposal.
   * @param proposalId The proposal.
   * @param accept True to accept.
   */
  async function decide(proposalId: string, accept: boolean): Promise<void> {
    try {
      await apiClient.decideProposal(proposalId, accept);
      proposals.refresh();
      files.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  const pendingCount = (proposals.data?.proposals ?? []).filter((proposal) => proposal.status === 'pending').length;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Files</h1>
        <p className="muted">Your files tell every desk who you are, how to work and which limits apply. The desks cannot change them; they propose changes for you to accept.</p>
      </div>
      <div className="files-layout">
        <section className="panel file-list">
          <h2>Files</h2>
          <Loadable data={files.data} error={files.error}>
            {(document) => (
              <>
                {document.files.map((file) => (
                  <button
                    key={`${file.desk ?? 'shared'}-${file.name}`}
                    type="button"
                    className={open !== null && open.name === file.name && open.desk === file.desk ? 'list-item selected' : 'list-item'}
                    onClick={() => openFile(file)}
                  >
                    <span>
                      {file.name}
                      {file.desk !== null && <span className="muted"> · {file.desk}</span>}
                    </span>
                    <span className="muted small">{file.exists ? `${file.characters.toLocaleString('en-IN')} characters` : 'not created'}</span>
                  </button>
                ))}
              </>
            )}
          </Loadable>
        </section>
        <section className="panel editor">
          {open === null ? (
            <p className="muted">Choose a file to read or edit it.</p>
          ) : (
            <>
              <div className="editor-header">
                <h2>
                  {open.name}
                  {open.desk !== null && <span className="muted"> · {open.desk}</span>}
                </h2>
                <span className="spacer" />
                {changed && <span className="muted small">Unsaved changes</span>}
                <button type="button" disabled={!changed} onClick={() => setDraft(savedText)}>
                  Undo changes
                </button>
                <button className="primary" type="button" disabled={!changed} onClick={save}>
                  Save
                </button>
              </div>
              {waitingToOpen !== null && (
                <div className="notice">
                  <span>{open.name} has unsaved changes. Discard them and open {waitingToOpen.name}?</span>
                  <span className="button-row">
                    <button type="button" onClick={() => setWaitingToOpen(null)}>
                      Keep editing
                    </button>
                    <button className="danger" type="button" onClick={discardAndOpen}>
                      Discard
                    </button>
                  </span>
                </div>
              )}
              {open.name === 'TradingRules.md' && <p className="muted small">Before saving, the risk engine reads the limits from the new text. If it cannot, nothing is saved and you are told why.</p>}
              {loading ? <p className="muted">Loading…</p> : <textarea className="file-editor" spellCheck={false} value={draft} onChange={(change) => setDraft(change.target.value)} />}
              {message !== null && <p className="small">{message}</p>}
            </>
          )}
          {error !== null && <p className="error-text">{error}</p>}
        </section>
      </div>
      <section className="panel">
        <div className="editor-header">
          <h2>Proposals {pendingCount > 0 && <span className="count-badge">{pendingCount}</span>}</h2>
          <span className="spacer" />
          <label className="checkbox">
            <input type="checkbox" checked={showDecided} onChange={(change) => setShowDecided(change.target.checked)} />
            Show accepted and rejected
          </label>
        </div>
        <Loadable data={proposals.data} error={proposals.error}>
          {(document) => {
            const shown = document.proposals.filter((proposal) => showDecided || proposal.status === 'pending');
            return (
              <>
                {shown.length === 0 && <p className="muted">No proposals waiting.</p>}
                {shown.map((proposal) => (
                  <article key={proposal.proposal_id} className="proposal">
                    <div className="editor-header">
                      <strong>{proposal.file_name}</strong>
                      <span className="desk-chip">{proposal.desk}</span>
                      <span className="muted small">{formatter.dayTime(proposal.created_at)}</span>
                      <span className={`state-badge proposal-${proposal.status}`}>{proposal.status}</span>
                      <span className="spacer" />
                      {proposal.status === 'pending' && (
                        <>
                          <button type="button" onClick={() => decide(proposal.proposal_id, false)}>
                            Reject
                          </button>
                          <button className="primary" type="button" onClick={() => decide(proposal.proposal_id, true)}>
                            Accept
                          </button>
                        </>
                      )}
                    </div>
                    <p>{proposal.reason}</p>
                    {proposal.status === 'pending' && <DiffView difference={proposal.difference} />}
                  </article>
                ))}
              </>
            );
          }}
        </Loadable>
      </section>
    </div>
  );
}
