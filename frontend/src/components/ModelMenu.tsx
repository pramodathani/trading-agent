import { useEffect, useRef, useState } from 'react';

import { apiClient } from '../api/apiClient';
import type { DeskBackend, DeskSummary } from '../api/types';
import { modelNames } from '../utilities/modelNames';

/** What the model menu shows. */
interface ModelMenuProperties {
  desk: DeskSummary;
  onChanged: () => void;
}

/** One model offered in a provider's submenu, and the backend that runs it. */
interface OtherModel {
  model: string;
  backendName: string;
}

/** A provider whose other models open in a submenu, such as Claude. */
interface Provider {
  kind: string;
  models: OtherModel[];
}

/** One row of the main list. */
type MenuRow = { type: 'backend'; backend: DeskBackend } | { type: 'provider'; provider: Provider } | { type: 'auto' };

/**
 * The chat's model chooser below the message box, as in Claude Code: the desk's own models in their order, then "Claude (other models) ›" and "DeepSeek (other models) ›" opening submenus of the provider's other models, then Auto for the configured order.
 * @param properties The desk, and what to call after a change so the page reloads the desk.
 * @returns The menu.
 */
export function ModelMenu(properties: ModelMenuProperties) {
  const desk = properties.desk;
  const backends = desk.backends ?? [];
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const [submenu, setSubmenu] = useState<string | null>(null);
  const [subHighlighted, setSubHighlighted] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const menuReference = useRef<HTMLDivElement>(null);
  const buttonReference = useRef<HTMLButtonElement>(null);
  const providers = providersOf(backends);
  const rows: MenuRow[] = [];
  for (const backend of backends) {
    rows.push({ type: 'backend', backend });
  }
  for (const provider of providers) {
    rows.push({ type: 'provider', provider });
  }
  rows.push({ type: 'auto' });
  const preferredBackend = backends.find((backend) => backend.name === desk.preferred_model) ?? null;
  const openProvider = providers.find((provider) => provider.kind === submenu) ?? null;

  useEffect(() => {
    if (!open) {
      return;
    }

    /**
     * Closes the menu when the user clicks anywhere outside it.
     * @param event The mouse event.
     */
    function closeOnOutsideClick(event: MouseEvent): void {
      if (menuReference.current !== null && !menuReference.current.contains(event.target as Node)) {
        closeMenu();
      }
    }

    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', handleKey);
    };
  });

  /** Opens the menu with the current choice highlighted. */
  function openMenu(): void {
    setError(null);
    setSubmenu(null);
    const index = rows.findIndex((row) => row.type === 'backend' && row.backend.name === desk.preferred_model);
    setHighlighted(index >= 0 ? index : rows.length - 1);
    setOpen(true);
  }

  /** Closes the menu and any submenu. */
  function closeMenu(): void {
    setOpen(false);
    setSubmenu(null);
  }

  /**
   * Opens a provider's submenu.
   * @param kind The provider's backend kind.
   */
  function openSubmenu(kind: string): void {
    setSubmenu(kind);
    setSubHighlighted(0);
  }

  /**
   * Makes a backend the first choice, optionally with another model, or returns to the configured order, and closes the menu.
   * @param backendName The backend, or null for Auto.
   * @param model Another model of that backend, or null for its configured model.
   */
  async function choose(backendName: string | null, model: string | null): Promise<void> {
    closeMenu();
    buttonReference.current?.focus();
    try {
      await apiClient.chooseModel(desk.name, backendName, model);
      properties.onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }

  /**
   * Chooses or opens the row at a position of the main list.
   * @param index The row's position.
   */
  function activate(index: number): void {
    const row = rows[index];
    if (row.type === 'backend') {
      void choose(row.backend.name, null);
    } else if (row.type === 'provider') {
      openSubmenu(row.provider.kind);
    } else {
      void choose(null, null);
    }
  }

  /**
   * Keyboard control, heard anywhere on the page while the menu is open: arrows move, Enter chooses, the right arrow opens a submenu and the left arrow or Escape closes it.
   * @param event The key event.
   */
  function handleKey(event: KeyboardEvent): void {
    if (openProvider !== null) {
      const count = openProvider.models.length;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setSubHighlighted((index) => (index + 1) % count);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        setSubHighlighted((index) => (index - 1 + count) % count);
      } else if (event.key === 'Enter') {
        event.preventDefault();
        const chosen = openProvider.models[subHighlighted];
        void choose(chosen.backendName, chosen.model);
      } else if (event.key === 'ArrowLeft' || event.key === 'Escape') {
        event.preventDefault();
        setSubmenu(null);
      }
      return;
    }
    const number = Number.parseInt(event.key, 10);
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu();
      buttonReference.current?.focus();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlighted((index) => (index + 1) % rows.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlighted((index) => (index - 1 + rows.length) % rows.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      activate(highlighted);
    } else if (event.key === 'ArrowRight' && rows[highlighted].type === 'provider') {
      event.preventDefault();
      activate(highlighted);
    } else if (number >= 1 && number <= backends.length) {
      event.preventDefault();
      void choose(backends[number - 1].name, null);
    }
  }

  if (backends.length === 0) {
    return null;
  }

  let buttonLabel = 'Auto';
  let buttonDetail = modelNames.label(backends.find((backend) => backend.name === desk.last_model)?.active_model ?? desk.last_model) || 'configured order';
  if (preferredBackend !== null) {
    buttonLabel = modelNames.label(preferredBackend.active_model ?? preferredBackend.model);
    buttonDetail = preferredBackend.name;
  }

  return (
    <div className="model-menu" ref={menuReference}>
      {error !== null && <span className="error-text small">{error}</span>}
      <button
        ref={buttonReference}
        type="button"
        className={open ? 'model-menu-button open' : 'model-menu-button'}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Choose which model the desk tries first"
        onClick={() => (open ? closeMenu() : openMenu())}
      >
        <span>{buttonLabel}</span>
        <span className="model-menu-muted">{buttonDetail}</span>
      </button>
      {open && (
        <div className="model-menu-list" role="listbox" aria-label="Model">
          {rows.map((row, index) => {
            const className = index === highlighted ? 'model-menu-item highlighted' : 'model-menu-item';
            if (row.type === 'backend') {
              const chosen = desk.preferred_model === row.backend.name && (row.backend.active_model ?? row.backend.model) === row.backend.model;
              return (
                <div
                  key={row.backend.name}
                  role="option"
                  aria-selected={chosen}
                  className={className}
                  onMouseEnter={() => {
                    setHighlighted(index);
                    setSubmenu(null);
                  }}
                  onClick={() => activate(index)}
                >
                  <span className="model-menu-name">{modelNames.label(row.backend.model)}</span>
                  <span className="model-menu-muted">{row.backend.name}</span>
                  {chosen ? <CheckIcon /> : <span className="model-menu-key">{index + 1}</span>}
                </div>
              );
            }
            if (row.type === 'provider') {
              const picked = preferredBackend !== null && preferredBackend.kind === row.provider.kind && preferredBackend.active_model !== preferredBackend.model ? preferredBackend.active_model : null;
              return (
                <div key={row.provider.kind}>
                  {rows[index - 1]?.type === 'backend' && <div className="model-menu-divider" />}
                  <div
                    role="option"
                    aria-haspopup="listbox"
                    aria-expanded={submenu === row.provider.kind}
                    aria-selected={picked !== null}
                    className={submenu === row.provider.kind ? `${className} submenu-open` : className}
                    onMouseEnter={() => {
                      setHighlighted(index);
                      openSubmenu(row.provider.kind);
                    }}
                    onClick={() => activate(index)}
                  >
                    <span className="model-menu-name">{modelNames.provider(row.provider.kind)} (other models)</span>
                    <span className="model-menu-muted">{picked !== null ? modelNames.label(picked) : ''}</span>
                    <ChevronIcon />
                  </div>
                  {submenu === row.provider.kind && (
                    <div className="model-submenu" role="listbox" aria-label={`${modelNames.provider(row.provider.kind)} models`}>
                      {row.provider.models.map((other, subIndex) => {
                        const chosen = picked === other.model;
                        return (
                          <div
                            key={other.model}
                            role="option"
                            aria-selected={chosen}
                            className={subIndex === subHighlighted ? 'model-menu-item highlighted' : 'model-menu-item'}
                            onMouseEnter={() => setSubHighlighted(subIndex)}
                            onClick={(event) => {
                              event.stopPropagation();
                              void choose(other.backendName, other.model);
                            }}
                          >
                            <span className="model-menu-name">{modelNames.label(other.model)}</span>
                            <span className="model-menu-muted mono">{other.model}</span>
                            {chosen ? <CheckIcon /> : <span className="model-menu-key" />}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            }
            return (
              <div key="auto">
                <div className="model-menu-divider" />
                <div
                  role="option"
                  aria-selected={desk.preferred_model === null}
                  className={className}
                  onMouseEnter={() => {
                    setHighlighted(index);
                    setSubmenu(null);
                  }}
                  onClick={() => activate(index)}
                >
                  <span className="model-menu-name">Auto</span>
                  <span className="model-menu-muted">configured order, with fallback</span>
                  {desk.preferred_model === null ? <CheckIcon /> : <span className="model-menu-key" />}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Groups the other models of the desk's backends by provider, each model run by the first backend of that provider that offers it.
 * @param backends The desk's backends, in their order.
 * @returns The providers that offer other models, in the order they first appear.
 */
function providersOf(backends: DeskBackend[]): Provider[] {
  const providers: Provider[] = [];
  for (const backend of backends) {
    if ((backend.other_models ?? []).length === 0) {
      continue;
    }
    let provider = providers.find((candidate) => candidate.kind === backend.kind);
    if (provider === undefined) {
      provider = { kind: backend.kind, models: [] };
      providers.push(provider);
    }
    for (const model of backend.other_models) {
      if (!provider.models.some((other) => other.model === model)) {
        provider.models.push({ model, backendName: backend.name });
      }
    }
  }
  return providers;
}

/**
 * The tick beside the current choice.
 * @returns The icon.
 */
function CheckIcon() {
  return (
    <svg className="model-menu-check" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * The arrow on a row that opens a submenu.
 * @returns The icon.
 */
function ChevronIcon() {
  return (
    <svg className="model-menu-chevron" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
