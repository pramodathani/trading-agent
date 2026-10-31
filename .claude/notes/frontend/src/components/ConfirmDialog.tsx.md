# ConfirmDialog.tsx

Risky buttons (flatten a trader, fire the kill switch) open this dialog. It always asks for a reason, which goes to the journal, and can also require a typed word. The confirm button stays disabled until both are given, so a stray click or Enter cannot fire it.

## askReason

Retiring a trader needs a confirmation but no reason for the journal, so the reason field can be left out. The typed-word check stays for the actions that use it.
