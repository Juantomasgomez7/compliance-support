# Build your own Claude Code plugin

This guide covers: what a Claude Code plugin is, when to build one (and when not), how to build it with Claude Code, and best practices.

Target Audience:  For an engineer with basic Claude Code experience who wants to package a workflow as a plugin.

## When to use a plugin

A plugin does two jobs: it bundles primitives into one unit, and it shares them. Build one when you want to:

- Combine several primitives into one installable unit to get a result no single primitive delivers.
- Make a behavior or convention the team default, applied without each person having to remember it.
- Hand the same setup to other people or repos in a single install.

## When not to use a plugin

When a single primitive is enough, use it directly and skip the plugin:

- A capability just for you on one machine: a skill in `~/.claude/skills/` loads on its own.
- Standing rules or context for one repo: a `CLAUDE.md` (a plugin ships its own rules through a skill, not a root `CLAUDE.md`).
- Data from one external system: a single MCP server in your settings.

## What a plugin is

A plugin turns expertise into infrastructure. It takes know-how that lives in one person's head, packages it as a folder you point Claude Code at, and gives every teammate who installs it access to the same behavior / workflow.

A plugin is built from primitives. Claude Code defines seven kinds, and building a plugin is mostly a matter of matching each job to the primitive that fits it:

| Primitive   | What it is                                                                                                                                                              | Use it when                                                                                                             |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Skills      | A packaged procedure exposed as a`/name` shortcut. You or Claude can invoke it by name, and Claude can also load it on its own when the task matches its description. | You want reusable know-how available either on demand or automatically by context.                                      |
| Sub-Agents  | A subagent that runs in its own separate context window, with its own prompt and a scoped tool set, then hands a result back.                                           | The work should be isolated (heavy exploration, parallel tasks, focused review) so it does not crowd your main context. |
| Hooks       | A script bound to a lifecycle event that fires automatically and deterministically, with no model judgment.                                                             | Something must run every single time: lint, format, scan for secrets, block a risky action.                             |
| MCP servers | A live connection to an outside system, exposed to Claude as callable tools.                                                                                            | Claude needs real-time external data or must act on another system (database, internal API, GitHub).                    |
| LSP servers | Wires in a language server for real-time code intelligence (diagnostics, go-to-definition).                                                                             | You need deep, language-aware editing. Usually you install a ready-made one rather than author it.                      |
| Monitors    | A background watcher that streams live events to Claude (experimental).                                                                                                 | You want Claude to react to logs or status changes as they happen.                                                      |
| Themes      | An editor color scheme (experimental).                                                                                                                                  | Visual preference only.                                                                                                 |

## Building a plugin from scratch with Claude Code

You describe each piece and Claude Code writes it, so the real skill is knowing what to ask for. A thin prompt ("add a hook") makes Claude guess. A good one names the primitive and fills in the specifics it cannot guess, and there are usually more of those than you would expect.

So each step below comes in two parts:

- **A prompt template** with blanks. It is the shape of a strong request for that primitive, and the blanks are the details you have to supply. Fill them in for your own workflow.
- **The same prompt, filled in** for one running example: a **Spend Tracker** that logs and reviews personal expenses. It is deliberately trivial, so the focus stays on how you prompt rather than on the workflow.

Match each job to the primitive that fits it (the table above), then work down the list.

### Scaffold and the manifest

Every plugin starts with a folder and one required file, the manifest.

Prompt template:

```text
Scaffold a Claude Code plugin.
  Name:                   ______   (kebab-case)
  Who it's for:           ______
  What it does:           ______   (one line)
  Primitives I will add:  ______   (e.g. skill, hook, agent, mcp)
Create .claude-plugin/plugin.json and empty folders for those pieces.
```

Filled in for Spend Tracker:

```text
Scaffold a Claude Code plugin.
  Name:                   spend-tracker
  Who it's for:           me, tracking my own expenses
  What it does:           logs and reviews personal spending
  Primitives I will add:  skill, hook, agent, mcp
Create .claude-plugin/plugin.json and empty folders for those pieces.
```

### Skill: a procedure you reuse

A routine you repeat, on demand or by context, is a skill.

Prompt template:

```text
Add a skill to my plugin.
  Call it:       ______   (the /name you will run)
  It should:     ______   (the procedure, step by step)
  Inputs:        ______   (what it takes, and where it reads or writes)
  Load it when:  ______   (the description that tells Claude the skill applies)
Put it in skills/<name>/SKILL.md.
```

Filled in for Spend Tracker:

```text
Add a skill to my plugin.
  Call it:       log
  It should:     append one expense as a row, then confirm the running total for the month.
  Inputs:        an amount, a category, and a note, written to expenses.csv.
  Load it when:  I say I want to log or record a spend.
Put it in skills/log/SKILL.md.
```

Result: `skills/log/SKILL.md`, run as `/spend-tracker:log`.

### Hook: a rule that runs every time

Something that must run on every write and needs no judgment is a hook.

Prompt template:

```text
Add a hook to my plugin.
  Fire on:             ______   (which events? e.g. Write, Edit)
  Watch:               ______   (the path or glob it applies to)
  Block when:          ______   (the exact condition to catch, be specific)
  On block, show:      ______   (the message the user sees, including how to fix it)
  Never block:         ______   (files or cases to leave alone)
  Read settings from:  ______   (one config file, if a hook and agent share scope)
Wire it in hooks/hooks.json, keep the logic in a script (not the model), and load any non-trivial rules from a data file the script reads rather than hardcoding them.
```

Filled in for Spend Tracker:

```text
Add a hook to my plugin.
  Fire on:             Write, Edit
  Watch:               expenses.csv
  Block when:          a new row is missing its amount or its category.
  On block, show:      which field is missing, and the correct row format.
  Never block:         edits to the header row.
  Read settings from:  not needed yet.
Wire it in hooks/hooks.json.
```

Result: an entry in `hooks/hooks.json`, bound to the write event.

### Agent: a review that needs judgment

Work that means reading something and weighing it is an agent.

Prompt template:

```text
Add an agent to my plugin.
  Name it:                ______
  It reviews:             ______   (what it reads, and where)
  Flag:                   ______   (the judgment calls to catch, listed precisely)
  Do NOT flag:            ______   (the cases to leave alone, so it stays precise)
  For each finding, show: ______   (the item, why it is flagged, and the fix)
  Rules come from:        ______   (the skill it reads, not rules pasted in the prompt)
It advises only; it never edits my files. Tools it needs: ______ (e.g. Read, Grep).
```

Filled in for Spend Tracker:

```text
Add an agent to my plugin.
  Name it:                reviewer
  It reviews:             expenses.csv for the current month
  Flag:                   charges far above my usual for a category, and likely miscategorized rows.
  Do NOT flag:            normal recurring bills, or one-offs I have marked as expected.
  For each finding, show: the row, why it stands out, and the category it likely belongs in.
  Rules come from:        the log skill's row format and my category list.
It advises only; it never edits expenses.csv. Tools it needs: Read, Grep.
```

Result: `agents/reviewer.md`.

### MCP server: reach an outside system

When the data or the action lives in another system, that is an MCP server.

Prompt template:

```text
Add an MCP server to my plugin.
  Connect to:       ______   (the external system)
  Configure in:     .mcp.json (command or URL, plus any credentials read from the environment)
  It lets Claude:   ______   (the live data to read, or the action to take)
Use it only where a local script cannot get the data.
```

Filled in for Spend Tracker:

```text
Add an MCP server to my plugin.
  Connect to:       my bank's API
  Configure in:     .mcp.json, reading the access token from the environment.
  It lets Claude:   import this month's card transactions, so I do not type them by hand.
Use it only where a local script cannot get the data.
```

Result: an entry in `.mcp.json`.

### Experimental extras: monitor and theme

Two more primitives exist. Both are experimental and rarely the point of a plugin, so a one-line prompt is usually enough:

- **Monitor**, a background watcher: "Add a monitor that watches the bank feed and tells me when a charge over $100 posts." Result: an entry in `monitors/monitors.json`.
- **Theme**, an editor color scheme: "Add a theme called ledger with a soft green background and high-contrast text." Result: `themes/ledger.json`.

### Validate and share

```text
Validate the plugin, then set up a marketplace so my team can install it.
```

```bash
claude --plugin-dir ./spend-tracker
claude plugin validate ./spend-tracker --strict
```

A clean plugin prints `✔ Validation passed`. Sharing works through a `.claude-plugin/marketplace.json` pushed to GitHub; a teammate then installs it with `/plugin install spend-tracker@your-team`. Bump the `version` in the manifest to release an update; teammates pull it with `/plugin update`, or automatically at session start if they enable auto-update for the marketplace.

## Best practices

- Keep the first version small. One check that earns its keep beats five that half-work; add the next once the first is in people's hands.
- Make an agent precise before thorough. A reviewer that cries wolf gets turned off, so tell it what not to flag and measure it against clean code before you trust it.
- Keep configuration in one place. When a hook and an agent need the same scope, put it in one file both read, not two that drift apart.
- Keep the rules as owned data, separate from the mechanism. A deterministic hook can load its patterns from a data file it reads at startup, exactly as a judgment agent reads its rules from a skill instead of its prompt. In this plugin the control library holds the agent's rules (`SKILL.md`) and the hook's patterns (`patterns.json`) side by side, so the person who owns the policy edits every rule while the engineer owns only the code that runs it, and both gates enforce one definition.
- Add a primitive only when it pays for itself. Every extra agent or MCP server is surface to maintain and context to carry.
