# Real-time worksheet functions

Use the namespace configured in your manifest (normally `JUPYTER`).

```excel
=JUPYTER.RtNow(1)
=JUPYTER.RtRand(2)
=JUPYTER.RtRandBetween(2,1,100)
=JUPYTER.RtRandArray(2,5,3,0,1,FALSE)
=JUPYTER.RtCount(1)
=JUPYTER.RtElapsed(1)
=JUPYTER.RtCountdown(1,60)
```

Numeric first arguments publish immediately and then refresh at that many seconds.
Intervals must be finite and at least 0.001 seconds; practical intervals of one
second or longer are recommended. Random arrays default to 1x1, 0 through 1
(exclusive for decimals), and FALSE for whole numbers. Arrays are limited to
100,000 elements to bound repeated allocation. Integer bounds must contain at
least one representable safe integer. Independent draws may coincide.

For a shared schedule, put a fixed Excel date/time in A1 and use:

```excel
A2: =JUPYTER.RtTimer(A1,2,10)
B1: =JUPYTER.RtRand(A2)
C1: =JUPYTER.RtRandBetween(A2,1,100)
D1: =JUPYTER.RtCountdown(A2)
```

RtTimer returns a versioned text descriptor, not a live JavaScript object.
Its arguments are start_time, frequency_in_seconds, and duration_in_minutes.
Start and RtNow use the computer's local time and Excel's 1900 date system;
1904-date-system workbooks are not supported. Format RtNow cells as dates/times.
Use fixed start values: NOW() can recalculate and move the schedule.

Before the start, consumers show #N/A. At expiration they retain their last
value, except countdown which publishes zero. A formula first entered after
expiration produces one snapshot using the end time and starts no timer.
RtCount starts at zero for each invocation and counts delivered refreshes.
RtElapsed measures wall-clock elapsed seconds, including delays. Sleeping or
busy Excel can delay updates; missed ticks are skipped, not replayed.

Identical schedule descriptors share one runtime-local timeout and independent
subscriber generators. Streaming metadata requests the calling cell address
(`requiresStreamAddress`) so Excel can provide cell-specific invocations.
Cancellation removes only that invocation; the last cancellation clears the
timeout. Completion releases subscriptions. Workbook runtime destruction also
destroys timers. No Python/server task is started by these built-ins.

Automatic calculation is expected to recalculate dependent formulas on streaming
updates. Excel host behavior is not established by the Node tests. Before release,
verify in the supported Excel build:

1. Copy identical RtRand formulas into separate cells and verify independent draws.
2. Reference RtNow/RtCount and RtRandArray spills from ordinary and Python functions.
3. Change arguments, delete formulas, and manually recalculate; check no duplicate ticks.
4. Share a future schedule; verify start, expiry, cancellation, and countdown zero.
5. Close the workbook while another remains open, then reopen; check fresh streams.
6. Check streaming cell-address metadata support on the target Office version.

Regenerate the served assets and reload the add-in metadata to expose new functions.
No generated deployment files are modified by this source change.
