# GitHub Copilot Instructions for pixie-for-pm

## Project Overview

pixie-for-pm is a multi-agent product collaboration system. Each agent plays a role in a cross-functional product team, with Discord as the main user-facing interface and MCP as the integration layer for external systems.

The initial product surface should assume these core integrations:

- **Discord** for the primary bot and conversational interface
- **Notion** for shared context, documentation, and team knowledge
- **GitHub** for source code, issues, pull requests, and technical delivery context
- **PostHog** for product analytics and behavioral signals
- **Vercel** for deployable clickable prototypes and preview environments

The project should be designed so agents can combine structured product context, engineering context, and analytics context without hard-coding integration logic directly into agent prompts.

## Expected Architecture Direction

This repository is being set up from scratch. Until the implementation proves otherwise, prefer an architecture with clear separation between:

- **agent orchestration** — agent roles, routing, workflows, handoffs
- **Discord interface** — bot entrypoints, commands, threads, user-facing formatting
- **MCP integration layer** — adapters and tools for Notion, GitHub, PostHog, and Vercel
- **domain logic** — planning, research, prototype coordination, delivery workflows
- **storage/configuration** — environment settings, workspace config, local state, secrets boundaries
- **tests** — unit, integration, and end-to-end coverage mirroring the source tree
- **specs/changelogs** — system design, workflow contracts, and implementation history

Prefer explicit boundaries between agent logic and integration logic. Agent roles should consume typed context and tool interfaces, not raw third-party SDK calls scattered across the codebase.

## Technology Baseline

Unless the user directs otherwise, start from the same development discipline as `pixie-qa`:

- **Python 3.11+** with type hints
- **uv** for package and environment management
- **pytest** for testing
- **mypy** for static type checking
- **ruff** for linting and formatting
- **Playwright** for browser-based verification when validating Discord-adjacent web flows, dashboards, or prototypes

If the implementation later adds TypeScript services or web surfaces, apply the same standards there: typed APIs, test-first changes, and narrow validation after each edit.

## Workspace Structure Guidance

The exact layout can evolve, but default to a structure that makes agent, integration, and application boundaries obvious. A reasonable starting point is:

```text
pixie_for_pm/
  agents/                  # agent roles, prompts, workflow coordination
  discord/                 # Discord bot entrypoints and interaction handling
  integrations/            # MCP-facing adapters and provider clients
    notion/
    github/
    posthog/
    vercel/
  domain/                  # product planning and workflow logic
  config/                  # typed settings and configuration loaders
  py.typed

tests/
  pixie_for_pm/
    agents/
    discord/
    integrations/
    domain/

specs/                     # architecture and workflow specifications
changelogs/                # non-trivial change summaries
```

Test files must start with `test_`, mirror the structure of the source code, and include regression coverage for every bug fix.

## uv Package Management

Use **uv** for dependency and environment management.

### Common Commands

```bash
uv sync
uv add <package>
uv add --dev <package>
uv run pytest
uv run mypy .
uv run ruff check .
uv run ruff format .
```

### Rules

- **Never use `pip install` directly**
- **Always run tools through `uv run`** unless the environment is already explicitly managed
- **Commit `uv.lock`** alongside dependency changes

## Test-Driven Development Requirements

This project follows strict TDD. Always write or verify tests before implementing a feature or bug fix.

### Development Workflow

1. Understand the requirement and sharpen it into testable behavior.
2. Write the test first.
3. Run the test and verify it fails.
4. Implement the smallest code change that should make it pass.
5. Rerun the same narrow test.
6. Refactor only while keeping tests green.
7. Run broader validation for the touched area.

### Coverage Expectations

- All new behavior must have tests.
- All bug fixes must include a regression test.
- Integration boundaries must be tested with fakes, fixtures, or deterministic mocks.
- Agent workflow logic must be tested separately from provider SDK behavior whenever possible.
- MCP-facing adapters must validate success, error, timeout, and malformed payload paths.

### What to Test

- function inputs and outputs
- role routing and handoff behavior between agents
- Discord interaction handling and message formatting
- MCP adapter request and response mapping
- Notion, GitHub, PostHog, and Vercel integration edge cases
- configuration loading and validation
- failure handling, retries, rate limiting, and degraded modes

## Type Safety Requirements

Use Python type annotations consistently and keep both **mypy** and **Pylance** clean.

### Rules

- All function signatures must be fully annotated.
- Use `|` syntax for unions.
- Prefer typed protocols, dataclasses, and small typed interfaces at integration boundaries.
- Avoid `Any`, `cast()`, and `type: ignore` unless there is no cleaner alternative.
- Model external payloads explicitly rather than passing around untyped dictionaries deep into the system.

### Required Checks

```bash
uv run mypy .
```

Also verify zero Pylance errors in the editor before considering a task complete.

## Incremental Development

Implement changes in small slices. Before and after each slice, run the narrowest meaningful validation.

### Default Loop

1. Search for existing implementations before writing new code.
2. Add or update a failing test.
3. Make the smallest plausible change.
4. Run a focused test or type check immediately.
5. Only expand scope after the touched slice is green.

Avoid broad rewrites when a narrow, testable change will solve the problem.

## Code Reuse and Boundaries

Before adding new modules or abstractions:

1. Search the codebase for existing helpers, patterns, and contracts.
2. Reuse or extend existing code when it keeps boundaries clearer.
3. Extract shared helpers when the same logic appears in multiple places.

Keep these boundaries explicit:

- Discord transport code should not directly own product decision logic.
- MCP and provider adapters should not contain agent policy.
- Agent prompts and workflow code should not be responsible for secret loading or raw SDK setup.
- Domain logic should remain testable without live network access.

## Documentation and Changelog Requirements

Documentation is part of implementation, not follow-up work.

### Keep Up To Date

- root `README.md` for project overview and setup
- relevant module and API docstrings
- `specs/` documents for architecture, workflows, and integration contracts
- `tests/README.md` when test structure or manual verification changes
- `changelogs/<feature>.md` for every non-trivial feature or bug fix

### Hard Completion Gate

For any non-trivial change, the work is not complete until the same change set includes:

1. relevant tests
2. relevant README and docstring updates
3. relevant `specs/` updates when behavior or architecture changes
4. a `changelogs/<feature>.md` entry

## Validation Expectations

Before finishing a meaningful task, run the narrowest checks that fit the touched surface. Typical commands are:

```bash
uv run pytest
uv run mypy .
uv run ruff check .
```

Prefer narrower test targets before full-suite runs when iterating.

When changes affect clickable prototypes, dashboards, or browser-rendered artifacts, add browser-based verification with Playwright where practical.

## Integration and Reliability Rules

This project will depend on external systems and agent workflows, so reliability rules matter from the start.

### Required Practices

- Never let raw provider exceptions leak through user-facing Discord flows without translation.
- Treat Notion, GitHub, PostHog, and Vercel as unreliable network boundaries.
- Validate and sanitize all external payloads before using them in agent context.
- Make retries, timeouts, and fallback behavior explicit.
- Keep secrets out of prompts, logs, snapshots, and persisted chat transcripts.
- Design Discord handlers and background jobs so a single failed integration call does not crash the whole workflow.

## Summary Checklist

Before considering a task complete:

1. Write or update tests first.
2. Run the narrowest relevant pytest target.
3. Run `uv run mypy .`.
4. Run `uv run ruff check .`.
5. Check for Pylance errors.
6. Update docs and specs as needed.
7. Add or update `changelogs/<feature>.md` for non-trivial changes.
8. Verify behavior end to end when the change crosses agent, Discord, MCP, or browser-visible boundaries.

## Default Development Principles

When the user does not specify otherwise, optimize for:

- small, reversible edits
- typed contracts over implicit dictionaries
- deterministic tests over live dependency calls
- narrow validation immediately after each edit
- separation between agent policy, transport, and integrations
- explicit documentation of workflows and handoff contracts
