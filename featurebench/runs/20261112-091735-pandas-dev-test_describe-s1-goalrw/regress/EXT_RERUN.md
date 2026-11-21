# Extension-folder rerun (2026-11-12)
Agent tree `pandas/tests/extension` timed out at REGRESS_TIMEOUT=1800 in the split run (exit 124; gold took 28:38, agent ran ~2x slower).
Re-ran that one path alone on the agent tree, same in-container script + QT_QPA_PLATFORM=offscreen, T_RUN=5400
(scratchpad regress_one.sh) -> regress/agent_ext/. Result: 40330 passed, 3670 skipped, 865 xfailed, 1 xpassed in 40:35 — identical counts to gold.
Merged (agent + agent_ext): 2 regressions remain, both window/test_online.py::TestEWM::test_online_vs_non_online_mean params;
the same test family fails on gold with other params (5 gold FAILED vs 6 agent FAILED), agent diff touches no window code -> flaky.
regression.json / regression.md (pre-merge, 40332) left unchanged.
