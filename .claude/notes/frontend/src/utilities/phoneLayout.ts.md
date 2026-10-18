# phoneLayout.ts

Some phone changes cannot be done in CSS alone: the model chip moves into the composer row, Enter adds a line instead of sending (a phone keyboard has no Shift+Enter habit, and the Claude app sends with its button), and the composer hint is shorter. `PhoneLayout` watches the same `(max-width: 760px)` query as `phone.css`, so the two always agree.
