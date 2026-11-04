---
name: nibble
description: >-
  Find and remove hot-path waste: data fetched wider than the code reads, and work repeated per call that could be done once. Lenses: select only the columns you read, promote hot keys out of large JSON/jsonb columns, batch N+1 queries, count and test existence in the store, hoist regexes and expensive constants out of functions and loops, parse URLs/JSON/dates once, replace linear lookups in loops with a Map or Set, and drop serialization round trips and eager log formatting. Use when the user invokes nibble, asks to "select only what we need", "stop loading whole rows", "remove unnecessary new URL() parsing", "move regexes to module level", "promote this jsonb key to a column" or "fix the N+1", or wants an over-fetching or repeated-work pass. Any language or store (TS/JS, Python, Go, Rust, Java, SQL/Postgres, ORMs). Audits by default; `apply` changes one finding at a time with proof the site is hot and a measured before/after.
---

# Nibble: take only what you need, and only once

Two kinds of waste survive every green test suite:

- **Over-fetch:** loading more data than the code reads. That means whole rows for two fields, whole documents for one key, and whole tables to count them.
- **Repeated work:** redoing on every call what could be done once. That means compiling the same regex, parsing the same URL, and building the same formatter.

Each instance is small, and fixing a few does little. The value is in finding *every* instance on the hot paths, and then fixing only the ones that matter.

A finding needs three things: (a) evidence that the site is hot, (b) the waste per call (bytes fetched but unread, parses, allocations, round trips), and (c) once applied, a measured win. Without a measurement it is a candidate, not a change.

Arguments:
- **Mode:** `audit` (default; read-only, produces a report) or `apply` (changes code in an isolated worktree, one finding per commit, each with a measured before/after).
- **Scope:** paths, routes, handlers, queries or tables. With no scope, start with **Find the hot paths**.

## Available tools

Use the host agent's file, search and shell tools. If profiling, query logs, `EXPLAIN` or report-file writes are unavailable, say so and report only what you can verify. Return the report in chat if you can't write the file. Never invent measurements.

## Ground rules

- **Hot first.** A site is hot when one of these holds:
  - a profile, a slow-query log or `pg_stat_statements` ranks it;
  - it runs per request, per row or per message on a path you can show is busy.

  A one-off admin script or a startup path is out of scope, however wasteful it looks.
- **Enumerate, then rank.** Grep every site that matches a lens, not just the first few. A sweep is only as good as its enumeration. Rank by measured cost.
- **Behaviour stays constant.** Results, ordering, errors, validation and security checks must not change. Existing tests must pass unchanged. Each lens below names the trap that makes a careless fix wrong; check it before every change.
- **Measure on the same host against the same-source parent,** alternating A/B runs. Report the noise. A change that doesn't move the number gets reverted and recorded as a non-win.
- **Schema changes are migrations, not refactors.** Promoting a column, adding an index or changing a query's shape in a shared database gets a written proposal: backfill, dual-write, cutover, rollback. Don't make a silent edit.

## Find the hot paths

1. Collect what exists:
   - an application profile;
   - an APM trace;
   - the slow-query log or `pg_stat_statements` (sort by total time, then by calls);
   - request rates per route;
   - the project's benchmarks.
2. For the top routes, handlers and queries, record:
   - calls per request;
   - the rows and bytes returned compared with the fields actually read;
   - the parses and constructions per call;
   - queries per request (N+1 shows up here).
3. That table is the work list. Apply every lens to every entry.

## The lenses

### 1. Load whole rows, read two fields → select only what you read
- **Find:** `SELECT *`, ORM calls that hydrate whole entities (`findOne`, `.get()`, `Model.objects.get`, `find_by`), and repository methods that return full records to callers that read one or two fields.
- **Fix:** select the columns you read. In an ORM use `select`/`only`/`values`/`pluck`/`attributes`, or a projection type. Large columns (text, jsonb, bytea) matter most, because they force TOAST reads and wire transfer.
- **Trap:** before narrowing, trace every consumer of the returned object, including serializers, templates, `toJSON`, ORM hooks and lazy relations. A field you dropped then fails at runtime, often as `undefined` or a lazy-load query, not a compile error. Prefer a narrow typed projection, so a missing field fails to compile. Don't hand a partial entity to code that expects a full one.

### 2. Hot key inside a large JSON/jsonb column → promote it to a real column
- **Find:** queries or code that read one key (`data->>'status'`, `doc["status"]`) from a large JSON, jsonb or document column on a hot path. Filtering, sorting or joining on such a key is the strongest signal.
- **Fix:** make the key a real typed column, with an index if you filter on it, and stop fetching the blob on that path. Large jsonb is costly even when you need one key: the whole value is detoasted and decompressed, there are no column statistics, and every update rewrites the whole value.
- **Trap:** two copies of the truth. The proposal must cover the backfill, writing both the column and the key until cutover (or a generated column, which avoids the dual write), every writer of the key (grep all of them), and when the key leaves the blob.

### 3. N+1 queries → batch or join
- **Find:** a query inside a loop over the results of another query. Lazy-loaded relations touched in a loop. Per-item `await fetch(...)` against your own API.
- **Fix:** one `WHERE id = ANY($1)` or `IN (...)` query, a join, the ORM's eager load (`include`, `select_related`/`prefetch_related`, `preload`), or a DataLoader-style batcher.
- **Trap:** batching changes the failure and ordering semantics. One failed item can now fail the batch, and results come back unordered: map them by key and preserve the input order. Bound the batch size, because an unbounded `IN` list from user input is its own problem.

### 4. Counting or existence by loading rows → let the store answer
- **Find:** `len(query.all())`, `rows.length`, `findMany(...).length > 0`, or a full fetch just to test `if (row)`.
- **Fix:** `SELECT count(*)`, `SELECT EXISTS(...)`, `LIMIT 1`, or the ORM's `count`/`exists`.
- **Trap:** a count that was paired with reading the same rows can hide a race once the two are separate queries. Keep them in one query or one transaction if the code depends on them agreeing.

### 5. Expensive constants built per call → hoist to module level
- **Find:** these, constructed inside a function, handler or loop with arguments that never change:
  - regex literals or constructors (`new RegExp`, `re.compile`, `Regex::new`);
  - formatters and collators (`Intl.NumberFormat`, `Intl.DateTimeFormat`, `Intl.Collator`, `DateTimeFormatter`);
  - `new Set([...])` or maps from constant arrays;
  - `TextEncoder`/`TextDecoder`, compiled templates and schema validators (`ajv.compile`, `z.object(...)` built per call), HTTP or database clients, prepared statements.
- **Fix:** build once at module level, or lazily once (`LazyLock`/`OnceLock`, `functools.cache` on a zero-argument factory, `sync.OnceValue`). Rust regexes in a loop are a classic: use `LazyLock<Regex>`.
- **Traps:**
  - **Stateful objects can't be shared naively.** A JS regex with `/g` or `/y` carries `lastIndex` between calls, so a hoisted global regex used with `.test()` or `.exec()` returns alternating results. Drop the flag, reset `lastIndex`, or use `matchAll` or `String.prototype` methods.
  - **Patterns or options built from runtime input can't be hoisted.** Key a small bounded cache by input only when the inputs are few and trusted.
  - **Concurrency.** The hoisted object must be safe to share across threads or requests. Formatters in some runtimes are not.
  - **A hoisted client or connection** changes lifecycle and failure behaviour: reconnects, shutdown, test isolation.

### 6. The same value parsed repeatedly → parse once, pass the parsed form
- **Find:** `new URL(x)` on a string that was already a URL a frame up, or parsed several times in one request. Also `JSON.parse` of the same blob in several places, date parsing in a loop, path normalization repeated per call, `Number()`/`parseInt` of the same field again and again, and decode-modify-encode-decode chains.
- **Fix:** parse at the boundary into a typed value (a `URL`, a struct, a `Date`), pass that inward, and serialize once on the way out. Where the code only needs to join a base and a path, string operations on known-good parts can replace a full parse.
- **Trap:** a parse is sometimes the validation. `new URL()` and `JSON.parse` throw on bad input, and some code relies on that to reject garbage. When you remove a parse, keep an explicit check at the boundary where untrusted input enters. Normalization differs too: `new URL()` lower-cases the host, resolves `..` and percent-encodes, so replacing it with string concatenation must not change the output or open path traversal.

### 7. Linear lookups inside loops → build the index once
- **Find:** `array.find`/`includes`/`indexOf`/`some`, Python `x in list`, or a nested loop matching items from two lists. Each is O(n·m) disguised as one line.
- **Fix:** build a `Map`/`Set`/dict keyed by the lookup field once before the loop, then do O(1) lookups.
- **Trap:** duplicate keys. `find` returns the first match; a map built naively keeps the last. Preserve first-wins (`if (!map.has(k)) map.set(k, v)`), or prove the keys are unique. Small n doesn't need this; measure first.

### 8. Serialization round trips and eager formatting → do the direct thing
- **Find:**
  - `JSON.parse(JSON.stringify(x))` used as a deep clone;
  - `JSON.stringify(a) === JSON.stringify(b)` used as an equality test;
  - stringify used to build cache or map keys;
  - log messages built with string formatting or `JSON.stringify` on a hot path when that log level is disabled;
  - debug-only work that runs in production.
- **Fix:** `structuredClone`, or a typed copy. A field-wise or library equality. A composite key built from the fields. Lazy or structured logging (`log.debug({ obj })`, `if (log.isDebugEnabled())`, `tracing` fields), so formatting happens only when the line is emitted.
- **Trap:** the round trip may be doing something on purpose. It drops `undefined`, functions and class prototypes, and it turns `Date`s into strings. Callers may depend on that, so `structuredClone` is not always a drop-in replacement. Key order makes stringify-equality unreliable anyway; the fix may be correcting a bug, so say so.

### Also check while you're there
- Config or env read and parsed on every request instead of once at startup.
- The same query run twice in one request; fetch it once and pass it down. Prefer this over adding a request-scoped cache.
- Hot queries that `EXPLAIN` shows doing a sequential scan, a sort or a hash over far more rows than they return. Propose the index or the query shape; don't silently add indexes to a shared schema.
- Wide rows with cold large columns on a hot table. Propose moving the cold columns to a side table.
- Middleware doing per-request work only some routes need.

## Output

**Audit** writes `<scratch>/nibble-<date>.md` containing:
- the evidence source and the workload;
- the hot-path table: site, calls per request or second, waste per call, total cost;
- for each lens, every matching site with a verdict:
  - **apply:** the expected win, how to measure it, and the trap checked;
  - **skip:** with the reason (cold path, n too small, the parse is the validation, the pattern depends on input);
  - **propose:** schema or migration changes, with backfill, dual-write and cutover written out;
- a ranked plan, biggest measured cost first, one change per item.

**Apply** works in an isolated worktree on a branch:
- One finding per commit, with existing tests passing and a new test for any trap the change touches. Examples: the `/g` regex reused across calls, a dropped field still being consumed, first-wins on duplicate keys, invalid input still rejected after a parse was removed.
- Each commit's message or the PR body carries its measurement: same host, alternating A/B against the parent, with the noise.
- Changes that don't move the number are reverted and listed as non-wins.
- Schema changes stay proposals, unless the user explicitly asks for the migration.
- The final summary lists each change with its measured delta, plus the sites skipped and why.

## Related

`array` covers data layout in hot loops: flat arrays, indices, struct-of-arrays, and deleting caches. `forage` covers lifecycle state and sequential awaits. When a nibble finding is really a layout or concurrency problem, hand it to the matching skill and don't fix it here.
