# Reliability playbook (cue: guards, monitors, gates, self-heal, "is it done?")
- Verify the effect, not the existence: installed is not initialized, scheduled is not run, "fixed" is not observed. Done = the real path produced the expected output (log line, row, HTTP 200, LastTaskResult 0).
- A guard that reports but does not block is a monitor, not a guard; name which one you built. Guards fail closed unless failing open is a stated decision.
- Every artifact-producing pipeline states its quality floor before building and emits a machine-checkable pass/fail report each run; a reported defect gets a new check, not only a patch.
- A rejected or timed-out tool call may still have run: check for partial side effects before retrying.
- Long jobs print progress, use per-item timeouts and write a heartbeat; a silent hang is a failure.
- When a design cites a precedent's failure mode, show explicitly how the new design avoids it.
