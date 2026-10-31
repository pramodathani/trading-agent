
## refresh() returns a promise, and only the newest answer counts

From research-agent's `079753a`. The Traders page waits for both lists to be read again before opening a new trader's chat, so `refresh` resolves when the answer is shown. While testing in research-agent the selection bounced back after a creation, because an older, slower poll answered after the newer one; each request now has a number and only the latest one's answer or error is kept.
