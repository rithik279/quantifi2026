"""Build the single-file submission `submission/trader.py` from src/strategies/*.py.

Each strategy file is a self-contained Trader for its own products. The submission must be ONE file
with ONE `Trader` class, so this script:
  1. inlines each strategy file, renaming its top-level names with a group prefix so the files'
     constants don't collide (every file has its own LIMITS and PARAMS, for example);
  2. hoists the imports to the top;
  3. appends a combining `Trader` that runs every group each tick and keeps each group's memory
     in its own slot of traderData.

Run from repo root:  python tools/build_trader.py
Then check:         python src/backtester.py submission/trader.py

Options:
  --groups g1 g2 ...        strategy files to combine (default: GROUPS below)
  --out path                output file (default: submission/trader.py)
  --set group.NAME=VALUE    replace a one-line top-level constant of a group before inlining,
                            e.g. --set standalone.JUMP_GUARD=None  (builds a variant without editing sources)
"""

import argparse
import ast
import io
import keyword
import os
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUPS = ["standalone", "pearls", "basket", "smile"]  # best-366k used "options" instead of "smile"
OUT = os.path.join(ROOT, "submission", "trader.py")


def top_level_names(tree: ast.Module) -> set:
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def new_name(group: str, name: str) -> str:
    if name == "Trader":
        return group.capitalize() + "Trader"
    if name.startswith("_"):
        return f"_{group}{name}"
    return f"{group.upper()}_{name}" if name.isupper() else f"{group}_{name}"


def apply_overrides(src: str, overrides: dict) -> str:
    """Replace one-line top-level assignments NAME = ... with NAME = VALUE."""
    if not overrides:
        return src
    tree = ast.parse(src)
    lines = src.splitlines()
    for name, value in overrides.items():
        node = next((n for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)), None)
        if node is None or node.lineno != node.end_lineno:
            raise SystemExit(f"--set: {name} is not a one-line top-level assignment")
        lines[node.lineno - 1] = f"{name} = {value}  # set by tools/build_trader.py --set"
    return "\n".join(lines) + "\n"


def inline(group: str, overrides: dict = None):
    path = os.path.join(ROOT, "src", "strategies", f"{group}.py")
    src = apply_overrides(open(path, encoding="utf-8").read(), overrides)
    tree = ast.parse(src)
    names = top_level_names(tree)

    # import lines to drop (hoisted to the header)
    imports, drop = set(), set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.add(ast.get_source_segment(src, node))
            drop.update(range(node.lineno, node.end_lineno + 1))

    # rename NAME tokens that refer to top-level names (not attributes, not keyword arguments)
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    edits = []  # (row, col_start, col_end, replacement)
    depth = 0
    for i, tok in enumerate(toks):
        if tok.type == tokenize.OP and tok.string in "([{":
            depth += 1
        elif tok.type == tokenize.OP and tok.string in ")]}":
            depth -= 1
        if tok.type != tokenize.NAME or tok.string not in names or keyword.iskeyword(tok.string):
            continue
        prev = next((t for t in reversed(toks[:i]) if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT)), None)
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if prev is not None and prev.type == tokenize.OP and prev.string == ".":
            continue  # attribute access like self.PARAMS
        if depth > 0 and nxt is not None and nxt.type == tokenize.OP and nxt.string == "=":
            continue  # keyword argument
        edits.append((tok.start[0], tok.start[1], tok.end[1], new_name(group, tok.string)))

    lines = src.splitlines()
    for row, c0, c1, rep in sorted(edits, key=lambda e: (e[0], -e[1])):
        line = lines[row - 1]
        lines[row - 1] = line[:c0] + rep + line[c1:]
    body = "\n".join(l for n, l in enumerate(lines, start=1) if n not in drop).strip("\n")
    return imports, body


COMBINER = '''

# =====================================================================================
# Combined Trader: runs every group each tick. Groups trade disjoint products, and each
# keeps its own memory in its own slot of traderData, so they cannot interfere.
# =====================================================================================
class Trader:
    def __init__(self):
        self.groups = {
__GROUPS__
        }

    def set_day(self, day):
        """Only called by our local backtester; the real engine never tells us the day."""
        for trader in self.groups.values():
            if hasattr(trader, "set_day"):
                trader.set_day(day)

    def run(self, state):
        try:
            memory = json.loads(state.traderData) if state.traderData else {}
        except ValueError:
            memory = {}
        original = state.traderData
        result = {}
        for name, trader in self.groups.items():
            state.traderData = memory.get(name, "")
            try:
                orders, _, data = trader.run(state)
            except Exception as exc:  # one group failing must not stop the others
                memory[name + "_error"] = repr(exc)[:200]
                continue
            memory[name] = data or ""
            for product, product_orders in orders.items():
                result.setdefault(product, []).extend(product_orders)
        state.traderData = original
        return result, 0, json.dumps(memory)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", nargs="+", default=GROUPS)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--set", nargs="*", default=[], dest="sets", metavar="group.NAME=VALUE")
    a = ap.parse_args()
    overrides = {}
    for s in a.sets:
        key, value = s.split("=", 1)
        g, name = key.split(".", 1)
        overrides.setdefault(g, {})[name] = value

    all_imports, sections = set(), []
    for g in a.groups:
        imps, body = inline(g, overrides.get(g))
        all_imports |= imps
        bar = "=" * 85
        sections.append(f"# {bar}\n# {g.upper()}  (generated from src/strategies/{g}.py)\n# {bar}\n{body}")
    std = sorted(i for i in all_imports if not i.startswith("from datamodel"))
    dm = sorted(i for i in all_imports if i.startswith("from datamodel"))
    header = (
        '"""UTEFA QuantiFi 2026, Team #21: combined trader.\n\n'
        "GENERATED by tools/build_trader.py from src/strategies/*.py. Edit those files, not this one.\n"
        "Each section below is one strategy group; notebooks/<group>/NOTES.md explains each one.\n"
        + ("Built with: " + " ".join(f"--set {s}" for s in a.sets) + "\n" if a.sets else "")
        + '"""\n\n' + "\n".join(std + dm) + "\n"
    )
    entries = "\n".join(f'            "{g}": {g.capitalize()}Trader(),' for g in a.groups)
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n\n" + "\n\n\n".join(sections) + COMBINER.replace("__GROUPS__", entries))
    print("wrote", out)


if __name__ == "__main__":
    main()
