import { type KeyboardEvent, useEffect, useRef, useState } from 'react';

import type { TraderSummary } from '../api/types';
import { selectedTraderStore } from './selectedTraderStore';

/** What the trader menu shows. */
interface TraderMenuProperties {
  traders: TraderSummary[];
  selectedTrader: string;
}

/**
 * The header's trader chooser: a button with the chosen trader's name that opens a list of every trader, styled like Claude Code's menus.
 * @param properties The traders and the chosen one.
 * @returns The menu.
 */
export function TraderMenu(properties: TraderMenuProperties) {
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const menuReference = useRef<HTMLDivElement>(null);
  const buttonReference = useRef<HTMLButtonElement>(null);
  const traders = properties.traders;

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

  /** Opens the menu with the chosen trader highlighted. */
  function openMenu(): void {
    const index = traders.findIndex((trader) => trader.name === properties.selectedTrader);
    setHighlighted(Math.max(index, 0));
    setOpen(true);
  }

  /**
   * Chooses a trader and closes the menu.
   * @param traderName The trader.
   */
  function choose(traderName: string): void {
    selectedTraderStore.choose(traderName);
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
      setHighlighted((index) => (index + 1) % traders.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlighted((index) => (index - 1 + traders.length) % traders.length);
    } else if (event.key === 'Enter' && traders[highlighted] !== undefined) {
      event.preventDefault();
      choose(traders[highlighted].name);
    }
  }

  return (
    <div className="trader-menu" ref={menuReference} onKeyDown={handleKey}>
      <button
        ref={buttonReference}
        type="button"
        className={open ? 'trader-menu-button open' : 'trader-menu-button'}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : openMenu())}
      >
        {properties.selectedTrader}
        <svg viewBox="0 0 16 16" aria-hidden="true">
          <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <ul className="trader-menu-list" role="listbox" aria-label="Trader">
          {traders.map((trader, index) => {
            const chosen = trader.name === properties.selectedTrader;
            let className = 'trader-menu-item';
            if (index === highlighted) {
              className = `${className} highlighted`;
            }
            return (
              <li
                key={trader.name}
                role="option"
                aria-selected={chosen}
                className={className}
                onMouseEnter={() => setHighlighted(index)}
                onClick={() => choose(trader.name)}
              >
                <span className={trader.state === 'idle' ? 'trader-menu-dot' : 'trader-menu-dot busy'} />
                <span className="trader-menu-name">{trader.name}</span>
                <span className="trader-menu-state">{trader.paused ? 'paused' : trader.state}</span>
                <svg className={chosen ? 'trader-menu-check' : 'trader-menu-check hidden'} viewBox="0 0 16 16" aria-hidden="true">
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
