# Kernel pool and Jupyter Status

JupyterExcel now starts a per-server managed pool. Every kernel loads the same
snapshot of selected notebooks. Calls use a FIFO queue and an available worker;
Python globals and in-memory data are independent between kernels. Stateful
routing is not implemented yet. Notebook initialization runs once per worker,
so initialization side effects run multiple times. Idle workers retain memory.

Settings are read from `jupyterexcel-config.json` in the Jupyter root at server
startup. Keep the `discovery` section alongside this `execution` section:

```json
{
  "execution": {
    "min_kernels": 2,
    "max_kernels": 4,
    "scale_up_utilization": 0.8,
    "utilization_window_seconds": 5,
    "queue_scale_up_after_seconds": 1,
    "scale_up_cooldown_seconds": 1,
    "queue_timeout_seconds": 30,
    "startup_timeout_seconds": 60,
    "max_queue_size": 1000
  }
}
```

These are also the defaults when execution settings are absent. Restart the
server to apply changes. The pool proactively prepares its minimum workers;
the former opt-in `JUPYTEREXCEL_KEEP_KERNEL_READY` flag is no longer needed.
`JUPYTEREXCEL_EXECUTION_TIMEOUT` still controls each call's response timeout.

Every 0.1 seconds the scheduler checks demand. It starts at most one kernel at
a time, up to the maximum. Expansion occurs when average occupied time across
serving workers reaches the threshold over the rolling window, or all workers
are unavailable and the oldest queued request reaches the queue scale-up delay.
Starting workers are excluded from utilization. The window uses elapsed wall
time, not CPU percentage; a new worker begins with zero historical busy time.
No automatic scale-down occurs. Initialization failures back off for 30 seconds.
Queue waiting and execution have separate timeouts. Timed-out Python operations
keep their worker reserved until the actual execution reply and idle state;
the pool never automatically retries a call that may have had side effects.
Dead workers are replaced; only owned kernels are protected from idle culling
and removed on shutdown.

Save-and-reload pauses dispatch, waits for active operations, reads a fresh
snapshot, and replaces managed workers. Old globals are discarded. The notebook
must be included in discovery. If draining times out, active work continues.
If new initialization fails, requests must not run against old definitions.
Ordinary saves regenerate assets but do not reload already-running Python code.
Use Save-and-reload or restart the server after changing notebook code/selection.

In Excel, open **Input Access Token**, then **Jupyter Status** beside **Reload
add-in**. The panel displays kernel counts, per-kernel busy time, active function,
completed/failed calls, queued requests, oldest wait, scaling state, and last
pool error. It refreshes every two seconds while visible and stops on auth errors
or when hidden/closed. Refresh retries manually. It is read-only and remains
available while kernels are busy.

`GET /jupyterexcel/api/status` (under the server's base path on Hub) requires
authentication and kernel-read authorization. Hub requests also require an
authenticated token for the owning user. It reads telemetry without running
Python in any kernel. Status never includes credentials or function arguments.

After deploying the updated package, restart JupyterLab and regenerate the
served add-in assets. Reload the add-in to load the new dialog script. Live Excel
rendering and cross-origin access should be checked in the deployment environment.

## Persistent kernel connections

Each managed worker owns one shell-only AsyncKernelClient for initialization
and function calls. It reuses that client while exclusively reserved, filters
replies by message ID, and uses a kernel-info handshake without creating
heartbeat threads or unused channels. A changed kernel process ID or connection
information replaces the client. Retirement and shutdown explicitly close its
socket; startup failures also close partially created sockets. Timed-out calls
retain both their client and worker reservation until Python finishes.

After installing this fix, fully restart the Jupyter server to release resources
accumulated by older code. Reloading only the Excel add-in is insufficient.
