# Execution Profiles

An execution profile selects a server-side environment and its pool limits.
Python uses `@execution_profile("name")` independently of its Excel decorator:

```python
from jupyterexcel import execution_profile, jupyter_function

@jupyter_function(name="PRICE", description="Price from the finance environment")
@execution_profile("python-finance")
def price(symbol):
    import sys
    return sys.executable
```

Either decorator order is supported. The decorator does not wrap the function or
change an ordinary Python call. `@ribbon_function` supports the same additional
decorator. Conflicting declarations and nonliteral static profile names fail.

For JavaScript use JSDoc:

```javascript
/**
 * Reports the Deno version.
 * @excelFunction DENO_VERSION
 * @execution server
 * @executionProfile javascript
 * @returns {string} Runtime version.
 */
function denoVersion() {
  return Deno.version.deno;
}
```

An explicit server profile on a local export is an error. A notebook-level
profile default is ignored by local exports, which never start a server kernel.

## Configuration

Merge this execution section into `jupyterexcel-config.json`; keep your existing
server, assets, discovery, and other sections. Names below are examples, not
environments installed automatically by JupyterExcel.

```json
{
  "execution": {
    "defaults": {
      "timeout_seconds": 30,
      "startup_timeout_seconds": 60,
      "queue_timeout_seconds": 30,
      "max_queue_size": 100
    },
    "total_max_kernels": 8,
    "default_profiles": {
      "python": "python-default",
      "javascript": "javascript"
    },
    "profiles": {
      "python-default": {
        "language": "python",
        "kernel_name": "python3",
        "min_kernels": 1,
        "max_kernels": 4
      },
      "python-finance": {
        "language": "python",
        "kernel_name": "finance-venv",
        "min_kernels": 0,
        "max_kernels": 2,
        "idle_shutdown_seconds": 300
      },
      "javascript": {
        "language": "javascript",
        "kernel_name": "deno",
        "min_kernels": 0,
        "max_kernels": 2,
        "idle_shutdown_seconds": 300
      },
      "r": {
        "enabled": false,
        "language": "r",
        "kernel_name": "ir",
        "min_kernels": 0,
        "max_kernels": 2
      }
    }
  }
}
```

Profile settings inherit the existing top-level execution settings, then
`execution.defaults`, then the profile's overrides. New named profiles default
to zero warm kernels. `python-default` and `javascript` are built-in profiles;
JavaScript defaults to zero warm kernels and a maximum of two.

Profiles support the existing utilization window, utilization threshold,
queue scale-up delay, scale-up cooldown, and startup/execution/queue timeouts.
Workers start for demand or sustained utilization, subject to the profile and
global limits. Idle workers above the minimum retire after the idle period.
Failed kernel startups back off for 30 seconds. A warm worker is initially
unbound; notebook initialization happens when it receives its first call.

R settings can be reserved with `enabled: false`. Enabling R is rejected until
an R discovery/execution adapter exists; configuring a kernelspec alone does
not implement R support.

## Registering a Python Environment

Run these commands using the intended venv's Python executable:

```sh
python -m pip install ipykernel jupyterexcel
python -m ipykernel install --user --name finance-venv --display-name "Finance Python"
jupyter kernelspec list
```

For a development checkout, install that checkout into the environment instead
of an older published package. The kernelspec must be visible to the Jupyter
server account. Its argv determines the Python interpreter; `display_name` is
only a label. Profiles reference the registered name, never a shell activation
command. JupyterExcel checks the installed kernelspec's declared language before
starting it. A missing kernel does not fall back to another environment.

For Deno, register its kernel using `deno jupyter --install` in the server
environment. Node.js remains required on the server PATH for static JSDoc parsing.

## Routing and Isolation

Selection priority is:

1. Function decorator/JSDoc profile.
2. Notebook metadata: `metadata.jupyterexcel.execution_profile`.
3. A unique profile matching the notebook's saved kernelspec and language; the
   configured language default breaks ties if it is one of the matches.
4. The language's default profile when the notebook has no kernelspec name or
   no profile matches it. An unmatched kernelspec logs a warning identifying the
   notebook, saved kernelspec, selected default profile, and selected kernel.
   Discovery and execution share a server-owned warning registry: identical
   fallback decisions for the same notebook warn only once per server session.
   Changed routing can warn again; restarting Jupyter resets the registry.

An explicit but missing/disabled profile fails. Ambiguous matches without a
matching language default still fail. Conflicting language metadata fails. JavaScript/TypeScript select the
Deno adapter; Python selects the Python adapter. Custom kernelspec names require
language metadata. Old notebooks with no language metadata retain Python handling.

Workers are bound to a profile, full notebook path, and code/configuration
revision. Notebook outputs and execution counts do not invalidate workers.
Different notebooks do not share a namespace in profile mode. The whole saved
notebook initializes in the chosen environment, so all its imports/setup cells
must work there. Function overrides can load the same notebook in different
environments; they do not extract just one function's dependencies.

Calls are serialized per worker. Multiple workers in one profile can execute
concurrently, with independent memory. This is environment affinity, not session
affinity: persistent single-kernel state is not guaranteed. Timed-out profile
workers are retired, and calls are never retried automatically. Restart Jupyter
after modifying profile configuration or packages inside a venv.

Save-and-reload retires idle workers for the selected notebook. If its calls are
active, reload reports busy instead of interrupting them. Saved source changes
select fresh workers on subsequent calls. The status panel identifies profiles,
notebooks, queue sizes, capacity, and startup errors. Help pages show the resolved
execution profile.

## Legacy Compatibility

With no `profiles`, `defaults`, `default_profiles`, or `total_max_kernels` fields,
Python retains its existing shared pool and default `python3` kernel. As before,
an ordinary Python notebook's interactive kernelspec does not change that legacy
pool. Explicit profile declarations are still validated and cannot silently fall
back. JavaScript uses its separate managed profile pool.

Adding any of those profile configuration fields opts Python into notebook-
isolated profile pools. Existing cross-notebook global variables then stop being
shared; move shared helpers into importable modules before migrating. Map custom
Python kernelspecs to explicit profiles when they require a specific environment;
otherwise they fall back to the configured language default with a warning.
