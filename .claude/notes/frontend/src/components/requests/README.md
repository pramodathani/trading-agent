# components/requests/

Copies Claude Code's prompts: the waiting request is docked above the message box (permission requests first, because they lapse), and the transcript keeps a short summary of what was asked and answered.

- QuestionCard: a tab per question with ticks once answered and a Submit tab for review; numbered options with descriptions; check boxes for multiple choice; an Other box; a preview panel beside the options when any option has one. A single question with a single choice is sent on the first click, as Claude Code does.
- PlanCard: the plan in Markdown, a feedback box, Keep planning (needs feedback) and Approve.
- PermissionCard: the tool and its arguments, "Do you want to proceed?" with 1 Yes, 2 Yes and don't ask again, 3 No with a reason, and a countdown to the lapse time.

A message that carries a request_id is the harness's write-up of the user's answer, so the chat shows a short "Your response went to the trader" note instead of that text.
