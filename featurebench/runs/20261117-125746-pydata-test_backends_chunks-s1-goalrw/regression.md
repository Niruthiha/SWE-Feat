# Existing-feature regression check: pydata__xarray.97f3a746.test_backends_chunks.fa55f68a.lv1

scope = touched, 1 test paths, gold vs agent tree, pytest -rA per test id

| tree | tests collected | passed | failed/error |
|---|---|---|---|
| gold (pristine) | 19702 | 18870 | 414 |
| agent (accepted) | 19702 | 18870 | 414 |

**verdict: REGRESSION** (1 tests PASSED on gold and not on agent)

- `xarray/tests/test_interp.py::test_interpolate_chunk_1d[3-2-0-True-pchip]` gold PASSED -> agent FAILED

1 tests fail on gold and pass on agent (listed in regression.json).
