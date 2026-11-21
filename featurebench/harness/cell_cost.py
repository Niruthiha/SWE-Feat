#!/usr/bin/env python3
"""cell_cost.py <run_dir> [<through_round>] - dollars spent in a cell.

SUM ACROSS ROUNDS, LAST-WINS WITHIN A ROUND -- see roundcost.py for why a round
can emit several result events and why summing them double-counts. With
<through_round> N, covers rounds r00..rNN inclusive; that is how the harness-v4
cost LAYERS are built (attempt-1 = through 0; cost-to-self-green = through the
round the suite first went green; cost-to-acceptance = all rounds).
Used for cap enforcement mid-loop; collect_metrics.py uses the same module.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from roundcost import total_cost                                  # noqa: E402

through = int(sys.argv[2]) if len(sys.argv) > 2 else None
print(f"{total_cost(sys.argv[1], through):.4f}")
