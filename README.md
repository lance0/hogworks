![hogworks — a pixel-art hedgehog wizard with a glowing wand beneath a starry castle sky](assets/hogworks.png)

# hogworks

Skills for finding the bugs and slow paths that green tests miss. Portable Agent Skills for **Claude Code, Codex, Cursor, and other compatible coding agents**.

| Skill | Use it for | Modes |
| --- | --- | --- |
| [forage](skills/forage/SKILL.md) | Lifecycle bugs, stale state, and sequential awaits that stall independent work | `state`, `awaits`, or `both` (default). Read-only: findings with source evidence and proposed tickets, each requiring a failing regression test |
| [array](skills/array/SKILL.md) | Hot data layouts, allocations, caches, and pointer chasing | `audit` (default, read-only) or `apply` (changes with before/after measurements) |
| [nibble](skills/nibble/SKILL.md) | Over-fetching (whole rows, big jsonb, N+1) and work repeated per call (regexes, parsing, constants) | `audit` (default, read-only) or `apply` (changes with before/after measurements) |

## Install

With Node.js and npm installed, run:

```sh
npx skills add lance0/hogworks
```

In an interactive terminal, the installer lets you choose skills and coding agents. It installs into the current project by default. Add `-g` to make the skills available across projects:

```sh
npx skills add lance0/hogworks -g
```

For scripts or a specific target, use `--skill <name>` (repeat for each skill you want) and `-a <agent>` (for example, `-a codex`). See the [supported agents and install paths](https://github.com/vercel-labs/skills/blob/main/docs/agents.md) for your agent's identifier.

Restart your agent if the new skills do not appear. Choose either the CLI install or the Claude Code plugin below to avoid duplicate skills.

## Use

### Claude Code

```text
/forage both src/server
/array audit src/index
/array apply src/index
/nibble audit src/routes
```

### Codex

Mention the skill with `$` in your prompt, or select it from the skills picker:

```text
$forage both src/server
$array audit src/index
$array apply src/index
$nibble audit src/routes
```

### Cursor

In Agent chat, type `/` and select a skill, then add the mode and scope:

```text
/forage both src/server
/array audit src/index
/array apply src/index
/nibble audit src/routes
```

### Other coding agents

Select the skill using your agent's skill picker, or ask naturally, for example: “Use forage to audit lifecycle and concurrency in src/server.”

Invocation syntax varies by agent; `/forage` and `$forage` are not universal commands.

Each skill's modes are listed in the table above. Paths, types, and subsystem names narrow the scope; omit them to let the skill identify candidates.

## Compatibility

All skills use the same portable `skills/<name>/SKILL.md` files. No agent-specific copies, MCP server, or runtime dependencies are required by the skills themselves. The installer needs Node.js; audits need access to your source, and `apply` modes need your project's tests and profiling tools.

The Claude Code plugin manifest is only an alternative installer for Claude Code. Other agents use the skill files directly through the skills CLI. Agent permissions still apply; available tools and models affect the depth of a review.

The shared format and installation discovery are checked with the skills CLI. Support for installation does not mean every agent has been tested end to end. This does not guarantee identical audit results across agents. See the official [CLI agent support](https://github.com/vercel-labs/skills/blob/main/docs/agents.md), [Codex skills](https://developers.openai.com/codex/skills), and [Cursor skills](https://cursor.com/docs/skills) documentation.

### Claude Code plugin alternative

Run inside Claude Code:

```text
/plugin marketplace add lance0/hogworks
/plugin install hogworks@hogworks
```

This installation prefixes each skill with the plugin name, for example `/hogworks:forage` instead of `/forage`.

## Maintain your install

```sh
# Preview the available skills without installing
npx skills add lance0/hogworks --list

# Check installed skills for updates
npx skills check

# Update installed skills (including skills from other repositories)
npx skills update
```

## Contributing

Edit the canonical files under `skills/`. Keep findings tied to reachable code and performance claims tied to measurements. Include a concrete example when reporting a problem or proposing a change.

CI checks YAML frontmatter, required names (up to 64 lowercase letters, digits, or hyphens, matching the directory) and descriptions (up to 1,024 characters), and non-empty instructions on pushes and pull requests. Run the same check locally, then confirm CLI discovery:

```sh
python -m pip install PyYAML==6.0.3
python scripts/validate-skills.py
npx skills add . --list
```

## License

[MIT](LICENSE)
