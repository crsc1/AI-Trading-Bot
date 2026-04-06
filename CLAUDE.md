## UI debugging rules

When investigating a UI bug, especially "X is barely visible" or "X looks wrong":

1. **Measure first, theorize second.** Run JS to get `offsetHeight`, `scrollHeight`,
   `getBoundingClientRect()`, and `getComputedStyle()` on the element AND its ancestors
   before guessing at causes. A 53px section is a layout bug, not a contrast bug.
2. **Check overflow.** `overflow: hidden` inside flex containers collapses sections.
   This is the #1 cause of "barely visible" sections in this codebase. Always check
   `overflow`, `max-height`, and `flex` on the element and its parent chain.
3. **Don't chase secondary symptoms.** If a section is 53px tall, fix the height first.
   Color contrast is irrelevant if the section is collapsed.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
