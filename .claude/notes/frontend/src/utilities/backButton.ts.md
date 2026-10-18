# backButton.ts

Android's back button should close the newest open layer before leaving the page, the way the Claude app closes its drawer or a sheet first. Components register a close handler while open (through `hooks/useCloseOnBack.ts`), and the Capacitor `App` back-button listener asks `closeNewest()` first; only when it returns false does the app go back a page or leave.
