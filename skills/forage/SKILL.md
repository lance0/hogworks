---
name: forage
description: >-
  Read-only lifecycle and concurrency audit that forages for two defect classes green tests rarely catch. (1) Implicit state machines are state spread across bools, Options, sets and counters with no named combined state, along with the stale copies they leave behind. (2) Sequential awaits over N independent targets inside actors or fan-out loops, which turn one stuck peer into a stall of the whole process. Use when the user invokes forage, asks for a "lifecycle audit", asks to "find the implicit state machines", "find stale copies", "audit sequential awaits", "find hidden stalls", or "find async calls that should be concurrent", or wants a lifecycle or concurrency correctness sweep. Works in any language (Rust/tokio, Go, TS/Node, Python asyncio, Java). Produces verified findings and proposed tickets, never edits.
---

# Forage: lifecycle audit

Find the bugs that live *between* the variables and *between* the awaits. Each piece of code looks correct on its own; the bug is in the combination. Both lenses are read-only code traces. Fixes are separate work, and each one starts with a test that fails before the fix.

Arguments: the lens (`state`, `awaits` or `both`, default `both`) and an optional scope. With no scope, run **Scope** below.

## Available tools

Use the host agent's available file, search, and shell tools. If tracker access, profiling tools, or report-file writes are unavailable, state the limitation and report only what you can verify; return the report in chat when needed. Never invent tracker checks or measurements.

## Ground rules

- **Read-only.** Read from the default branch (`git show origin/<main>:<path>` or a detached worktree in a scratch dir). No edits, and no builds unless the user allows them. Many machines are shared.
- **Enumerate, then triage.** A sweep is only as good as its enumeration. Grep every writer of each field and every await in each loop, and report the counts (found and triaged). If a region was classified by shape rather than read line by line, say so.
- **Refute before reporting.** Before calling anything a defect, look for the guard, timeout, try_send, spawn, actor serialization or bounded N that makes it impossible. Prove the triggering input has a **production emitter**: a state that only a test can reach is not a finding. A false positive costs a review round. Concurrency inside a single actor is a common false premise, because an actor that is awaiting does not poll its own mailbox.
- **Dedupe.** Search the tracker in *every* state, including Done and Canceled, and the project's known non-issues. Cite the duplicates you checked.
- **No speculative refactors, and no module splits.** A refactor finding counts only if it deletes code or makes an illegal state unrepresentable.
- **Never break an ordering contract.** Wire or message order per peer, "marker only after the data it covers", actor serialization, commit points and fences. An await that enforces order is correct as written.

## Scope

1. Find the long-lived owners: actors, managers, supervisors, session tasks, the config/transaction layer, startup and shutdown. Use `rg -n 'loop \{|select!|for .* in .*\.await|while let .*recv|spawn' -g '*.<ext>'` or the language's equivalent, plus the README or architecture docs.
2. Rank the subsystems by blast radius: whatever carries live traffic, then whatever operators trigger in bulk (reload, global toggles, bulk delete), then shutdown and restart, then everything else.
3. If more than about 3 subsystems are in scope and subagents are available, fan out **one read-only agent per subsystem**, using the brief template at the bottom. Re-trace every A they report before accepting it. Without subagents, audit the subsystems sequentially.

## Lens 1: implicit state machines (`state`)

For each owner, list the fields that describe *lifecycle*, not data: bools, Option/nullable handles, membership in sets or maps keyed by entity, counters, timestamps, generation numbers, "pending", "owed", "dirty", "forced", "held", "exited". Then, for each cluster:

1. **Writers.** List every set and clear site with file:line. Grep the whole repo, not just the owner's file.
2. **Implied states.** Name the combined states the fields encode. Mark any combination the code assumes is impossible, and note whether anything actually prevents it.
3. **Transitions.** For each one, name its trigger. Flag any exit that **only a timer or poll** takes ("stuck until the next tick"); usually an event should take it.
4. **Wakeups.** Flag any state change that doesn't wake the waiters or consumers that depend on it, for example "degraded" being set without notifying the readers.
5. **Cancellation.** When a request or task is dropped mid-transition, check what is left set.
6. **Disagreeing lists and collapsed facts.** Look for several independently built lists of "who takes part in X" (for example, who gets a restart flag, who gets grace, who is waited on) and check that they agree. Look for a reduction that folds two independent facts into one enum value, such as "ours present" + "foreign present" → `Foreign`, and then acts on only one of them.
7. **Stale copies: the most productive check.** For every *copy* of a piece of state (a cache, a dead-letter or held record for a disconnected entity, a local `config` captured at boot, a sampled mtime or timestamp, a snapshot taken before a long operation), list the owner's **update** and **clear** paths. Check that each one reaches the copy. Also check whether the shared teardown seam clears everything that the one "full" teardown clears.

Classify each cluster:
- **A, reachable defect.** Give a concrete interleaving or input sequence, the wrong observable result, and the test that would turn red.
- **B, refactor candidate.** An enum or typed set that deletes the hand-written combination checks or makes the bad state unrepresentable. Give a size estimate and the risk it removes.
- **C, checked and fine.** One line on why.

## Lens 2: sequential awaits (`awaits`)

This hunts **stalls**, not throughput. The target is a loop over N independent things (peers, sessions, members, tables, ports, tenants) that awaits each one in turn, so one stuck target or a large N stalls the owner.

1. **Enumerate.** Find every await inside a `for` or `while` body, with the language's own patterns (`\.await`, `await `, `<-ch`, `.get()`/`.join()`), excluding test code. Split them into: the loop's own event wait (recv/tick/sleep, which is fine), awaits inside actor run loops and retry loops, and awaits inside `for` or `while` loops over a collection. Triage every loop in the last group.
2. **Find the driver condition.** Work out what makes one iteration slow. Usually it is a target that **stops draining its command channel** while it is itself blocked, for example a session parked sending to a full downstream mailbox. Then every command to it costs the full deadline. The project's own past stall bugs usually show this condition.
3. **Bound it.** The cost is N × the per-iteration deadline. Compare that with what it starves: a readiness or health deadline, a watchdog, a hold timer, or a peer's keepalive. Note whether readiness is served during the wait.
4. **Fan-out sends.** A loop that does `send().await` to each target is head-of-line blocked by the first full channel. Check whether the project prefers refusing over waiting here (`try_send`).

Classify each site:
- **A, stall defect.** Give a reachable N × deadline or head-of-line scenario, with numbers.
- **B, perf candidate.** The awaits are independent and running them concurrently would save time, but no stall results. Nothing changes until a measurement shows the win.
- **C, correct as sequential.** Name the ordering contract, or note that N is small and bounded.

For every proposed fix, **bound the concurrency**: a shared deadline window, `JoinSet` or `buffer_unordered(k)`, or a semaphore. An unbounded `join_all` over network- or user-controlled N is a new defect. Keep the order within each target, for example "toggle before refresh" and "delete before add". Prefer the patterns the codebase already uses for this class.

## Output

1. **Report file** in the scratch dir, for example `<scratch>/forage-<lens>-<date>.md`. It contains:
   - the commit audited;
   - enumeration counts;
   - a table of every candidate (subsystem, variables or loop, class, one-line verdict);
   - a section per A or B finding with file:line evidence, the scenario, and the proposed red test and fix;
   - one line per C finding;
   - a coverage caveat;
   - sources for any prior art.
2. **Pattern note.** Add one paragraph on what most of the A findings share. On rustbgpd, pass 1 found that 4 of 5 were stale copies, and all 3 stall bugs came from one driver condition. The shared pattern is what improves the next pass.
3. **Triage.** The auditor never files tickets. The person running the audit verifies the A findings by spot-reading at least the key line. Then file one ticket per independent fix, with:
   - the defect, consequence and acceptance;
   - "verified by read" or "unverified" stated honestly;
   - a requirement for a regression test that fails on the current default branch before any code change.

   File each B as a gated improvement ticket, or decline it in a comment. Group A fixes that share one mechanism and one test harness into one PR.
4. **Second pass.** Run one only if pass 1 found real A defects. Order it by blast radius, and add whatever the pass 1 pattern note taught to the method.

## Agent brief template (one per subsystem)

```
Read-only <lens> audit of <subsystem paths> in <repo> at origin/<main>.
No edits, no builds. Read via `git show origin/<main>:<path>` or a detached worktree in <scratch>.
Read the tracker issue <ID> and these prior defects in this class: <IDs>.
Method: <paste the lens steps above>. Enumerate before triaging and report the counts.
Refute every A before reporting it: find the guard, timeout, bounded N, or actor serialization
that would prevent it, and prove the triggering input has a production emitter.
Must not break: <ordering contracts>. Out of scope: module splits, speculative refactors.
Dedupe against: <tracker search, all states>.
Deliver: <scratch>/<file>.md (candidate table, A/B sections with file:line, C one-liners,
coverage caveat). Reply with the class counts and two lines per A. File no tickets.
```

## Prior art

- rustbgpd (2026-11), lens 1: pass 1 found 5 A, 4 B and 53 C. Four of the five A findings were stale copies, of these kinds:
  - a force flag cleared only in the full teardown, not in the shared seam;
  - a dead-letter flag that a bulk clear never reached;
  - a boot-time `config` local that only SIGHUP refreshed;
  - an mtime sampled at adoption instead of at read.
- rustbgpd, lens 2: 230 loops were triaged into 3 A, 7 B and the rest C. All three A findings shared one driver: a session parked on a full RIB mailbox stops reading commands, so per-peer 500 ms commands become N × 500 ms. The fix was a shared window, a bounded JoinSet, and serving readiness during the wait.
