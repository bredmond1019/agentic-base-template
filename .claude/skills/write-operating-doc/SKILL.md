---
name: write-operating-doc
description: Write a doc the operator reads to DO something today — an operating rhythm, a checklist, a next-action board, a runbook he follows under time pressure or low executive function. Optimises for "where do I start" answered in the first three lines, one screen max, tables over prose, and the argument moved to a separate file. Use BEFORE writing or rewriting any doc whose job is to be acted on rather than understood, and whenever a doc is being avoided because opening it is overwhelming.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Writing an operating doc

**This is not `write-repo-doc`.** That skill teaches a reader a system they do not understand. This
one gets a reader who already understands the system to *act*, on a day when acting is hard.

| | `write-repo-doc` | `write-operating-doc` |
|---|---|---|
| Reader's question | "What is this and how does it work?" | "What do I do right now?" |
| Success | they can explain it | they did the thing |
| Length | as long as the subject needs | **one screen, and no longer** |
| Prose | explains before detail | is the failure mode |
| Failure | reader is confused | **reader closes the file** |

## Who you are writing for

**Brandon, with ADHD, mid-week, with agents running.** He knows the system — he designed it. What
he cannot do is enter a doc that presents him with everything at once and pick a starting point.
Volume is not neutral here; it is the thing that makes the doc go unread. **An unread doc is worse
than no doc, because it also removes the pressure to build something usable.**

He has said this plainly: *"If there is too much info in one place thrown at me, I'm instantly
overwhelmed and avoid that doc all together."* Treat that as a hard requirement, not a preference.

---

## Quickstart

1. **Line 1 is the command.** Not a heading, not context — the thing to type.
2. **Answer "which situation am I in" in one table of at most four rows**, each with a single next
   action.
3. **Move every "why" to a separate `-rationale.md`** and link it once.
4. **Cap it at one screen** — about 100 lines. If it will not fit, the doc is doing two jobs; split
   it.
5. **End with a lookup table**, not a summary. `| Question | Go here |`.
6. Run the checklist at the bottom, then the gates.

---

## The rules

### 1. The first three lines decide everything

The reader's eye lands once. Spend it on the action, never on framing.

```md
# Start here

```bash
python3 scripts/morning.py
```

That's it. Everything below is a lookup table, not reading.
```

The last sentence is doing real work: it gives permission to stop reading, which is what makes the
rest of the page safe to open.

### 2. Tables carry the load; paragraphs are the exception

A table is scannable at a glance and has a visible end. A paragraph has to be entered. Use prose
only where a table would lie — and then keep it to two or three sentences.

**Rule of thumb: if a section is more than four lines of prose, it belongs in the rationale file.**

### 3. Every item is one physical act with a time estimate

"Publish the post" is a project. "Open the draft, read it once, publish, paste the URL into
`blog-tracker.md` — 10 min" is an act.

The time estimate is not decoration. It is what lets a reader match work to the gap they actually
have, and it is why a 10-minute item gets done in a 15-minute window while an unestimated one does
not get started at all.

**Anything over 20 minutes is not atomic. Split it, or mark it explicitly as not-yet-atomic** — do
not print it as if it were ready to do.

### 4. Never show more than five things to do

Five is the cap, and it is generous. Rank them, show the top set, and put the rest behind a link or
below a rule. A list of twenty actionable items is a list of zero actionable items.

### 5. Say what NOT to do, by name

Waiting-on-someone-else items must appear, explicitly labelled, with an instruction to ignore them.
Absence does not stop a reader carrying an item — **seeing it marked "not yours" does.** This is
why the `external` edge type exists in `state.json` and why it is worth the write.

### 6. Generate it if you can

A hand-maintained board drifts, and a drifted board is distrusted, and a distrusted board is not
opened. Prefer a generator plus a small hand-written mapping (the *act* text, which cannot be
derived) over a fully-authored file. See
`planning/open-work/scripts/update_manual.py` **in the brain root** for the pattern: derived
structure, hand-written verbs, and an explicit "not atomic yet" lane for anything missing its verb.
(Bare path, not a link — see the note under Worked example.)

### 7. The argument goes in a sibling file

Every operating doc gets a `<name>-rationale.md` carrying the why, the history, and the tradeoffs.
Link it exactly once, from the lookup table, described as *when* to read it ("Friday review, not
daily") rather than what it contains.

This is not a filing preference. The interface and the argument have different readers and different
lengths, and forcing them into one file means one of them loses — historically, the interface.

### 8. Ordering is by "can I start it", not by importance

A doc sorted by importance opens with the hardest thing, which is where a low-executive-function
reader stops. Sort by cheapest-to-start, and let the ranking note importance in a column.

---

## Frontmatter and indexes

Operating docs are corpus files: they need OKF frontmatter and an `index.md` row like anything else.
**Load `write-okf-markdown` for the schema and the traps** — this skill does not restate them.

One field matters more here than elsewhere: `description` should say *when to open the file*, not
what it contains. "Start here. One command per mode, the week shape, and where to look for anything
else" beats "Documentation of the operating rhythm".

---

## Checklist

- [ ] Line 1 (after the title) is a command or a single-table decision, not prose
- [ ] The whole file fits one screen — roughly 100 lines
- [ ] No section has more than four consecutive lines of prose
- [ ] At most **five** things to do are shown
- [ ] Every action is one physical act with a time estimate, all under 20 minutes
- [ ] Items that are *not* the reader's are listed and labelled as such
- [ ] There is an explicit "you can stop reading now" signal near the top
- [ ] A `-rationale.md` sibling exists and is linked exactly once, with *when* to read it
- [ ] The file is generated where it can be; hand-written parts are only what cannot be derived
- [ ] A lookup table (`| Question | Go here |`) ends the file — not a summary
- [ ] OKF frontmatter present; `description` says when to open it
- [ ] `index.md` row added (Standing Rule 7)
- [ ] This repo's structural/link gate is clean (in the brain fleet: `bastion validate-brain
      --structure` and `--links`, one flag per invocation — they do not compose)

## Worked example

`docs/operating-rhythm.md` **in the brain root** (`agentic-portfolio/`) — 94 lines, five tables,
one command at the top, argument split into `docs/operating-rhythm-rationale.md`. It replaced a
165-line version that was correct, complete, and not read.

> Those are **bare paths, not links, on purpose.** This skill ships to every repo in the fleet, and
> a relative link from a skill directory resolves against *that* repo — `../../../docs/` is
> `<this repo>/docs/`, so the link would be dead everywhere except the brain root. Verified
> 2026-09-05: the file exists at the brain root and in neither `base-template/docs/` nor
> `core/mev/docs/`. If you are not in the brain root you will not have this example; the checklist
> above is the operative part.
