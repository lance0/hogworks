---
name: array
description: Review or rewrite hot code using data-oriented design. The seven questions are: flat arrays instead of hash tables, indices instead of pointers, hot bits packed into an index, redesign instead of caching (delete caches), struct-of-arrays instead of array-of-structs, inline-capacity small vectors instead of heap lists, and bitsets instead of bool arrays. Use when the user types `/array`, asks for a "data-oriented review" or "data-oriented design pass", asks "how do we rewrite this to better leverage data-oriented design", "replace these hash tables with a flat array", "make the pointers indices", "should this be SoA", "delete the caches and make it faster", "use a bitset" or "use small vectors", or wants a memory-layout or cache-locality pass on hot paths. Works in any language (Rust, C/C++, Zig, Go, Java/C#). By default it audits and reports; with `apply` it rewrites in a worktree, and every change needs a measured before/after.
argument-hint: "[audit|apply] [paths, types or hot functions...]"
---

# Array: data-oriented review

Shape the data around what the hot loop actually touches. Every question below is a lens to apply to the code, not a rule to apply blindly. A finding needs (a) a hot path that touches the data, (b) the layout cost (bytes per element, pointer chases, hash probes, allocations per operation, branches), and (c) a measured win once applied. Without a measurement it is a candidate, not a change.

Arguments:
- **Mode:** `audit` (default; read-only, produces a report) or `apply` (rewrites in an isolated worktree, one change per commit, each with a measured before/after).
- **Scope:** paths, type names or hot functions. With no scope, run **Find the hot data** first.

## Ground rules

- **Profile before you touch anything.** Start from a profile or a benchmark (perf, cachegrind, `perf stat` cache-misses, Criterion or the language's harness, allocation counts). Rank the candidates by measured time, not by how "un-DOD" the code looks.
- **Keep correctness constant.** Behaviour, ordering and error handling must not change. The existing tests must pass unchanged. Add `size_of`/`static_assert` layout pins for any type you shrink.
- **Linear in untrusted input.** Never trade a bounded structure for one an attacker can blow up. Examples: an index space sized from network input with no cap, or a bitset sized from an unvalidated maximum.
- **Measure on the same host, against a same-source control,** alternating A/B runs. Report the bars and any noise. A change that doesn't move the number gets reverted. Record that it was a non-win so nobody tries it again.
- **Respect public API and compatibility surfaces.** A layout change behind a stable API is fine. A change to the API itself needs its own decision.
- **Check the project's history first.** Look for perf notes, benchmark results, ADRs and tracker items about "what was not the bottleneck", so you don't re-chase a known dead end.

## Find the hot data

1. Get a profile of the representative workload, or read the project's existing benchmark results.
2. For the top functions, list the types they iterate or look up. For each type record:
   - its `size_of` and padding;
   - which fields the hot loop reads;
   - how many elements there are;
   - how it is allocated (per element or bulk);
   - how lookups work (hash, tree, linear scan, pointer chase).
3. That table is the work list. A type nobody iterates in a hot loop is out of scope, however un-DOD it looks.

## The lenses

Apply each lens to every type on the work list, and record a verdict for each.

### 1. Hash table → flat array with a dense index
- **Ask:** are the keys allocated by us (IDs, handles, peer or member numbers) or bounded and dense? If so, a `Vec<T>` indexed by a `u32`, or a slot map with a generation counter for reuse safety, replaces hashing, probing and the key storage.
- **Keep the hash table when:**
  - keys come from outside and are sparse (prefixes, strings, addresses);
  - the key space is attacker-controlled;
  - lookups are rare.
- **Intermediate step:** intern the external key once at the boundary into a dense ID. Inside the system everything then uses the ID.
- **Evidence:** count probes per operation before and after, and compare the memory per entry.

### 2. Pointer → index into the array
- **Ask:** do `Box`, `Rc`, `Arc`, `*T` or references to siblings in a collection exist mainly to link elements together? If so, replace them with `u32` (or `u16`) indices into the owning array.
- **Gains:** half or a quarter of the size of a pointer, no per-node allocation, trivially serializable, no lifetime or borrow fights, and a contiguous walk.
- **Watch for:** stale indices after removal. Use generations, tombstones or swap-remove with a fix-up, and pin the reuse rule in a test.

### 3. Pack hot data into the index's upper bits
- **Ask:** does the hot path load the element only to read 1–8 bits (kind, flags, small enum, family)? If so, keep those bits in the index's spare high bits so the check needs no load.
- **Requires:** a proven maximum element count that leaves room, enforced at insertion (fail closed, never wrap). Write the encode and decode in one place with a round-trip test and a boundary test at the maximum count.
- **Skip when:** the bits change after the index is handed out. Each copy of the index would then go stale.

### 4. Caching is a symptom: redesign, then delete it
- **Default stance:** no new caches. Treat every existing cache as a finding. A cache means the underlying computation or layout is too slow, and it adds invalidation state, memory, and a second source of truth that drifts. That is the stale-copy bug class.
- **For each cache, ask:**
  - What is the uncached path's cost?
  - Why is it slow (layout, repeated parsing, pointer chasing, allocation, an algorithm with the wrong complexity)?
  - What would make the uncached path as fast as the cache hit?

  Typical answers:
  - precompute at the boundary into a compact form;
  - change the representation so the lookup is an index;
  - batch the work;
  - sort for locality;
  - fix the complexity.
- **Count the full cost of a hit.** A cache hit is not free. Answering "is this entry still valid?" usually means:
  - hashing the key or inputs;
  - system calls for metadata (`stat`, mtime, inode, size);
  - deserializing the stored value, and serializing it again on write;
  - a lock or atomic around shared state.

  Measure the hit path including all of that. It often costs more than a design fast enough to need no cache at all.
- **Invalidation is a security surface.** A stale or poisoned entry can serve something that should have been rejected:
  - an authorization decision;
  - a validation verdict (RPKI, signatures);
  - a parsed config;
  - a resolved path or a file whose contents changed between check and use (TOCTOU).

  Flag every cache whose key leaves out an input the result depends on, and every cache that crosses a trust boundary.
- **Delete the cache once the redesigned path matches the cache's hit latency on the benchmark,** measured with validation included. Report any cache you can't match yet, with the number the redesign has to beat.
- **Cache-aside sprawl (Redis, memcached, an in-process LRU in front of a store).** Putting a cache in front of a slow read is easy. It looks fast in a benchmark because the benchmark fetches only a few unique keys. Then the pattern spreads: get, miss, fetch, set, a TTL, and invalidation hooks in every write path.
  - Grep for the pattern and count the sites.
  - For each site, measure the production hit rate against the number of distinct keys, and the miss-path latency.
  - A high hit rate over a small working set means the source is slow at its own job. Fix the source: an index, a precomputed or denormalized table, a better query shape, or a data layout the read is a lookup into.
  - A low hit rate means the cache adds a network hop, serialization and an invalidation risk, and its misses are paid anyway.
  - The goal is a source fast enough that nobody reaches for the cache.
- **Your own database is not a remote system.** If you own the store behind a Redis cache, the cache is a symptom of a slow design, and the exemption below doesn't cover it.
- **Remote results.** A cache of results from a system you don't own (network fetches, DNS, another service's answers) may stay only if a fresh fetch truly costs more than the full hit cost above. Even then, audit what the validation costs and check its invalidation for security. A cache of local disk reads or of your own computation gets no exemption.

### 5. Array of structs → struct of arrays
- **Ask:** does the hot loop read a few fields of many elements? If so, split those fields into parallel arrays (or a hot/cold split: hot fields in one array, cold ones in another indexed the same way). Then every cache line the loop pulls in holds only useful bytes, and the loop can vectorize.
- **Keep AoS when:**
  - the loop uses most fields of each element;
  - access is random, one element at a time;
  - the element is already small (≤ 16 bytes).
- **Tools:** Zig `MultiArrayList`, Rust `soa_derive` or hand-written parallel `Vec`s, C++ a struct of `std::vector`s, ECS-style tables.
- **Evidence:** bytes touched per element per pass, and cache misses before and after.

### 6. Heap list → inline-capacity small vector
- **Ask:** are most instances small, with a known typical length (p50/p99)? If so, use a small vector with inline capacity at about p95 so the common case does no allocation. Rust has `SmallVec<[T; N]>` and `ArrayVec` for a hard cap; C++ has `small_vector` and `boost::container::static_vector`; Zig has `BoundedArray`.
- **Measure the length distribution first.** A badly chosen N inflates every instance and spills often anyway. Check that the enclosing type's size doesn't grow on a hot array; a larger struct can cost more than the allocation it saves.
- **Hard cap:** prefer a fixed-capacity array with an explicit refusal past N when the protocol bounds the length.

### 7. Array of bools → bitset
- **Ask:** is it a `Vec<bool>`, `[bool; N]`, a set of small integers, or several bool fields per element? If so, use a bitset (`u64` words, `fixedbitset`/`bitvec`, `std::bitset`, a `u8`/`u32` flags field). That is 8× denser, and set operations and "find the next set bit" become word operations (`trailing_zeros`, `popcount`).
- **Per element:** fold several bool fields into one flags integer; this is also lens 3's raw material.
- **Watch for:** C++ `std::vector<bool>` is already a bitset, with proxy-reference pitfalls. Concurrent writers to the same word need atomics or partitioning.

### Also check while you're there
- **Size and padding.** Reorder fields, shrink IDs (`u64` → `u32`) and use enum niches. Pin the result with a `size_of` assertion.
- **Allocation per operation.** Use arenas or bump allocation per batch, and reuse buffers instead of a `Vec::new()` in the loop.
- **Branches in hot loops.** Sort or partition by kind first, then run a tight loop for each kind.
- **Interning repeated values** (strings, attribute sets) so they are compared by ID.
- **Iteration order versus memory order.** Sort or compact so the walk is sequential.

## Output

**Audit** writes `<scratch>/array-<date>.md` containing:
- the profile source and the workload;
- the hot-data table (type, size, element count, hot fields, lookup and allocation pattern);
- per lens, a verdict for each type: **apply** (with the expected win and how to measure it), **skip** (with the reason, e.g. external keys, cold path, already small) or **caches** (each with the redesign that would replace it and the hit-path number it must beat);
- a ranked plan, biggest measured cost first, one change per item.

**Apply** works in an isolated worktree on a branch:
- One lens change per commit, with the existing tests passing and new layout or round-trip tests.
- Each commit's message or the PR body carries its measurement: same host, alternating A/B against the parent, bars and noise.
- Changes that don't move the number are reverted and recorded as non-wins.
- No public-API change without a separate decision.
- The final summary lists each change with its measured delta, the caches deleted, and the caches kept, each with the reason.

## Prior art

Andrew Kelley, "A Practical Guide to Applying Data-Oriented Design" (Handmade Seattle 2021): indices over pointers, SoA via `MultiArrayList`, and storing hot data in the upper bits of an index. Mike Acton, "Data-Oriented Design and C++" (CppCon 2014). On rustbgpd, a pass of this kind over the RIB, the wire decoder and the policy engine recorded which lenses paid off and which were dead ends before any change was made.
