---
name: acuminator
description: Run Acuminator static analysis through the acuminator MCP tools. Use after writing or changing Acumatica C# (a DAC, graph, graph extension or attribute), when asked to run Acuminator or check for PX#### diagnostics, when a PX#### code needs explaining, or to baseline a legacy project so only new diagnostics are reported.
---

# Acuminator

Four tools, all Windows-only (the runner is .NET Framework 4.8): `analyze_project`, `analyze_snippet`, `get_diagnostic_docs`, `generate_suppressions`. A run compiles the project, so expect 10 s or more per call; batch edits before re-running.

## Checking code you wrote or changed

1. Find the `.csproj` that owns the files (for a `.sln`, pass the solution; results carry project-relative paths). Run `analyze_project` on it.
2. Read `counts_by_code` first, then `groups`. Each group is one `(code, message)` with `locations` as `path:line:col`; the message is the diagnostic text and is usually enough to fix the issue. Call `get_diagnostic_docs` only for a code whose message leaves the fix unclear.
3. Fix only diagnostics in the files you touched unless asked to clean up more; the rest of a legacy project is usually already known. Done when a re-run shows no diagnostics at the locations you edited.

`truncated: true` means `groups` was cut at `max_diagnostics`; `counts_by_code` is still complete. Raise `max_diagnostics` or run per project rather than per solution when you need the rest.

## Checking a snippet before it exists in the project

`analyze_snippet` compiles a C# fragment inside a reference project so `PX.Data` types resolve. Pass the project's `.csproj` as `reference_project_path` when the server's working directory is not inside the repo. A bare DAC or graph class is enough: usings and a namespace are added, and locations come back as `snippet:line:col` against the text you sent. It writes and deletes a temp `.cs` file in that project's folder.

## Baselining a legacy project

`generate_suppressions` **writes files**: it records every current diagnostic in `<Project>.acuminator` next to each project (creating the file and adding an `<AdditionalFiles>` item to the `.csproj` when missing), so later `analyze_project` runs report only new issues. Tell the user which files it changed and that they belong in the commit. To see what a suppression file hides, run `analyze_project` with `disable_suppression: true`.
