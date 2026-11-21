# window/test_online.py isolation rerun (2026-11-12)
Split regression flagged 16 tests gold PASSED -> agent FAILED, all window/test_online.py::TestEWM::test_online_vs_non_online_mean.
Agent diff touches no window/ewm/numba code. Failures: numba JIT compile (StopIteration / lowering errors) and pytest-timeout >10s.
Re-ran only pandas/tests/window/test_online.py on each tree (scratchpad regress_one.sh, Qt offscreen):
  gold_online: 6 FAILED, 16 PASSED, 48 XFAIL (6 x Timeout >10s, numba lowering error)
  agent_online: 7 FAILED, 15 PASSED, 48 XFAIL (7 x Timeout >10s, numba lowering error)
Gold fails the same test family in isolation -> flaky (numba compile time vs 10s timeout); not attributed to the agent.
Same family flaked in test_describe (gold 5 / agent 6 failed). regression.md (16) left unchanged.
