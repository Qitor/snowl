# Monitor UI Spec

## Status

Draft for active use.

## Purpose

This document defines the visual, readability, and information hierarchy rules for the Snowl Web Monitor UI.

It exists to prevent the monitor from regressing into a raw engineering surface where:

- text is too small to read comfortably
- raw event payloads appear before human-readable summaries
- long internal identifiers dominate the page
- logs look like embedded terminal output instead of productized operational telemetry
- new features are added without consistent information hierarchy

This is not a generic design-system document.  
It is a Snowl Monitor-specific UI spec for operator-facing runtime observability.

---

## 1. Core Design Principles

### 1.1 Operator-first by default

The default monitor experience should help a user answer:

- What is happening?
- Which task or trial needs attention?
- Why does it need attention?
- What should I inspect next?

The default UI should optimize for judgment and action, not raw implementation detail.

### 1.2 Progressive disclosure

The monitor should reveal detail in layers:

1. Summary
2. Structured detail
3. Raw payload / raw JSON

Raw technical detail must remain accessible, but it should not dominate the default surface.

### 1.3 Readability before density

The monitor is not an IDE pane or terminal buffer.  
Primary surfaces must remain readable on a normal laptop display without zoom.

### 1.4 Human-readable labels before internal keys

Where possible, the default UI should prefer readable labels such as:

- “Pretask download started”
- “No recent progress”
- “Still recoverable”
- “Qwen2.5-7B”

over raw internal strings such as:

- `runtime.env.preflight.download.start`
- `trial=osworld:test::...`
- long session or container identifiers

### 1.5 Raw detail is secondary, not hidden

The monitor must not remove technical detail.  
Instead, raw detail should be placed behind:

- expand/collapse sections
- detail drawers
- tooltips
- copy actions
- “View raw event” / “Open JSON” affordances

---

## 2. Information Hierarchy

All monitor surfaces should respect this hierarchy.

### 2.1 Primary information

Must be visually dominant.

Includes:

- run status
- trial status
- phase
- attention reason
- progress summary
- recoverable / blocked / failed state
- suggested next action

### 2.2 Secondary information

Supports understanding but should not compete with primary status.

Includes:

- task name
- model name
- variant name
- benchmark name
- last updated time
- summary counts
- high-level runtime context

### 2.3 Tertiary information

Useful for precision, but visually de-emphasized.

Includes:

- run id
- trial id
- session id
- event key
- timestamp precision
- internal source key
- structured technical metadata

### 2.4 Debug-only information

Must not appear as the primary content of a default-expanded panel.

Includes:

- raw JSON
- raw event payload
- schema version
- event id
- event index
- container/session internals
- large mono code blocks

---

## 3. Typography Rules

## 3.1 Typography goals

The monitor must remain readable on a normal laptop display without zoom.

Typography should create strong separation between:

- page titles
- section titles
- card titles
- body text
- secondary text
- badges
- logs
- raw payload blocks

## 3.2 Recommended type scale

These values are guidelines, not rigid one-size-fits-all rules, but they define the intended baseline.

### Page title
- Recommended: 40–48px
- Use for the main run workspace title only

### Section title
- Recommended: 28–32px
- Use for major sections such as Runtime Logs, Trial Detail, Run Metadata

### Card title
- Recommended: 20–24px

### Body text
- Recommended baseline: 14–16px
- Primary operator-facing text should not feel smaller than 14px

### Secondary text
- Recommended baseline: 13–14px
- Avoid pushing important metadata below this unless it is truly tertiary

### Badge text
- Recommended baseline: 12–13px
- Badges must remain readable without zoom

### Monospace / log text
- Recommended baseline: 13–14px
- Log rows must not feel like tiny terminal text

### Raw payload / raw JSON text
- Recommended baseline: 12–13px
- Only acceptable in secondary/expandable surfaces

## 3.3 Minimum readability rule

Default user-visible text on primary surfaces must not fall below the project’s minimum readable size.

Practical rule:

- primary and secondary UI text should generally stay at or above 14px / 13px visual feel
- raw payload may be smaller, but it must not become the default reading surface

## 3.4 Line height and spacing

Dense technical content must use comfortable line height.

Recommended direction:

- body text: around 1.45–1.6
- log rows: around 1.45–1.6
- raw JSON/code blocks: around 1.4–1.5

Tight mono rows should be avoided in default UI surfaces.

---

## 4. Identifier Display Rules

Long machine identifiers should not dominate the monitor.

## 4.1 Primary-surface rule

Long values such as:

- run ids
- trial ids
- task keys
- model keys
- session ids
- container ids

must be truncated in primary surfaces.

## 4.2 Full-value access

The full value should remain accessible via one or more of:

- tooltip
- copy button
- detail drawer
- expandable metadata section

## 4.3 Human-readable label preference

Prefer:

- short task label
- short model name
- short variant label
- short session label

instead of long internal composite keys in primary rows.

## 4.4 Visual de-emphasis

Identifiers should typically use:

- smaller emphasis than status text
- muted color treatment
- monospace only where it improves clarity
- no oversized raw machine strings in primary headers

---

## 5. Panel Composition Rules

Complex panels should follow a consistent information order.

## 5.1 Default panel composition

For monitor panels that describe runtime state, the default order should be:

1. Summary
2. Current status / phase
3. Why it matters
4. Suggested next action
5. Structured details
6. Raw payload / raw JSON

## 5.2 Summary-first requirement

A panel should not begin with raw JSON or a raw event block if a meaningful human summary can be shown first.

## 5.3 Structured details before raw payload

When technical detail is needed, prefer a structured key-value block before showing the raw original event.

---

## 6. Runtime Logs Presentation Rules

The Runtime Logs surface is not a raw terminal view.  
It is a productized observability surface.

## 6.1 Default log row structure

Each log row should be readable in this order:

1. timestamp
2. human-readable event summary
3. secondary metadata
4. raw event key only if needed

Example direction:

Instead of visually leading with:

- `runtime.env.preflight.download.start`

prefer visually leading with:

- `Pretask download started`

The raw event key may remain available in an expanded view or secondary metadata.

## 6.2 Log readability requirements

- log text must be readable without zoom
- rows must have enough height and padding to scan comfortably
- long rows should not become undifferentiated mono walls
- important state words should stand out

## 6.3 Metadata separation

Within a row, visually distinguish:

- time
- summary label
- status/severity
- task/model/trial metadata

Do not render the whole row as one uniform mono sentence if a structured layout is possible.

## 6.4 Severity/state treatment

Logs should visually support states such as:

- running
- attention
- warning
- failed
- blocked
- recovered

These should be recognizable at a glance.

## 6.5 Match/filter readability

The log search and filtering area must feel like a product control bar, not a backend tool strip.

Controls should be:

- readable
- clearly selected or not selected
- appropriately sized
- visually aligned

---

## 7. Trial Detail Rules

Trial Detail should help the user understand what is happening before exposing raw runtime payload.

## 7.1 Required top-level content

The top of Trial Detail should answer:

- current status
- current phase
- last meaningful progress
- why this trial needs attention, if applicable
- suggested next inspection action

## 7.2 Suggested structure

Recommended order:

1. Trial summary card
2. Attention summary, if applicable
3. Key metadata
4. Structured runtime detail
5. Raw event / raw JSON (collapsed or secondary)

## 7.3 Raw event handling

Raw event blocks should:

- remain accessible
- be collapsible
- be visually secondary
- not dominate the default view

## 7.4 Pretask and similar diagnostics

Pretask diagnostics should be framed in human-readable terms first:

- current step
- last signal
- status
- likely reason for attention
- next suggested inspection

Raw internals may be shown after that.

---

## 8. Attention State Presentation

Attention is not just a color or badge.  
It must explain what happened and what to inspect next.

## 8.1 Required attention summary fields

When a run, task, or trial needs attention, the UI should show:

- a short attention title
- current status or phase
- why it is attention-worthy
- how recent the last progress signal is
- suggested next step

## 8.2 Example direction

Good:

- `No recent progress during pretask download`
- `Still recoverable`
- `Last update 3m ago`
- `Next step: open Pretask`

Bad:

- showing only a generic red badge with no explanation

## 8.3 Recoverable vs failed

Recoverable states should not look identical to terminal failures.

The monitor should distinguish:

- recoverable
- still failing
- blocked
- failed
- recovered

---

## 9. Cards, Badges, and Controls

## 9.1 Card rules

Cards should:

- show one main message clearly
- avoid dense tiny metadata walls
- keep key numbers legible
- use muted supporting text for secondary information

## 9.2 Badge rules

Badges should be readable and meaningful.

They should be used for:

- status
- phase
- severity
- attention type

They should not become a dumping ground for long internal strings.

## 9.3 Control rules

Search fields, dropdowns, toggles, and filters should:

- be readable on laptop screens
- clearly show current state
- align visually with the rest of the panel
- avoid ultra-compact admin-tool styling

---

## 10. Default-visible vs Collapsed Content

## 10.1 Default-visible

Should usually include:

- status
- phase
- summary
- attention reason
- suggested next step
- last progress
- top-level metrics and counts

## 10.2 Collapsed or secondary by default

Should usually include:

- raw JSON
- raw event payload
- schema fields
- internal identifiers
- long technical metadata blocks

## 10.3 Accessibility of collapsed detail

Collapsed detail must still be easy to access for debugging.  
Do not bury raw detail behind hidden developer-only routes.

---

## 11. Monitor-specific Anti-Patterns

Avoid these patterns:

- tiny text that requires zoom to read
- raw JSON shown before human summary
- long machine ids in large prominent headers
- logs rendered as undifferentiated terminal lines
- event keys shown as the only label users see
- attention states without explanation
- controls that look like backend debug widgets instead of product controls
- using monospace too broadly across non-code surfaces

---

## 12. Implementation Guidance

When implementing or updating monitor UI:

1. start from operator questions
2. define summary first
3. define structured detail second
4. place raw payload last
5. ensure typography meets readability baseline
6. truncate identifiers in primary surfaces
7. preserve full technical detail through secondary affordances

---

## 13. Scope of This Spec

This spec applies to Snowl Web Monitor surfaces including, but not limited to:

- run workspace
- runtime logs
- trial detail
- pretask diagnostics
- metadata cards
- attention summaries
- filter bars
- expandable debug sections

It should be used for both incremental UI refinement and future feature additions.