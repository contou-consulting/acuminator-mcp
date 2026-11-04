# acuminator-mcp

An [MCP](https://modelcontextprotocol.io) stdio server that exposes the
[Acuminator](https://github.com/Acumatica/Acuminator) static analyzer for
Acumatica ERP customizations. Lets an AI agent:

- run Acuminator against a `.csproj` or `.sln`,
- analyze a raw C# snippet against a reference Acumatica project,
- and look up official documentation for any `PXNNNN` diagnostic code.

**Requirements**

- **Windows** with **.NET Framework 4.8** — `Acuminator.Runner.NetFramework.exe` is `net48`-only.
- **Python 3.10+**.
- **`pipx`** (or `uv`, or any isolated-tool installer). [Install pipx](#install-pipx).
- **`gh` CLI** logged in with access to `contou-consulting` (repo is private).

The runner itself is downloaded and cached automatically on first use at
`%LOCALAPPDATA%\acuminator-mcp\runner\v<version>`.

---

## 1. Install

### Install pipx

If you don't already have `pipx`:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Restart your terminal, then verify: `pipx --version`. (`winget install pipx` and `scoop install pipx` also work.)

### Authenticate with GitHub

The repo is private, so installing needs your GitHub creds on git:

```powershell
gh auth login
gh auth setup-git
```

### Install the server

```powershell
# pin to a release (recommended)
pipx install git+https://github.com/contou-consulting/acuminator-mcp.git@v1.0.0

# or track main
pipx install git+https://github.com/contou-consulting/acuminator-mcp.git
```

`uv` works the same way — swap `pipx install` for `uv tool install`.

Verify the server launches:

```powershell
acuminator-mcp --help   # prints nothing; it's a stdio server. Ctrl+C exits.
```

### Upgrading

```powershell
pipx install --force git+https://github.com/contou-consulting/acuminator-mcp.git@v1.0.1
```

---

## 2. Use

### In Claude Code

Pick the scope that matches how you want the server to appear:

| Scope | Where it lives | When to use |
|---|---|---|
| `local` (default) | `.claude/settings.local.json` in the current project | Just you, just this repo |
| `project` | `.mcp.json` at the repo root, checked into git | Share with everyone cloning the repo |
| `user` | `~/.claude.json` | Everywhere, every project, on this machine |

Register the server:

```powershell
# user-scoped: available in every project
claude mcp add --scope user acuminator acuminator-mcp

# project-scoped: committed to .mcp.json
claude mcp add --scope project acuminator acuminator-mcp
```

Point the snippet tool at a reference Acumatica project (needed for `analyze_snippet`; harmless otherwise):

```powershell
claude mcp add --scope user acuminator acuminator-mcp `
  --env ACUMINATOR_MCP_REFERENCE_PROJECT=C:\src\my-acumatica-ext\MyExt.csproj
```

Verify it connected — inside a Claude Code session:

```
/mcp
```

You should see `acuminator` listed as *connected* with four tools.

### In Claude Desktop

Edit `claude_desktop_config.json`:

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

Restart Claude Desktop.

### Sample prompts

- *"Run acuminator on `C:\src\MyExt\MyExt.csproj` and explain any PX1014 hits."*
- *"Use the snippet analyzer on this DAC and look up the docs for every diagnostic it reports."*
- *"What does PX1030 mean and how do I fix it?"*

### Tools

#### `analyze_project`

Run Acuminator against an Acumatica `.csproj` or `.sln`.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_path` | `string` | — | Absolute path to the `.csproj` or `.sln`. |
| `isv_mode` | `bool` | `false` | Stricter analysis; promotes some warnings to errors. |
| `enable_px1007` | `bool` | `false` | Require XML docs on DACs/DAC fields. |
| `disable_px1099` | `bool` | `false` | Disable the banned-APIs diagnostic. |
| `enable_info_diagnostics` | `bool` | `false` | Include `Info`-severity diagnostics. |
| `disable_suppression` | `bool` | `false` | Also report diagnostics hidden by `<Project>.acuminator` files or `// Acuminator disable once …` comments. |
| `banned_apis_path` | `string` | — | Custom banned-APIs file for PX1099 (format in the [PX1099 docs](https://github.com/Acumatica/Acuminator/blob/master/docs/diagnostics/PX1099.md)). |
| `allowed_apis_path` | `string` | — | Custom allowed-APIs file for PX1099. |
| `max_diagnostics` | `int` | `200` | Cap on the number of locations returned across all groups. |

Returns `AnalysisResult`:

```json
{
  "code_source": "C:\\src\\MyExt\\MyExt.csproj",
  "total_diagnostics": 3,
  "counts_by_code": { "PX1014": 2, "PX1069": 1 },
  "groups": [
    {
      "code": "PX1014",
      "message": "A DAC field must have a nullable type",
      "locations": ["DAC/CTCWidget.cs:12:5", "DAC/CTCWidget.cs:15:5"]
    },
    {
      "code": "PX1069",
      "message": "\"CTCWidget\" DAC must declare the mandatory \"tstamp\", \"CreatedByID\", \"LastModifiedDateTime\" DAC fields",
      "locations": ["DAC/CTCWidget.cs:8:18"]
    }
  ],
  "truncated": false
}
```

The shape is built for small context footprints: hits are grouped by
`(code, message)` so each message appears once, paths are relative to the
analyzed `.csproj`/`.sln` directory, and `line:col` are 1-based. `groups` stops
after `max_diagnostics` locations (largest groups first) and `truncated` flips
to `true`; `counts_by_code` is always complete. The message is usually enough
to act on — reach for `get_diagnostic_docs` only when it isn't.

#### `analyze_snippet`

Analyze a raw C# snippet against a **reference Acumatica project** so Acuminator
sees the full `PX.Data` type environment.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `code` | `string` | — | The C# snippet. May be a full compilation unit (starts with `using` or `namespace`) or just type declarations — see auto-wrapping below. |
| `reference_project_path` | `string` | — | Optional absolute path to the reference `.csproj`. Overrides the env var and auto-discovery. |
| `isv_mode` | `bool` | `false` | Stricter analysis; promotes some warnings to errors. |
| `max_diagnostics` | `int` | `200` | Cap on the number of locations returned. |

The server picks the reference project in this order:

1. Explicit `reference_project_path` argument.
2. `ACUMINATOR_MCP_REFERENCE_PROJECT` env var.
3. Auto-discovery from the server's CWD — walks up looking for any `.csproj`,
   then BFS-scans down (skipping `bin`, `obj`, `packages`, etc). When the MCP
   server is launched with CWD at an Acumatica repo root, this "just works".

**Auto-wrapping.** If `code` doesn't already start with `using` or `namespace`,
the server wraps it with `using PX.Data; using PX.Objects;` and a
`namespace AcuminatorMcp.Snippet { … }` block before analysis. This lets you
submit just a DAC or graph class without boilerplate. Locations come back as
`snippet:line:col` with line numbers already mapped onto your input (the
injected prelude is subtracted). Pass a snippet that starts with `using` or
`namespace` yourself if you need usings the default doesn't include.

Returns only diagnostics that target the snippet, in the same `AnalysisResult`
shape as `analyze_project`. The server writes a temp
`.cs` file into the project's directory, runs the analyzer, and deletes the
file. Consider adding `AcuminatorMcpSnippet_*.cs` to your `.gitignore` in case
a crash ever orphans one.

#### `generate_suppressions`

**Writes into your source tree.** Runs the analysis in Acuminator's
`report-and-generate` work mode, which records every diagnostic found in a
`<ProjectName>.acuminator` suppression file next to each analyzed project
(creating or extending it). Subsequent `analyze_project` runs then report only
*new* issues — the usual way to baseline a legacy project before enforcing
Acuminator in CI. The runner refuses to generate unless the file already
exists and the project lists it as an `<AdditionalFiles>` item, so for a
project that has neither the tool creates the empty file and appends

```xml
<ItemGroup>
  <AdditionalFiles Include="MyProject.acuminator" />
</ItemGroup>
```

to the `.csproj` (for a `.sln`, every project it lists). Returns the same
`AnalysisResult` shape plus `suppression_files` and `project_files_modified`.
Review and commit those files.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_path` | `string` | — | Absolute path to the `.csproj` or `.sln`. |
| `isv_mode` | `bool` | `false` | Baseline with ISV-mode severities. |
| `banned_apis_path` / `allowed_apis_path` | `string` | — | As for `analyze_project`. |
| `max_diagnostics` | `int` | `200` | Cap on the locations returned (the suppression file is always complete). |

The runner matches the suppression file by **project name**: `CCIS.Acu.csproj`
reads `CCIS.Acu.acuminator`. A file left behind by a renamed project is silently
ignored — `analyze_project` with `disable_suppression=true` vs `false` giving
the same counts is the tell.

#### `get_diagnostic_docs`

Fetches the markdown at
`https://raw.githubusercontent.com/Acumatica/Acuminator/refs/heads/master/docs/diagnostics/<code>.md`
and caches to disk.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `code` | `string` | — | Diagnostic code, e.g. `PX1014`. |
| `full` | `bool` | `false` | Return the whole document. By default the top-level *Example of Incorrect Code* and *Related Articles* sections are dropped; the summary table, description, code-fix behavior and fixed-code example are kept. |

### Environment variables

| Variable | Purpose |
|---|---|
| `ACUMINATOR_MCP_REFERENCE_PROJECT` | Default reference project for `analyze_snippet`. |
| `ACUMINATOR_MCP_RUNNER_VERSION` | Pin a different runner release (default: `4.0.1`). |
| `ACUMINATOR_MCP_CACHE` | Override the on-disk cache root. |

---

## 3. Develop & Debug

### Local setup

```powershell
git clone https://github.com/contou-consulting/acuminator-mcp.git
cd acuminator-mcp
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest
.venv\Scripts\ruff check .
```

### Debugging the MCP server

#### MCP Inspector (the best first tool)

The [official MCP Inspector](https://github.com/modelcontextprotocol/inspector)
spawns the server over stdio and gives you a browser UI where you can list
tools, invoke them with arbitrary arguments, and see the raw JSON-RPC traffic.

```powershell
# requires Node.js
npx @modelcontextprotocol/inspector acuminator-mcp
```

For a dev checkout (no install):

```powershell
npx @modelcontextprotocol/inspector .venv\Scripts\python.exe -m acuminator_mcp
```

Open the URL it prints, pick a tool, fill in the parameters, click **Run Tool**. Exceptions raised by the tool show up as MCP errors; the whole JSON-RPC exchange is visible in the *History* pane.

#### Inside Claude Code

List connected servers and their state:

```
/mcp
```

Launch Claude Code with verbose MCP logging to see every request/response:

```powershell
claude --mcp-debug
```

Claude Code logs include the stdout/stderr of each MCP server it spawns — check them if a server silently fails to connect.

#### Verify the underlying Acuminator runner works

If `analyze_project` fails, isolate whether the problem is in the Python glue or in the runner itself. Resolve and run the exe directly:

```powershell
$exe = .venv\Scripts\python.exe -c "import asyncio; from acuminator_mcp.runner import ensure_runner; print(asyncio.run(ensure_runner()))"
& $exe --help
& $exe "C:\src\MyExt\MyExt.csproj" --format json -f report.json --non-interactive
```

If the runner itself fails, it's almost always one of:
- Missing .NET Framework 4.8.
- The `.csproj`/`.sln` doesn't restore cleanly (run `msbuild /t:Restore` on it first).
- Path has unescaped spaces or non-ASCII characters.

#### Invoke a tool directly from Python

The tools are plain async functions — drop into a REPL and call them:

```powershell
.venv\Scripts\python.exe -c "import asyncio; from acuminator_mcp.docs import get_diagnostic_docs; print(asyncio.run(get_diagnostic_docs('PX1014'))[:400])"
```

```powershell
.venv\Scripts\python.exe -c "import asyncio; from acuminator_mcp.snippet import analyze_snippet; import json; r = asyncio.run(analyze_snippet('public class Foo : PXGraph<Foo> {}', reference_project_path=r'C:\src\scratch\Scratch.csproj')); print(r.model_dump_json(indent=2))"
```

#### Clearing caches

If something got wedged — stale runner, stale docs:

```powershell
Remove-Item -Recurse -Force $env:LOCALAPPDATA\acuminator-mcp
```

Next tool invocation will re-download.

#### Common failure modes

| Symptom | Likely cause |
|---|---|
| `Acuminator runner requires Windows + .NET Framework 4.8` | You're on macOS/Linux, or .NET Fx 4.8 isn't installed. |
| `No reference project found. Tried …` | `analyze_snippet` called without `ACUMINATOR_MCP_REFERENCE_PROJECT` set, no `reference_project_path` argument, and auto-discovery from the server's CWD turned up no `.csproj`. |
| `Acuminator did not produce a JSON report` | The runner crashed before writing output. Re-run with the **standalone runner** step above to see its stderr. |
| `HTTP 404` when fetching docs | The diagnostic code isn't in the public docs folder (some internal-only codes aren't published). |
| Claude Code shows server as *disconnected* | Usually means `acuminator-mcp` isn't on `PATH`. Run `where.exe acuminator-mcp` to confirm. |

### Releasing

1. Bump `version` in `pyproject.toml` and `src/acuminator_mcp/__init__.py`.
2. Commit and push.
3. `git tag vX.Y.Z && git push --tags`.
4. The `Release` workflow builds the sdist + wheel and creates a GitHub release
   with both attached. Employees pin their `pipx install git+https://...@vX.Y.Z` to the new tag.

---

## License

MIT — see [LICENSE](LICENSE).
