# hogworks

Agent skills for the bugs and slow paths that green tests don't catch. Hedgehogs hunt by night and by scent, and so do these skills.

hogworks is a small collection of skills in the open Agent Skills `SKILL.md` format. They work in Claude Code and in other agents that read that format. Each skill is a method written as plain instructions, so it works in any repository and any language.

## Skills

| Skill | What it does |
| --- | --- |
| [`forage`](skills/forage/SKILL.md) | A read-only lifecycle and concurrency audit. It finds implicit state machines, stale copies of state, and sequential awaits that let one stuck target stall the whole process. |
| [`array`](skills/array/SKILL.md) | A data-oriented design pass over hot code: flat arrays, indices, packed bits, deleted caches, struct-of-arrays, small vectors and bitsets. Every change needs a measured before/after. |

## Install

### Claude Code plugin

```
/plugin marketplace add lance0/hogworks
/plugin install hogworks@hogworks
```

Plugin skills are namespaced, so you invoke them as `/hogworks:forage` and `/hogworks:array`. They also load on their own when a request matches their description.

### Manual copy

Copy a skill directory into your personal skills folder (or into a project's `.claude/skills/`):

```sh
git clone https://github.com/lance0/hogworks
cp -r hogworks/skills/forage hogworks/skills/array ~/.claude/skills/
```

Installed this way, they are `/forage` and `/array`. For other agents, put the `skills/<name>/` directories wherever that agent looks for `SKILL.md` skills.

## Usage

```
/forage both src/server        # lens: state, awaits or both; then optional paths
/array audit src/index         # mode: audit (default) or apply; then paths, types or functions
```

forage never edits code. array also only reports, unless you pass `apply`.

## License

MIT
