"""Compare unchanged filter modes against the frozen test2 RTL source."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parents[1] / "outputs/nes-analogizer-luma-chroma-test2/source-snapshot-2026-10-05/target/pocket/composite_blend.sv"
CANDIDATE = ROOT / "target/pocket/composite_blend.sv"
TB = ROOT / "tests/unchanged_modes_compare_tb.sv"

baseline = BASELINE.read_text(encoding="utf-8")
baseline, replaced = re.subn(r"\bmodule\s+composite_blend\s*\(",
                             "module composite_blend_baseline(", baseline, count=1)
if replaced != 1:
    raise SystemExit("could not uniquely rename the frozen baseline module")

with tempfile.TemporaryDirectory(prefix="nes-unchanged-mode-compare-") as temp:
    temp = Path(temp)
    renamed = temp / "baseline.sv"
    image = temp / "compare.vvp"
    renamed.write_text(baseline, encoding="utf-8")
    subprocess.run(["iverilog", "-g2012", "-s", "unchanged_modes_compare_tb",
                    "-o", str(image), str(CANDIDATE), str(renamed), str(TB)], check=True)
    result = subprocess.run(["vvp", str(image)], check=True, text=True, capture_output=True)
    print(result.stdout, end="")
