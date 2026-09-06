# OfficeAddinHandler rewrite plan

Status: planning specification. No Python implementation changes are authorized by this document alone.

## Scope

Generate and serve Excel worksheet custom-function assets from notebook functions. Keep the current ribbon-function and task-pane behavior. Executable ribbon buttons and task-pane redesign are deferred for a future joint design.

## Agreed requirements

### Generate on notebook save

After a user successfully saves a notebook, generate `functions.js` and `functions.json` from the exported worksheet functions. Generated JavaScript calls ExcelModeHandler with a JSON array of positional arguments, always unpacked at the top level by the server.

Ribbon functions must remain separate from worksheet-function metadata.

### Output location

Resolve the data directory used by `jupyter --data-dir`; do not hard-code an installation path.

- Single-user JupyterLab: `<jupyter-data-dir>/excel-addin/`
- JupyterHub: `<jupyter-data-dir>/excel-addin/<username>/`

The Hub username must come from trusted authenticated/server identity, not an arbitrary request parameter. Validate its use as a path component and prevent cross-user file access.

### Templates

Provide an `addin_template` directory alongside the extension. Copy template assets into the output directory and incorporate generated content.

The discussed template set is:

- `manifest.xml`
- `functions.html`
- `commands.html`
- `taskpane.html`
- `functions.js`
- `commands.js`
- `taskpane.js`

These names normalize the original spellings `taskpan.html` and `commds.js`; confirm actual names against the supplied templates during implementation. Exact placement of `addin_template` within the Python package versus repository root remains to be finalized for packaging.

Start each generation from clean templates rather than repeatedly appending to previously generated output. Preserve existing task-pane and ribbon behavior when copying their assets.

### Filename versions

Use the server's local time. Timezone standardization is deferred.

Timestamp format: `YYMDHmmss`.

| Field | Encoding |
| --- | --- |
| Year | Two digits; 2026 becomes `26` |
| Month | `1` through `9`, then `A` for October, `B` for November, `C` for December |
| Day | `1` through `9`, then `A` for 10 through `V` for 31 |
| Hour | `0` for midnight, `1` through `9`, then `A` for 10 through `N` for 23 |
| Minute | Two digits, `00` through `59` |
| Second | Two digits, `00` through `59` |

Example: October 15, 2026 at 14:05:09 produces `26AFE0509` and `functions.26AFE0509.js`.

Version generated JavaScript filenames and update related HTML to reference the latest files. The same scheme applies to commands/task-pane scripts when those assets are emitted, without changing their functionality. Midnight encoding as `0` was the proposed completion of the requested hour scheme.

## Proposed implementation details, not yet finalized

- Separate generation logic from HTTP serving. OfficeAddinHandler serves the generated assets.
- Use static notebook inspection; saving should not execute notebook code.
- Aggregate worksheet exports across the user's notebooks, preserving complete notebook paths.
- Maintain a function registry and report duplicate exported IDs explicitly.
- Generate at startup as well as after saves; remove obsolete exports after notebook rename/deletion.
- Preserve existing save hooks and use the active ContentsManager for discovery.
- Use explicit template placeholders for generated content.
- Publish assets as a consistent batch so HTML never references missing scripts.
- Use one timestamp per batch. Decide how to handle multiple generations in the same second without changing the requested filename format.
- Retain previous script versions briefly for cached HTML; exact retention policy is undecided.
- Keep stable manifest/HTML URLs and preserve the server base URL, including Hub prefixes.
- Serve files through authenticated routes with appropriate content types; never embed tokens in generated assets or logs.

## Dependencies and open decisions

- How Excel receives and stores authentication tokens, without redesigning the task pane.
- Exact template placeholders and packaging of template files.
- Output aggregation and duplicate-name policy.
- Save-hook mechanism, generation error reporting, caching, and asset retention.
- Whether unchanged content needs a new timestamp.
- Actual Hub deployment layout and trusted username source.

## Planned verification

Verify save-triggered generation, nested notebook discovery, rename/deletion updates, template copying, version encoding, matching HTML references, complete batch publication, and single-user/Hub directory separation. Validate manifest XML and Office metadata. Confirm generated calls match ExcelModeHandler's JSON-array contract. Check that current ribbon/task-pane behavior remains intact. Live Excel integration remains a separate required verification before claiming end-to-end success.
