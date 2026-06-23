# E2E Test Templates

These are **templates, not auto-run tests**. Copy the relevant template to
`tests/e2e/test_<feature>.md` (or `.py` / `.spec.ts`) in your project. Replace all
`{{PLACEHOLDER}}` tokens with your project's actual values.

To get the full template library, copy from `base-template/.claude/commands/e2e/` or generate
a project from the template after templates are added there.

## Integrating with the SDLC pipeline

Set `block.verify: "consolidated+review"` in `planning/harness.json` and add your E2E command
to `validation.checks[]` to have E2E tests run as part of the `sdlc-block` back-half.
