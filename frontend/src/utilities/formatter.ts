const INDIA_TIME_ZONE = 'Asia/Kolkata';

/** Formats money, numbers and times the same way on every page. */
export class Formatter {
  private readonly rupees = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  private readonly price = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  private readonly clock = new Intl.DateTimeFormat('en-IN', {
    timeZone: INDIA_TIME_ZONE,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  private readonly dayAndClock = new Intl.DateTimeFormat('en-IN', {
    timeZone: INDIA_TIME_ZONE,
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  /**
   * Formats an amount of money.
   * @param amount The amount in rupees.
   * @returns Such as "₹1,23,456.70".
   */
  money(amount: number | null | undefined): string {
    if (amount === null || amount === undefined) {
      return '—';
    }
    return this.rupees.format(amount);
  }

  /**
   * Formats a profit or loss with its sign.
   * @param amount The amount in rupees.
   * @returns Such as "+₹120.00" or "−₹45.50".
   */
  signedMoney(amount: number | null | undefined): string {
    if (amount === null || amount === undefined) {
      return '—';
    }
    if (amount > 0) {
      return `+${this.rupees.format(amount)}`;
    }
    if (amount < 0) {
      return `−${this.rupees.format(-amount)}`;
    }
    return this.rupees.format(0);
  }

  /**
   * Formats a price.
   * @param value The price.
   * @returns Such as "12.59".
   */
  priceText(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }
    return this.price.format(value);
  }

  /**
   * Formats a moment as an India clock time.
   * @param isoText The moment as ISO 8601.
   * @returns Such as "09:15:02".
   */
  time(isoText: string): string {
    const moment = new Date(isoText);
    if (Number.isNaN(moment.getTime())) {
      return isoText;
    }
    return this.clock.format(moment);
  }

  /**
   * Formats a moment as an India day and time.
   * @param isoText The moment as ISO 8601.
   * @returns Such as "17 Oct, 12:51".
   */
  dayTime(isoText: string): string {
    const moment = new Date(isoText);
    if (Number.isNaN(moment.getTime())) {
      return isoText;
    }
    return this.dayAndClock.format(moment);
  }

  /**
   * Chooses the colour class for a profit or loss.
   * @param amount The amount.
   * @returns "profit", "loss" or "flat".
   */
  pnlClass(amount: number | null | undefined): string {
    if (amount === null || amount === undefined || amount === 0) {
      return 'flat';
    }
    return amount > 0 ? 'profit' : 'loss';
  }
}

export const formatter = new Formatter();
