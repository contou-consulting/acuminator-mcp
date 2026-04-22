# acuminator-mcp

An [MCP](https://modelcontextprotocol.io) stdio server that exposes the
[Acuminator](https://github.com/Acumatica/Acuminator) static analyzer for
Acumatica ERP customizations. Lets an AI agent:

- run Acuminator against a `.csproj` or `.sln`,
- analyze a raw C# snippet against a reference Acumatica project,
- and look up official documentation for any `PXNNNN` diagnostic code.

## Requirements

- **Windows** with **.NET Framework 4.8** (the Acuminator console runner is
  `Acuminator.Runner.NetFramework.exe` — `net48`-only).
- Python 3.10 or newer.

The runner itself is downloaded and cached on first use
(`%LOCALAPPDATA%\acuminator-mcp\runner\v<version>`); no manual install required.

## Installation

Distributed internally via GitHub — not published to PyPI. Employees need
read access to `contou-consulting/acuminator-mcp` (org members already do).

**From Git (simplest, tracks a branch or tag):**

```powershell
# latest main
pipx install git+https://github.com/contou-consulting/acuminator-mcp.git

# pin to a release
pipx install git+https://github.com/contou-consulting/acuminator-mcp.git@v0.1.0
```

`uv tool install` works the same way, swap `pipx install` for `uv tool install`.

**From a GitHub Release wheel** (no git clone, faster):

```powershell
pipx install https://github.com/contou-consulting/acuminator-mcp/releases/download/v0.1.0/acuminator_mcp-0.1.0-py3-none-any.whl
```

First-time `git+https` clones need `gh auth` or a PAT. The easiest setup is:

```powershell
gh auth login
gh auth setup-git
```

## Using it in Claude Code

Install the server once (`pipx install ...` above), then register it with
Claude Code. Pick the scope that matches how you want the server to appear:

| Scope | Where it lives | When to use |
|---|---|---|
| `local` (default) | `.claude/settings.local.json` in the current project | You only want it in this repo for yourself |
| `project` | `.mcp.json` at the repo root, checked into git | Share it with everyone on the team who clones the repo |
| `user` | `~/.claude.json` | You want it everywhere, on every project |

**Register the server:**

```powershell
# user-scoped: available in every project on this machine
claude mcp add --scope user acuminator acuminator-mcp

# project-scoped: committed to .mcp.json so teammates get it automatically
claude mcp add --scope project acuminator acuminator-mcp
```

**Point the snippet tool at a reference Acumatica project** (required for
`analyze_snippet`; optional but harmless otherwise):

```powershell
claude mcp add --scope user acuminator acuminator-mcp `
  --env ACUMINATOR_MCP_REFERENCE_PROJECT=C:\src\my-acumatica-ext\MyExt.csproj
```

**Verify it's connected** — inside a Claude Code session:

```
/mcp
```

You should see `acuminator` listed as *connected* with three tools:
`analyze_project`, `analyze_snippet`, `get_diagnostic_docs`.

**Example prompts** once it's wired up:

- *"Run acuminator on `C:\src\MyExt\MyExt.csproj` and explain any PX1014 hits."*
- *"Use the snippet analyzer on this DAC and look up the docs for any
  diagnostics it reports."*
- *"What does PX1030 mean and how do I fix it?"*

### Claude Desktop (for reference)

If you're also using the desktop app, add a stdio entry in
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "acuminator": {
      "command": "acuminator-mcp",
      "env": {
        "ACUMINATOR_MCP_REFERENCE_PROJECT": "C:\\src\\my-acumatica-ext\\MyExt.csproj"
      }
    }
  }
}
```

## Tools

### `analyze_project`

Run Acuminator against an Acumatica `.csproj` or `.sln`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_path` | `string` | — | Absolute path to the `.csproj` or `.sln`. |
| `isv_mode` | `bool` | `false` | Stricter analysis; promotes some warnings to errors. |
| `enable_px1007` | `bool` | `false` | Require XML docs on DACs/DAC fields. |
| `disable_px1099` | `bool` | `false` | Disable the banned-APIs diagnostic. |
| `enable_info_diagnostics` | `bool` | `false` | Include `Info`-severity diagnostics. |

Returns `AnalysisResult`:

```json
{
  "code_source": "C:\\src\\MyExt\\MyExt.csproj",
  "total_diagnostics": 2,
  "diagnostics": [
    {
      "code": "PX1014",
      "message": "DAC should have a primary key",
      "file": "C:\\src\\MyExt\\DAC\\CTCWidget.cs",
      "line": 12,
      "column": 5,
      "project": "MyExt"
    }
  ]
}
```

### `analyze_snippet`

Analyze a raw C# snippet. Because Acuminator relies on Acumatica Framework
types for semantic analysis, snippets are planted into a user-supplied
**reference project** whose references already resolve `PX.Data` etc.

Configure the reference project in one of two ways:

1. Set `ACUMINATOR_MCP_REFERENCE_PROJECT` to an Acumatica `.csproj`.
2. Pass `reference_project_path` to the tool call.

The server writes a temp `.cs` file into the project directory, runs the
analyzer, and cleans up — so point it at a scratch/test project, not a
production project you have locks on.

### `get_diagnostic_docs`

Fetches the markdown docs for a `PXNNNN` code from
`https://raw.githubusercontent.com/Acumatica/Acuminator/refs/heads/master/docs/diagnostics/<code>.md`
and caches to disk.

## Environment variables

| Variable | Purpose |
|---|---|
| `ACUMINATOR_MCP_RUNNER_VERSION` | Pin a different runner release (default: `4.0.1`). |
| `ACUMINATOR_MCP_CACHE` | Override the on-disk cache root. |
| `ACUMINATOR_MCP_REFERENCE_PROJECT` | Default reference project for `analyze_snippet`. |

## Development

```powershell
git clone https://github.com/contou-consulting/acuminator-mcp.git
cd acuminator-mcp
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest
.venv\Scripts\ruff check .
```

## Releasing

1. Bump `version` in `pyproject.toml` and `src/acuminator_mcp/__init__.py`.
2. Commit and push.
3. `git tag vX.Y.Z && git push --tags`.
4. The `Release` workflow builds the sdist + wheel and creates a GitHub release
   with both attached. Employees can then `pipx install` the wheel URL or pin
   their `git+https` install to the new tag.

## License

MIT — see [LICENSE](LICENSE).
