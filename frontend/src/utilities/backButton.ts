type CloseHandler = () => void;

/**
 * Keeps the things the Android back button should close first, newest on top, such as the menu drawer or the details sheet.
 *
 * When nothing is open the back button goes back a page instead.
 */
export class BackButton {
  private readonly handlers: CloseHandler[] = [];

  /**
   * Adds something that the back button should close.
   * @param handler Closes it.
   * @returns A function that removes the handler again.
   */
  register(handler: CloseHandler): () => void {
    this.handlers.push(handler);
    return () => {
      const position = this.handlers.lastIndexOf(handler);
      if (position >= 0) {
        this.handlers.splice(position, 1);
      }
    };
  }

  /**
   * Closes the newest open thing, if there is one.
   * @returns True when something was closed, false when nothing was open.
   */
  closeNewest(): boolean {
    const handler = this.handlers.at(-1);
    if (handler === undefined) {
      return false;
    }
    handler();
    return true;
  }
}

export const backButton = new BackButton();
