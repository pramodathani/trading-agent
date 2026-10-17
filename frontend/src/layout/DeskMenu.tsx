import { type KeyboardEvent, useEffect, useRef, useState } from 'react';

import type { DeskSummary } from '../api/types';
import { selectedDeskStore } from './selectedDeskStore';

/** What the desk menu shows. */
interface DeskMenuProperties {
  desks: DeskSummary[];
  selectedDesk: string;
}

/**
 * The header's desk chooser: a button with the chosen desk's name that opens a list of every desk, styled like Claude Code's menus.
 * @param properties The desks and the chosen one.
 * @returns The menu.
 */
export function DeskMenu(properties: DeskMenuProperties) {
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const menuReference = useRef<HTMLDivElement>(null);
  const buttonReference = useRef<HTMLButtonElement>(null);
  const desks = properties.desks;

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
        setOpen(false);
      }
    }

    document.addEventListener('mousedown', closeOnOutsideClick);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
    };
  }, [
    open,
  ]);

  /** Opens the menu with the chosen desk highlighted. */
  function openMenu(): void {
    const index = desks.findIndex((desk) => desk.name === properties.selectedDesk);
    setHighlighted(Math.max(index, 0));
    setOpen(true);
  }

  /**
   * Chooses a desk and closes the menu.
   * @param deskName The desk.
   */
  function choose(deskName: string): void {
    selectedDeskStore.choose(deskName);
    setOpen(false);
    buttonReference.current?.focus();
  }

  /**
   * Moves through the list with the arrow keys, chooses with Enter, and closes with Escape.
   * @param event The key event.
   */
  function handleKey(event: KeyboardEvent<HTMLDivElement>): void {
    if (!open) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        openMenu();
      }
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      buttonReference.current?.focus();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlighted((index) => (index + 1) % desks.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlighted((index) => (index - 1 + desks.length) % desks.length);
    } else if (event.key === 'Enter' && desks[highlighted] !== undefined) {
      event.preventDefault();
      choose(desks[highlighted].name);
    }
  }

  return (
    <div className="desk-menu" ref={menuReference} onKeyDown={handleKey}>
      <button
        ref={buttonReference}
        type="button"
        className={open ? 'desk-menu-button open' : 'desk-menu-button'}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : openMenu())}
      >
        {properties.selectedDesk}
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <ul className="desk-menu-list" role="listbox" aria-label="Desk">
          {desks.map((desk, index) => {
            const chosen = desk.name === properties.selectedDesk;
            let className = 'desk-menu-item';
            if (index === highlighted) {
              className = `${className} highlighted`;
            }
            return (
              <li
                key={desk.name}
                role="option"
                aria-selected={chosen}
                className={className}
                onMouseEnter={() => setHighlighted(index)}
                onClick={() => choose(desk.name)}
              >
                <span className={desk.state === 'idle' ? 'desk-menu-dot' : 'desk-menu-dot busy'} />
                <span className="desk-menu-name">{desk.name}</span>
                <span className="desk-menu-state">{desk.paused ? 'paused' : desk.state}</span>
                <svg className={chosen ? 'desk-menu-check' : 'desk-menu-check hidden'} viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
