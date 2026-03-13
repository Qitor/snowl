# Monitor UI Change Checklist

## Status

Draft for active use.

## Purpose

This checklist exists to prevent Snowl Web Monitor UI changes from regressing readability, information hierarchy, and operator usability.

Use this checklist whenever changing:

- run workspace UI
- runtime logs UI
- trial detail UI
- pretask diagnostics UI
- metadata cards
- filters/search controls
- badges/status presentation
- raw payload/debug surfaces

This checklist complements `docs/monitor_ui_spec.md`.

---

## 1. Core Review Questions

Before calling a UI task done, verify:

### Readability
- Is the text readable on a normal laptop screen without zoom?
- Did any primary or secondary surface drop below the minimum readable size?
- Are dense surfaces using enough line height and spacing?
- Does any important content still feel tiny?

### Information hierarchy
- Does the page show human-readable summary before raw technical detail?
- Is primary information visually stronger than secondary and tertiary information?
- Are raw ids and raw payloads visually subordinate to status and attention summary?
- Is there a clear “what is happening?” answer near the top of the relevant panel?

### Operator usability
- Can a user quickly identify what needs attention?
- Does the attention state explain why it matters?
- Does the UI suggest what to inspect next?
- Is the interface usable by someone who does not want to read raw JSON immediately?

### Debug access
- Is raw detail still accessible when needed?
- Are raw event payloads, identifiers, and JSON still available through expansion, copy, or detail views?
- Did the change accidentally hide important debugging data entirely?

---

## 2. Typography Checklist

- Is body text comfortably readable?
- Is log text comfortably readable?
- Are card labels and helper text still legible?
- Are section titles visually distinct from body content?
- Are mono surfaces limited mostly to logs, ids, and raw payloads?
- Did any small utility text become too small for real use?

If the answer to any of these is “not sure,” the page likely needs another pass.

---

## 3. Identifier Handling Checklist

- Are long run ids truncated on primary surfaces?
- Are long trial ids truncated on primary surfaces?
- Are model/session/task composite keys truncated when they appear in summaries?
- Is the full value still accessible via tooltip, copy action, or detail view?
- Are human-readable labels used where possible instead of long machine strings?
- Are identifiers visually de-emphasized relative to status and summary?

---

## 4. Runtime Logs Checklist

- Is the log view readable without zoom?
- Are log rows easy to scan?
- Is there a human-readable event summary in the default row?
- Is the raw event key preserved but visually secondary?
- Are timestamp, summary, and metadata separated clearly enough?
- Are selected/matched/filter states understandable?
- Does the log area still feel like a product surface rather than a pasted terminal?

---

## 5. Trial Detail Checklist

- Does Trial Detail begin with a readable summary?
- Does it show current status and phase before raw payload?
- Is the attention reason shown clearly if the trial needs attention?
- Is there a suggested next inspection action?
- Is raw JSON collapsed or visually demoted?
- Are structured details shown before the raw event block?

---

## 6. Attention State Checklist

For any attention-worthy state:

- Is the reason explicit?
- Is the current phase/status visible?
- Is the last meaningful progress signal visible?
- Is recoverable vs failed distinguished clearly?
- Is the user told what to inspect next?
- Is the attention treatment more than just a color badge?

---

## 7. Filters and Control Bar Checklist

- Are search and filter controls readable?
- Are control sizes large enough for comfortable use?
- Is the current filter state visually clear?
- Is the match count understandable?
- Is placeholder/help text human-readable?
- Does the control bar look like a product control surface rather than a backend debug strip?

---

## 8. Raw Payload / JSON Checklist

- Is raw JSON shown only after summary and structured detail?
- Is raw JSON collapsible or visually secondary?
- Does the page avoid leading with large code blocks?
- Are raw event fields available when debugging requires them?
- Did the UI accidentally make raw payload the main reading experience again?

---

## 9. Visual Regression Checklist

After any meaningful UI change, verify:

- no important section has shrunk typography unintentionally
- no key card or summary surface became denser and harder to scan
- no newly added widget introduces tiny text
- no new feature bypasses the summary-first rule
- no new panel leads with raw internal data unless explicitly a developer-only surface

---

## 10. Minimum Validation Routine for UI Changes

For any non-trivial monitor UI change:

1. Run the monitor locally.
2. Open at least one active run workspace.
3. Inspect:
   - top workspace summary
   - runtime logs panel
   - trial detail panel
   - pretask or equivalent diagnostic view
4. Confirm:
   - readable text sizing
   - correct hierarchy
   - raw detail still accessible
   - attention state still understandable

If the change affects shared components, inspect multiple surfaces, not just the one you edited.

---

## 11. Screenshot Validation Set

Before calling a UI change done, capture or review screenshots for:

1. Run workspace top summary
2. Runtime logs panel
3. Trial detail panel
4. Attention state / recoverable state
5. Any drawer/modal used for diagnostics
6. One surface showing raw payload expanded

The screenshots should make it obvious whether:

- the text is readable
- summary comes before raw detail
- ids are visually controlled
- logs are scannable

---

## 12. Docs Update Rules

Update `docs/monitor_ui_spec.md` when a UI change affects:

- typography baseline
- information hierarchy rules
- identifier handling rules
- raw payload presentation rules
- panel composition rules
- attention-state presentation rules

Update this checklist when:

- a new recurring UI regression pattern appears
- a new major monitor surface is added
- the review process needs a new mandatory validation item

---

## 13. When a UI Change Requires a Design Doc

Write or update a design doc before coding if the change:

- introduces a new major monitor surface
- changes the default information hierarchy
- changes how runtime state is summarized
- changes the relationship between summary and raw technical detail
- changes shared typography or component rules
- introduces a new operator workflow such as intervention, retry, or compare flows

Small spacing or copy fixes do not need a design doc.

---

## 14. Done Criteria

A monitor UI change is not done just because the page compiles.

It is done when:

- the target surface is more readable
- the hierarchy is clearer
- operator understanding improves
- raw technical detail remains accessible
- screenshots or live validation confirm the change
- required docs are updated if UI rules changed