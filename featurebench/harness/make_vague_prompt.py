"""make_vague_prompt.py <task_dir>... - stress-test prompt ("vague"), fixed rules (user, 2026-11-02):
  1. keep the task description and the function signatures (every Interface Description code block, verbatim);
  2. a Path: line whose interface the hidden test IMPORTS becomes an import line:
       Importable as `from <module the test imports it from> import <names>`
     (the module must be the block's own module or a parent package re-exporting it; if the test imports
     none of the block's names but does import other names from the block's own module that the dataset prompt
     already shows, those are given; attribute access via `import a.b as m; m.f()` counts as importing f from a.b)
  3. a Path: line whose interface the test does NOT import (internal) is deleted (signature stays, location gone);
  4. the Clarification EXAMPLE is deleted: from "for example, you will get things like this:" through the
     paragraph "The value of Path declares the path ..." (it explains the Path: line, which no longer exists).
     The rest of the Clarification subsection stays (its first sentence, "you may try to modify any file in
     codebase ...", the dependencies line, "there may be not only one Interface Description").
Everything else stays byte-for-byte. The hidden test is read HERE (harness side) only to learn which names it
imports; the only test-derived text that reaches the prompt is the import line (module + names), which the test
needs anyway. Writes <task_dir>/prompt_vague.txt, prompt_vague.diff, prompt_vague.json (per-block decision)."""
import ast, difflib, json, re, sys, pathlib


def test_source(task):
    """The hidden test file(s), reconstructed from test.patch (stored as deletions)."""
    files, cur = {}, None
    for line in (task / "test.patch").read_text().splitlines():
        if line.startswith("diff --git"):
            cur = line.split()[2][2:]; files[cur] = []
        elif cur and line.startswith("-") and not line.startswith("---"):
            files[cur].append(line[1:])
    return {f: "\n".join(v) for f, v in files.items()}


def test_imports(srcs):
    """name -> set of modules it is imported from; plus modules imported whole."""
    names, mods, alias = {}, set(), {}
    for src in srcs.values():
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                for a in n.names:
                    names.setdefault(a.name, set()).add(n.module)
                    mods.add(f"{n.module}.{a.name}")          # `from pkg import submodule`
            elif isinstance(n, ast.Import):
                for a in n.names:
                    mods.add(a.name)
                    if a.asname:                              # `import x.y.z as m` -> m.f() is x.y.z.f
                        alias[a.asname] = a.name
        # attribute access through a whole-imported module counts as a tested path too:
        # `optuna.storages.fail_stale_trials(...)` -> fail_stale_trials from optuna.storages
        roots = {m.split(".")[0] for m in mods}
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Attribute):
                chain, x = [n.attr], n.value
                while isinstance(x, ast.Attribute):
                    chain.append(x.attr); x = x.value
                if isinstance(x, ast.Name) and x.id in alias:
                    chain.reverse()
                    names.setdefault(chain[-1], set()).add(".".join([alias[x.id]] + chain[:-1]))
                elif isinstance(x, ast.Name) and x.id in roots:
                    chain.append(x.id); chain.reverse()
                    names.setdefault(chain[-1], set()).add(".".join(chain[:-1]))
    return names, mods


def defined(code):
    """Top-level def/class names in an interface code block (a trailing `...` line is allowed)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        try:
            tree = ast.parse(re.sub(r"(?m)^\.\.\.\s*$", "", code))
        except SyntaxError:  # 2026-11-13 (seaborn test_line): a def whose body is only a comment; take top-level names by regex
            return re.findall(r"(?m)^(?:async\s+def|def|class)\s+(\w+)", code)
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def module_of(path):
    p = path.removeprefix("/testbed/").removesuffix(".py")
    for pre in ("src/", "lib/"):
        p = p.removeprefix(pre)
    return p.replace("/", ".").removesuffix(".__init__")


def main(task):
    task = pathlib.Path(task)
    orig = (task / "prompt.txt").read_text()
    names, mods = test_imports(test_source(task))
    # rule 4: drop the Clarification example (+ the sentence explaining its Path: line)
    a = orig.index("for example, you will get things like this:")
    v = orig.index("The value of Path declares", a)
    b = orig.index("\n\n", v) + 2
    assert a < v < b < orig.index("### Interface Description 1")
    text = orig[:a] + orig[b:]
    # rules 2/3: each Path: line + the python block right after it
    out, decisions, pos = [], [], 0
    for m in re.finditer(r"(?m)^Path: `([^`]+)`\n```python\n(.*?)\n```", text, re.S):
        path, code = m.group(1), m.group(2)
        defs, mod = defined(code), module_of(m.group(1))
        imp = {}
        for d in defs:
            # only the block's own module or a parent package of it (a re-export) counts; a same-named
            # function imported from an unrelated module is a different function (test_scorers: list_scorers)
            src = sorted(x for x in names.get(d, ()) if x == mod or mod.startswith(x + "."))
            if src:
                imp.setdefault(mod if mod in src else src[0], []).append(d)
        if not imp:
            # the test imports OTHER names from this block's own module (test_scorers: `commands`, the click
            # group whose subcommands the block defines) -> the location is tested; give that import
            # only names the dataset prompt already shows, so no test-only name enters the prompt
            other = sorted(n for n, v in names.items() if mod in v and re.search(rf"\b{re.escape(n)}\b", orig))
            if other:
                imp[mod] = other
        whole = mod in mods
        out.append(text[pos:m.start()])
        if imp:
            line = "\n".join(f"Importable as `from {k} import {', '.join(v)}`" for k, v in imp.items())
            kind = "import_line"
        elif whole:
            line = f"Importable as `import {mod}`"; kind = "import_module"
        else:
            line = None; kind = "deleted_internal"
        out.append((line + "\n") if line else "")
        out.append(text[m.start() + len(f"Path: `{path}`\n"):m.end()])
        pos = m.end()
        decisions.append({"path": path, "module": mod, "defs": defs, "decision": kind,
                          "tested_names": imp, "not_imported_by_test": [d for d in defs if not any(d in v for v in imp.values())]})
    out.append(text[pos:])
    vague = "".join(out)
    (task / "prompt_vague.txt").write_text(vague)
    (task / "prompt_vague.diff").write_text("".join(difflib.unified_diff(
        orig.splitlines(True), vague.splitlines(True), "prompt.txt", "prompt_vague.txt", n=1)))
    test_needed = {n: sorted(v) for n, v in names.items()
                   if any(v2.split(".")[0] == mod.split(".")[0] for v2 in v for mod in [decisions[0]["module"]])}
    json.dump({"decisions": decisions, "test_project_imports": test_needed,
               "chars": [len(orig), len(vague)], "path_lines_left": vague.count("Path: `")},
              open(task / "prompt_vague.json", "w"), indent=1)
    print(f"{task.name}: {len(orig)} -> {len(vague)} chars;",
          ", ".join(f"{d['path'].split('/testbed/')[1]}={d['decision']}" for d in decisions))


if __name__ == "__main__":
    for t in sys.argv[1:]:
        main(t)
