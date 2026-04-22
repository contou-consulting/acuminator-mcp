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

From PyPI (recommended for most users):

```powershell
pipx install acuminator-mcp
# or with uv
uv tool install acuminator-mcp
```

From Git (for internal pre-release pulls):

```powershell
pipx install git+https://github.com/contou-consulting/acuminator-mcp.git
```

## Claude / MCP client configuration

Add a stdio server entry pointing at the installed `acuminator-mcp` script.
Example for Claude Desktop (`claude_desktop_config.json`):

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

Claude Code:

```powershell
claude mcp add acuminator acuminator-mcp
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

Releases publish to PyPI via [trusted publishing](https://docs.pypi.org/trusted-publishers/):

1. Bump `version` in `pyproject.toml` and `src/acuminator_mcp/__init__.py`.
2. Commit and push.
3. `git tag vX.Y.Z && git push --tags`.
4. The `Release` workflow builds and publishes; a GitHub release is created automatically.

One-time PyPI setup: configure a trusted publisher for `contou-consulting/acuminator-mcp`
on PyPI with workflow `release.yml` and environment `pypi`.

## License

MIT — see [LICENSE](LICENSE).
