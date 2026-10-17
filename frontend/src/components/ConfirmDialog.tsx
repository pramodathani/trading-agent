import { type FormEvent, useState } from 'react';

/** What a confirmation dialog shows and asks for. */
export interface ConfirmDialogProperties {
  title: string;
  explanation: string;
  confirmLabel: string;
  requiredWord?: string;
  onConfirm: (reason: string) => Promise<void>;
  onClose: () => void;
}

/**
 * A dialog that asks for a reason, and optionally a typed word, before a risky action.
 * @param properties What to show and what to do on confirmation.
 * @returns The dialog.
 */
export function ConfirmDialog(properties: ConfirmDialogProperties) {
  const [reason, setReason] = useState('');
  const [typedWord, setTypedWord] = useState('');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wordMatches = properties.requiredWord === undefined || typedWord === properties.requiredWord;
  const ready = reason.trim().length > 0 && wordMatches && !working;

  /**
   * Runs the action.
   * @param event The form's submit event.
   */
  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!ready) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      await properties.onConfirm(reason.trim());
      properties.onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      setWorking(false);
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onClick={properties.onClose}>
      <form
        className="dialog panel"
        role="dialog"
        aria-modal="true"
        aria-label={properties.title}
        onClick={(click) => click.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <h2>{properties.title}</h2>
        <p>{properties.explanation}</p>
        <label className="field">
          <span>Reason, for the journal</span>
          <input autoFocus value={reason} onChange={(change) => setReason(change.target.value)} />
        </label>
        {properties.requiredWord !== undefined && (
          <label className="field">
            <span>
              Type <strong>{properties.requiredWord}</strong> to confirm
            </span>
            <input value={typedWord} onChange={(change) => setTypedWord(change.target.value)} />
          </label>
        )}
        {error !== null && <p className="error-text">{error}</p>}
        <div className="dialog-buttons">
          <button type="button" onClick={properties.onClose}>
            Cancel
          </button>
          <button className="danger solid" type="submit" disabled={!ready}>
            {working ? 'Working…' : properties.confirmLabel}
          </button>
        </div>
      </form>
    </div>
  );
}
