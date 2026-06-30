# Build your own Claude Code plugin

This guide is intended for engineering audiences with a basic understanding of Claude Code.

It covers what a plugin is, when and when not to build one, how to use Claude Code to build one from scratch, and best practices.

## What a plugin is

A plugin is a way to turn expertise into infrastructure. It takes know-how that lives in one person's head and packages it as an installable bundle, so any teammate who installs it gets the same behavior by default.

Fundamentally, a plugin is a folder you point Claude Code at. Everything inside loads as a single unit, and the same folder installs the same way for every teammate.

The manifest, `.claude-plugin/plugin.json`, is the one file a shareable plugin needs. Inside it, only `name` is required, and everything else sits at the top level of the folder.

A plugin can hold ten kinds of primitives (the docs call them components). Five of them drive the most important behaviors that make a plugin worth building and installing:

| Primitive  | What it is                                       | What it achieves                              |
| ---------- | ------------------------------------------------ | --------------------------------------------- |
| Command    | A slash command someone runs                     | A human-triggered entry point to the plugin   |
| Agent      | A separate context with its own prompt and tools | Judgment and review that fixed rules can't do |
| Skill      | Reference knowledge Claude can load              | Shared know-how, kept in a central source    |
| Hook       | A script wired to an event                       | Automatic, deterministic enforcement          |
| MCP server | A connection to an external system               | Live external data and actions                |

The other five primitives: (output styles, themes, monitors, LSP servers, and a `bin/` of executables). Very useful but not used nearly as often.

## When to use a plugin

A plugin is a wrapper for two jobs: bundling pieces together and sharing them. Use one when you are trying
to:

- Bundle several primitives into one installable unit, like a command, the hook behind it, and the skill
  they share.
- Hand the same setup to other people or other repos in a single install.
- Make a check or convention the team default, applied without each person having to remember it.
- Package an external connection together with the prompts and skills that drive it.

## When not to use a plugin

For a single piece in a single place, skip the packaging and use the piece directly. Reach for something
simpler when you only need to:

- Add one command or hook to a single project. Put the file in `.claude/`; there is nothing to package.
- Give only yourself a capability on one machine. A skill in `~/.claude/skills/` loads on its own, with no
  marketplace.
- Give Claude standing rules or context for one repo. Write a `CLAUDE.md`; a plugin does not even load its
  own root `CLAUDE.md`, it ships instructions through a skill.
- Add a single external connection. Add one MCP server to your settings, without a plugin.

## Build it with Claude Code

You can write every file by hand, but the natural way is to let Claude Code scaffold the plugin and fill it
in while you steer. Each step is the prompt you give, the file it writes, and why the result looks that way.

One rule runs through all of it: match each piece of work to the primitive that fits it.

- A deterministic rule, enforced the moment code is written, is a hook.
- A check that has to read code and weigh it is an agent.
- Knowledge the agent needs is a skill.
- An entry point a person triggers is a command.
- A reach into an outside system is an MCP server.

Get the mapping right and the plugin mostly falls out of it. Get it wrong, by making a hook reason or an
agent run a regex, and you pay in latency and flakiness.

### 1. Scaffold the folder

> Scaffold a Claude Code plugin named my-plugin: the `.claude-plugin/plugin.json` manifest, plus empty
> commands, agents, skills, and hooks folders.

Claude Code writes the layout:

```
my-plugin/
  .claude-plugin/
    plugin.json
  commands/
  agents/
  skills/
  hooks/
```

Keep only the folders you will use.

### 2. The manifest

> Fill in plugin.json: name my-plugin, version 0.1.0, a one-line description, my name as author, MIT
> license.

```json
{
  "name": "my-plugin",
  "version": "0.1.0",
  "description": "What it does, in one line.",
  "author": { "name": "Your Name" },
  "license": "MIT"
}
```

- `name` is the only required field. It has to be kebab-case, because Claude Code uses it to namespace
  everything the plugin adds.
- `version` is worth setting and bumping on each release, so installs update only when you intend. Leave it
  out and Claude Code versions the plugin by its git commit.

### 3. A command

> Add a command called report that summarizes the risky changes on this branch and writes them to a file a
> reviewer can open.

Claude Code writes `commands/report.md`:

```markdown
---
description: Summarize the risky changes on this branch and write a report.
---
Run `git diff main...HEAD`, list the changes that deserve a closer look, and write them to
`branch-report.md` so the result can be shared.
```

The body is the instruction Claude follows; the frontmatter describes it. Because the plugin is
`my-plugin`, the command runs as `/my-plugin:report`, and namespacing keeps two plugins from colliding on
one name. Writing a file like this, whether a short summary or an agent's findings rendered as Markdown or
HTML, is often a plugin's most useful output: something a teammate or an auditor can read without running
anything.

### 4. A hook

> Add a PreToolUse hook on Write and Edit that runs a check script before any file write, and stub the
> script.

Claude Code writes `hooks/hooks.json` and a starter `scripts/check.sh`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}\"/scripts/check.sh" }
        ]
      }
    ]
  }
}
```

- `${CLAUDE_PLUGIN_ROOT}` is the installed plugin's absolute path. Use it for every path, since the install
  location is not where you wrote the code.
- The script reads the pending tool call as JSON on stdin. To block the write, it prints a deny decision
  and exits. This is what lets a plugin stop a bad write before it lands.

### 5. An agent and the skill it reads

> Add an agent called pii-reviewer that flags personal data in logs, and a skill called control-library it
> preloads for the rules.

Claude Code writes `agents/pii-reviewer.md`:

```markdown
---
name: pii-reviewer
description: Check changed code for personal data written to logs. Use after editing a handler.
tools: Read, Grep, Glob
skills: control-library
---
You review code for one thing: personal data in logs. Flag a line only if it writes an email, a name,
or a card number. Never flag an internal id. Be precise. A false positive gets you ignored.
```

It also writes `skills/control-library/SKILL.md` for the rules.

- A skill's frontmatter `description` is what Claude reads to decide whether the skill applies, so make it
  specific.
- Keeping the rules in the skill means the agent, and anything else, reads one source instead of its own
  copy.

### 6. Run it and validate

Launch a session pointed at the folder:

```bash
claude --plugin-dir ./my-plugin
```

Trigger each piece and watch it work. Edit, restart, repeat. When it behaves, validate:

```bash
claude plugin validate ./my-plugin --strict
```

A clean plugin prints:

```
Validating plugin manifest: my-plugin/.claude-plugin/plugin.json

✔ Validation passed
```

The check covers the manifest, the frontmatter on every command and agent, and the hooks file, and reports
what is malformed. `--strict` turns a misspelled field name from a warning into a failure, which is what you
want before publishing.

### 7. Share it

> Add a `.claude-plugin/marketplace.json` that lists my-plugin with source ./my-plugin.

A marketplace is a repo that lists one or more plugins for others to install:

```json
{
  "name": "my-team",
  "owner": { "name": "My Team" },
  "plugins": [
    { "name": "my-plugin", "source": "./my-plugin" }
  ]
}
```

Push it to GitHub. Your teammate runs two commands:

```bash
/plugin marketplace add my-org/my-repo
/plugin install my-plugin@my-team
```

A `source` can also point at another GitHub repo, a git URL, a subdirectory, or an npm package, so one
marketplace can serve plugins that live in different places.

## Best practices

- Keep the first version small. One check that earns its keep beats five that half-work, and you can add
  the second once the first is in people's hands.
- Match the primitive to the job. The split between a deterministic rule and a judgment call is the whole
  design; the moment a hook starts reasoning or an agent runs a regex, move the work where it belongs.
- Make an agent precise before thorough. A reviewer that cries wolf gets turned off and then protects
  nothing, so tell it what not to flag and measure it against known-clean code before you trust it.
- Keep configuration in one place. When a hook and an agent both need the in-scope paths, put them in one
  file both read, not two that drift apart.
- Use `${CLAUDE_PLUGIN_ROOT}` for every path. A hardcoded path works on your machine and breaks on everyone
  else's. Keep state that must survive an update in `${CLAUDE_PLUGIN_DATA}`.
- Test the way the plugin runs. Feed the hook crafted inputs and assert block or allow, then give the agent
  labeled files and check its hits and misses.
- Add a primitive only when it pays for itself. A second agent or an MCP server you do not need is surface
  to maintain and context to carry. The plugins that hold up are the ones that left things out.
