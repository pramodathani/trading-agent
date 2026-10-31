# TurnProgress.tsx

Copies Claude Code's working indicator: an orange spark that cycles through the glyphs Claude Code's terminal spinner uses (· ✢ ✳ ✶ ✻ ✽) while turning, words with a light sweeping across them, and the seconds since the turn started. Both animations stop for viewers who ask the system for reduced motion.

The words say what the trader is doing: the running tool's activity from `toolDescriber` with its most telling argument, "Writing the answer" while text streams, "Waiting in the queue" before the turn starts, and otherwise a thinking word chosen from the trigger id, so it stays the same for the whole turn instead of flickering.
