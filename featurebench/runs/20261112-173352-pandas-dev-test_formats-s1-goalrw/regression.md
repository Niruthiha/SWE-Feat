# Existing-feature regression check: pandas-dev__pandas.82fa2715.test_formats.05080a4e.lv1

scope = touched, 1 test paths, gold vs agent tree, pytest -rA per test id

| tree | tests collected | passed | failed/error |
|---|---|---|---|
| gold (pristine) | 232584 | 229606 | 736 |
| agent (accepted) | 232584 | 229590 | 752 |

**verdict: REGRESSION** (16 tests PASSED on gold and not on agent)

- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-False-True-False-False-obj0]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-False-True-False-False-obj1]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-False-True-False-True-obj0]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-False-True-False-True-obj1]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-False-True-True-False-obj0]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-False-True-True-False-obj1]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-False-True-True-True-obj0]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-False-True-True-True-obj1]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-True-True-False-False-obj0]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-True-True-False-False-obj1]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-True-True-False-True-obj0]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-True-True-False-True-obj1]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-True-True-True-False-obj0]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-True-True-True-False-obj1]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-True-True-True-True-obj0]` gold PASSED -> agent FAILED
- `pandas/tests/window/test_online.py::TestEWM::test_online_vs_non_online_mean[False-True-True-True-True-obj1]` gold PASSED -> agent FAILED
