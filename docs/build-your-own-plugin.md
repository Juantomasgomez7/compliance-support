# Build your own Claude Code plugin

A one-page recipe. It uses Compliance Support as the running example, but the method works for any team
rule you want enforced as people write code.

## The one idea

Match each piece of work to the primitive that fits it. Claude Code gives you a few building blocks, and
the whole skill is picking by the kind of work, not by what looks impressive.

| Your work | Primitive | Why it fits |
|---|---|---|
| A deterministic rule that should block a write | hook | runs on every write, no model, instant, can deny |
| A check that needs judgment or context | agent | reasons about the code, gives a reason, proposes a fix |
| Shared knowledge the agent needs | skill | one source of truth, preloaded into the agent |
| A memorable way to run it on demand | command | a slash command your team can remember |
| Reaching an external system | MCP server | gives the agent live data or actions, when truly needed |

The rule of thumb: deterministic and blocking is a hook, judgment is an agent, knowledge is a skill. Add
a command for a clean entry point. Reach for an MCP server only when the plugin genuinely needs an
outside system, so you do not add surface that has to be maintained for no real gain.

## The recipe

1. **Name one workflow and one person.** Compliance Support is for a backend engineer in a PCI codebase.
   Pick a single, concrete workflow and resist the urge to cover everything.
2. **List the checks, then split them.** Write down what good looks like. Sort each item into
   deterministic (a regex or an exact rule) or judgment (needs reasoning). That split decides hook versus
   agent.
3. **Deterministic checks become a hook.** Write a small script that reads the pending write from stdin
   and blocks it with a clear reason. Wire it in `hooks/hooks.json` on `PreToolUse` for `Write|Edit`. In
   Compliance Support this is `scripts/scan.sh`, which blocks hardcoded secrets and weak crypto.
4. **Judgment checks become an agent.** Write `agents/<name>.md` with a tight system prompt: what to
   flag, what not to flag, and the output format. Keep it precise, because false positives are what get a
   tool uninstalled. Ours is `agents/compliance-review.md`.
5. **Shared rules become a skill.** Put the knowledge the agent needs in `skills/<name>/SKILL.md`, and
   preload it through the agent's `skills:` field. Ours is `skills/control-library`.
6. **Put scope and settings in one file.** A single config that both the hook and the agent read. One
   source of truth, easy for a non-coder to edit. Ours is `.compliance.yml`.
7. **Add a command.** `commands/<name>.md` gives your team a memorable entry point. Plugin commands are
   namespaced, so ours is `/compliance-support:compliance-review`.
8. **Test the two kinds of check in two ways.** Golden tests for the deterministic hook: feed it inputs
   and assert block or allow. A small eval for the agent: label a few files and score precision and
   recall. See `eval/` for both.
9. **Make it installable.** Run `claude plugin validate`. Write a README that gets a new user from clone
   to a working demo in under five minutes, and test it on a fresh clone before you ship.

## The layout

```
.claude-plugin/plugin.json   the manifest (name, version, description)
hooks/hooks.json             deterministic checks
scripts/                     the hook scripts
agents/<name>.md             judgment checks
skills/<name>/SKILL.md       shared knowledge
commands/<name>.md           on-demand entry points
<config>.yml                 scope and settings, one source of truth
eval/                        golden tests and the agent eval
README.md                    clone to demo in under five minutes
```

## How this maps to other workflows

The same split works far beyond compliance. A forbidden import or a missing license header is a
deterministic rule, so it is a hook. "Is this error message safe to show a user?" needs judgment, so it
is an agent. Your team's API design rules are knowledge, so they are a skill. Start with the one check
that hurts the most, ship it, and add the next one later.

## What to keep in mind

- Start with the smallest version that solves the real problem. You can add checks later.
- Write the block and the finding to teach. A reason that names the rule and the fix turns a blocker into
  help.
- Keep the agent precise. Tell it what not to flag, and measure it.
- Add surface only when the plugin needs it. A second agent or an MCP server that does not earn its place
  works against you.
