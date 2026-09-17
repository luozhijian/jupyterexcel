# ExcelModeHandler rewrite plan

Status: planning specification. No Python implementation changes are authorized by this document alone.

## Scope

Provide GET and POST execution endpoints for exported worksheet functions. Both methods share authentication, kernel selection, input validation, execution, and response handling. Ribbon-function redesign is deferred together with task-pane work.

## Agreed requirements

### Routes

Use `/Excel/<function-id>`, for example `/Excel/Sum`. Preserve the actual Jupyter server base URL; a Hub deployment may expose `/user/<username>/Excel/Sum` rather than a root-level route.

### Authentication

- JupyterHub: receive the token in the Authorization header, authenticate it through Jupyter/Hub identity machinery, and resolve the username from that authenticated identity.
- Single-user JupyterLab: accept the token in the query parameter, for example `?token=ABCD`.

Tokens are opaque credentials; do not decode a username from token text. Use existing Jupyter authentication rather than a separate custom token validator. Do not log tokens or place them in generated assets.

### Kernel selection

- JupyterHub: select the first kernel belonging to the authenticated user whose last reported execution state is idle.
- Single-user JupyterLab: select the first available kernel.

The selected kernel must already contain the requested function. The plan does not require executing notebook cells automatically or silently switching to another kernel when the function is absent.

Idle state is a snapshot, not a guarantee that a kernel remains free. In a normal Hub deployment, user servers manage their own kernels; verify how requests reach the appropriate user server instead of assuming one process can inspect every user's kernels.

### Arguments: always unpack the top-level array

Require JSON array input for both GET and POST. Invoke the requested callable conceptually as `function(*inputs)`, regardless of its parameter count. This replaces the earlier proposal to treat single-parameter functions differently.

| Intended call | JSON input |
| --- | --- |
| `add(3, 4)` | `[3, 4]` |
| `hello("Jim")` | `["Jim"]` |
| `total([3, 4])` | `[[3, 4]]` |
| `process({"a": 3})` | `[{"a": 3}]` |
| `hello()` | `[]` |

Preserve JSON value types. Missing trailing arguments may use Python defaults. A nested object is a positional dictionary argument, not keyword-argument expansion.

### GET

Proposed query field: `inputs`, containing a URL-encoded JSON array.

Example for a single-user server:

```text
http://localhost:8888/Excel/add?token=ABCD&inputs=%5B3%2C4%5D
```

The example decodes to `[3, 4]`. The earlier `a=3` example illustrated token placement; named query arguments are not the planned argument contract.

### POST

Proposed body contract: the JSON array directly, with `Content-Type: application/json`.

```http
POST /Excel/add?token=ABCD
Content-Type: application/json

[3, 4]
```

For Hub, use the deployment's base URL and supply authentication in the header instead:

```http
POST /user/<username>/Excel/add
Authorization: token <token>
Content-Type: application/json

[3, 4]
```

This direct-array body supersedes the initial suggestion of an object wrapper such as `{"inputs": [3, 4]}`. GET is useful for browser testing; generated Office calls should preferably use POST to avoid URL length limits.

## Proposed behavior and open implementation details

- Return a clear error if no kernel exists or, for Hub, no eligible idle kernel exists. Waiting/queueing is not currently specified.
- Define what deterministic ordering means for the first eligible kernel.
- Reserve a selected kernel during request dispatch to reduce races between simultaneous extension requests. External activity can still change its state.
- Use the active server's session/kernel managers; do not introduce process-global server state.
- Resolve only intended exported functions. Define the function registry and duplicate-name policy in coordination with asset generation.
- Report function-not-found, malformed JSON, non-array input, argument mismatch, execution failure, and timeout explicitly.
- Establish execution timeout, cancellation behavior, and request size limits.
- Preserve Jupyter authentication and applicable XSRF behavior for POST.
- Use consistent JSON responses for GET and POST; finalize success/error envelopes, HTTP status codes, and treatment of non-JSON Python results.
- Correlate kernel replies to each request; avoid leaking output or results between requests.
- Do not treat `yield` of a plain string as a return value. HTTP handlers write/finish response bodies rather than relying on a Python return value.

## Important consequence of kernel selection

Metadata can be generated from one notebook while the first selected kernel belongs to another notebook. Discovery does not prove that a function is present in that kernel. Keep the agreed selection policy and report the missing function clearly; any future notebook-specific routing would be a separate design change.

## Planned verification

Test GET/POST parity; Hub identity and user isolation; single-user token authentication; idle/busy/no-kernel cases; concurrent selection; scalar, list, dictionary, default, and zero-argument calls; malformed and non-array input; missing functions; execution exceptions; and timeouts. Verify Hub base URLs and actual Excel-to-kernel integration separately.
