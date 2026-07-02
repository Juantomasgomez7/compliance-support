# Design notes

A few decisions behind Compliance Support that were not obvious, and the places I had to steer Claude Code rather than take its first answer. This is the "how it was built" companion to the README.

## Two tiers, not one

The four controls split cleanly into two kinds. A hardcoded secret or an MD5 hash is always wrong; you can match it and there is nothing to argue about. Personal data in a log, or a refund that returns with no audit entry, needs judgment: is this field actually sensitive, does this handler really move money.

So I built two gates instead of one. Gate 1 is a PreToolUse hook that runs a regex scanner and blocks the write. No model, no cost, no false positives worth debating. Gate 2 is the compliance-review agent, and it runs only on the two controls a scanner cannot judge. Sending all four to the model would have been easier to write and worse to live with: slower, more expensive, and noisier. The first false positive on a payments team is the last time they trust the gate, so keeping the model out of the deterministic cases was a correctness decision, not just a cost one.

## Two owners, not one

Splitting the controls by tier also split them by owner, and that turned out to matter as much as the tiers. Every control definition lives in the AppSec-owned control library: the two judgment controls as prose the agent reads (`skills/control-library/SKILL.md`), and the two deterministic controls as data the scanner loads (`skills/control-library/patterns.json`) rather than as regexes buried in `scan.py`. Scope, which paths are in PCI scope, lives once in `.compliance.yml`, read by both gates. Engineering owns only the mechanism: the hooks, the agent wiring, and the report renderer. So AppSec can tighten a rule or widen the pattern set without touching engineering's code, and engineering can change the plumbing without touching a rule. The governance story is then literally true: one owner for every control, a different owner for the machinery, instead of a diagram that claims it while the deterministic rules actually live in the code.

I did not start here. The first version had the CTRL-1/CTRL-2 regexes hardcoded in `scan.py`, and the README claimed AppSec owned the controls while half of them sat in engineering's Python. Writing that sentence down was what exposed the gap: if AppSec cannot change a secret pattern without an engineer, they do not own it. Extracting the patterns into `patterns.json` beside the skill was the change that made the claim true.

## Hooks, not an MCP server

The assignment lets you pick a hook or an MCP server. The trigger here is local: code being written in the editor, which is exactly what a hook is for. An MCP server earns its place when the plugin has to reach an outside system, a ticketing API or a cloud account, and this one does not. I did not add one for the sake of using more of the platform.

## The turn-end gate had to be safe before it could be useful

Gate 2 fires from a Stop hook, when Claude finishes a turn. Two things can go wrong with that, and both had to be closed off before it was safe to ship:

- A Stop hook that reinjects work can retrigger itself. The hook checks `stop_hook_active` and does nothing on the re-entry, so it cannot loop.
- Firing on every turn would spend model budget for nothing. The hook hashes the in-scope files that changed and records the hash. If nothing in scope changed, or the same change was already reviewed, it stays silent. An empty turn costs zero.

I wrote this test-first (`tests/test_review_gate.py`), because the loop guard and the once-per-change-set logic are the kind of code that looks right and is not. The tests were the deliverable as much as the hook was.

## Proving the deterministic half, measuring the judgment half

The two tiers need two kinds of proof, and conflating them would have been dishonest. Gate 1 is deterministic: a given line either matches a pattern or it does not, so it gets exact golden tests (`eval/hook/test_hook.sh`) that feed crafted write payloads through the hook and assert block or allow, plus a unit test that the patterns come from the control library rather than from code. Those either pass or fail; there is nothing to average.

Gate 2 is a language model making a call, and you cannot assert that its output equals a fixed string. What matters there is the shape of its mistakes. A false positive is the expensive one: cry wolf once on a payments team and they turn the gate off, so the number I care about most is precision. A false negative means a real leak shipped, so recall matters too. Neither is visible from eyeballing a single run, which is the reason the eval set exists at all, to put numbers on those two failure modes instead of hoping.

So `eval/` carries a small labeled fixture, `cases.yml`, where the ground truth is known by construction because I planted it: each case is tagged with the control IDs that should fire, and the clean cases are tagged to fire nothing. `eval/run_eval.py` runs the real `compliance-review` agent over each case with `claude -p`, scores the control IDs it flags against the expected set, and prints precision and recall. It uses the existing login, needs no new credentials, and takes a couple of minutes.

I deliberately did not turn those numbers into a hard pass/fail threshold. The agent is stochastic, so a fixed cutoff would be a flaky test that fails on an unlucky run and trains you to ignore it, which is the same trap as a noisy gate. Golden tests for the deterministic half, a measured eval for the probabilistic half: the right instrument for each, with no false precision pretending the two are the same kind of check.

## Where I had to steer Claude Code

The Stop-hook contract was the sharpest example. When I asked how the payload and the reinjection field worked, I got a confident, detailed answer that turned out to be invented: field names that do not exist, a control flow that was not real. Rather than build on it, I wrote a probe hook, ran it against the actual version I was on, and read what really came back. Everything above is built on what the probe showed, not on what the model recalled. That became the rule for the whole build: trust the run, not the recollection.

**I constrained the agent hard.** It checks exactly two controls and emits a fixed JSON shape. Left open, it drifted into re-reporting the secrets the hook already blocks, which is double noise, and it editorialized instead of citing a line. Pinning it to two controls and a schema is what makes the review precise and the report renderer deterministic: the agent fills in the specifics, and `render_report.py` supplies every fixed string, so the report reads the same on every run.

## What I would do with more time

Widen the deterministic scanner's pattern set, wire the eval into CI so the agent's precision and recall are tracked over time, and let a repo carry more than one scope profile so a monorepo can gate several services with different rules from one install.