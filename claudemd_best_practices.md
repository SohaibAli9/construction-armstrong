# CLAUDE.md Best Practices

Research synthesised from Anthropic docs, community guides, and real-project experience.  
Sources: docs.anthropic.com/claude-code/memory, humanlayer.dev, datacamp.com, jdhodges.com

---

## What it is

CLAUDE.md is injected into every Claude Code session as a system-level context block.  
Adherence is ~80% — for 100% enforcement, use hooks in `settings.json` instead.

---

## Sections to include (priority order)

1. **Project overview** — one paragraph: what it does, primary stack, any unusual tech choices.
2. **Build / run commands** — exact commands. Claude executes these dozens of times per session.
3. **Hard constraints** — things Claude must never do. One per line, each paired with what to do instead.
4. **Architecture / structure** — where things live, module boundaries. Only what cannot be inferred by reading files.
5. **Workflow rules** — scope of changes, test expectations, PR conventions.

---

## Lean vs. necessary

**Skip:**
- Standard language idioms Claude already knows
- Anything readable directly from `pyproject.toml`, `tsconfig`, `Dockerfile`, etc.
- Vague goals: "write clean code", "prefer composition" — not testable

**Keep:**
- What a new teammate would need to be told verbally on day one
- Project-specific deviations from the standard pattern, and **why**
- Rules that have caused mistakes before

**Size target:** under 200 lines. Adherence degrades above ~150–200 total instructions.

---

## CLAUDE.md vs other storage

| What | Where |
|---|---|
| Durable rules, build commands, always-on conventions | `CLAUDE.md` |
| Personal preferences (not team-wide) | `~/.claude/CLAUDE.md` or `CLAUDE.local.md` |
| Task-specific instructions loaded on demand | Skills files |
| Corrections/preferences across sessions | Auto Memory |
| 100%-enforced actions (lint, format) | Hooks in `settings.json` |
| Current task tracking | Claude Tasks |

---

## Writing instructions Claude follows reliably

- **Concrete and testable.** If you can't verify in code review whether the rule was followed, rewrite it.
- **Pair prohibitions with solutions.** "Never X; instead do Y."
- **One rule per line.** Dense paragraphs get skimmed.
- **Commit to git** so the whole team maintains it.
- Use `/init` to generate a starter file, then refine.

---

## Common mistakes

- File over 300–500 lines → adherence degrades
- Repeating what the code already says
- Prohibitions without a positive direction
- Conflicting rules across `~/.claude/CLAUDE.md` and project `CLAUDE.md`
- Vague rules that cannot be verified
