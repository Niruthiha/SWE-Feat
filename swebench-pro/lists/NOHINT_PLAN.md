# No-hint run: cell list (s1, instruction.md verbatim, MAX_ROUNDS=30)
| cell | task | recall_prec | status |
|---|---|---|---|
| 1 | 0d0267c4 | 0.455 | PASS r0 |
| 2 | 8be4f6cb | 0.719 | PASS r0 |
| 3 | d8ff92b4 | 0.75 | PASS r0 |
| 4 | **bf2e89c0** (swapped in 2026-11-05 by user; replaced 08bb0991, recall_prec 1.0) | 0.25 | not launched |
| 5 | 32ff1099 | 0.0 | not launched |

- **Why the swap:** after the cue-strength measure (benchmark-audit/swebench-pro-v2/CUE_STRENGTH.md), the user said "swap". 08bb0991 was the most strongly cued of the five.
- **Why bf2e89c0:** of the low-cue protonmail tasks, it is a behaviour-only description across 8 calendar files.
- **Rejected:**
  - 3a6790f4: its fix is in the module the prompt names (`useLinksListing`); its low score comes only from the gold patch's extra refactoring.
  - c6f65d20: a data-testid sweep.
  - f080ffc3: a layout move.
  - ac23d1ef: a viable alternate.

## Batch 2 (proposed 2026-11-05; not launched, awaiting user go)
User's criteria: gold patch of at least 100 changed lines, touching at least 2 packages. The pool is the 121 no-hint set, protonmail only (same harness and musl image path as batch 1). Exactly 5 unrun protonmail tasks qualify:

| iid | gold lines | code files | packages | recall_prec |
|---|---|---|---|---|
| f080ffc3 | 106 | 15 | 7 (account, calendar, drive, mail, vpn-settings, packages/*) | 0.067 |
| 08bb0991 | 321 | 4 | 2 (applications/storybook, packages/components) | 1.0 |
| 3a6790f4 | 207 | 10 | 3 (drive, packages/components, packages/styles) | 0.0 |
| c6f65d20 | 182 | 30 | 2 (mail, packages/components) | 0.0 |
| fc9d535e | 102 | 7 | 3 (mail, packages/components, packages/shared) | 0.429 |

Earlier I set aside 3a6790f4, c6f65d20 and f080ffc3 only as low-cue *substitutes*, for the reasons above. They are not flawed tasks.
