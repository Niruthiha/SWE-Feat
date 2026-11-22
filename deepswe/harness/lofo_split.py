"""lofo_split.py <gold.patch> <outdir> - split a unified git diff into per-file sections; for each file write
drop_NN.patch = the gold patch WITHOUT that file's section; files.tsv = idx, path, kind (src|test|doc|gen|nonsrc).
kind uses the same rules as the task selection (lists/select_deepswe.py / classify)."""
import os, re, sys, pathlib
CODE_EXT = {".py", ".pyx", ".pyi", ".go", ".java", ".kt", ".kts", ".scala", ".groovy", ".rs", ".c", ".h", ".cc", ".cpp",
            ".cxx", ".hpp", ".hh", ".hxx", ".inl", ".ipp", ".cu", ".m", ".mm", ".cs", ".fs", ".vb", ".js", ".jsx", ".mjs",
            ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte", ".rb", ".php", ".swift", ".dart", ".lua", ".zig",
            ".ps1", ".sh", ".xaml", ".razor", ".cshtml"}
TEST_DIR = re.compile(r"(^|/)(tests?|testing|__tests__|__mocks__|fixtures?|testdata|test_data|testutils?|spec|e2e|benchmarks?|snapshots?|__snapshots__)(/|$)", re.I)
TEST_FILE = re.compile(r"(_test\.[^/]+$|(^|/)test_[^/]*\.py$|\.spec\.[^/]+$|\.test\.[^/]+$|(^|/)conftest\.py$|Tests?\.(java|kt|cs|scala)$|_tests?\.(rs|cc|cpp|c)$|\.snap$)", re.I)
GEN = re.compile(r"((^|/)(vendor|node_modules|third_party|thirdparty|dist|generated|gen)/|\.pb\.go$|_pb2(_grpc)?\.py$|\.pb\.(cc|h)$|\.generated\.|\.g\.cs$|\.Designer\.cs$|\.min\.js$|\.d\.ts$|zz_generated)", re.I)
DOC = re.compile(r"((^|/)docs?/|(^|/)examples?/|\.md$|\.rst$)", re.I)
def classify(p):
    if os.path.splitext(p)[1].lower() not in CODE_EXT: return "nonsrc"
    if DOC.search(p): return "doc"
    if GEN.search(p): return "gen"
    if TEST_DIR.search(p) or TEST_FILE.search(p): return "test"
    return "src"
txt = pathlib.Path(sys.argv[1]).read_text(errors="surrogateescape"); out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
parts = re.split(r"(?m)^(?=diff --git )", txt); head, secs = parts[0], [p for p in parts[1:]]
paths = []
for s in secs:
    m = re.match(r"diff --git a/(.+?) b/(.+)\n", s); paths.append(m.group(2) if m.group(2) != "/dev/null" else m.group(1))
with open(out / "files.tsv", "w") as f:
    for i, (p, s) in enumerate(zip(paths, secs)):
        f.write(f"{i:02d}\t{p}\t{classify(p)}\n")
        (out / f"drop_{i:02d}.patch").write_text(head + "".join(x for j, x in enumerate(secs) if j != i), errors="surrogateescape")
print(f"{len(secs)} file sections, {sum(classify(p) == 'src' for p in paths)} source")
