# -*- coding: utf-8 -*-
r"""
gh_takebycount.py -- Grasshopper Script component: read one list as counts
over another, and give back the value each count covers.

Paste the whole file into a Rhino 8 Script component set to **Python 3**.
It is self-contained; nothing else needs to be on the module path.

Component setup
---------------
    input   A      int      access = Tree   the counts
    input   B      int      access = Tree   the values they are counts of
    output  V      -                        one value per count
    output  INFO   -                        one report per branch

A is not a list of values to match: it is a list of *how many*. Each number in
A takes that many elements off the front of B, and the value of that block is
what comes out -- so A says how B is grouped, and V names the group. One item
of V per item of A, in A's order.

    A = 1  2  1  2  2  2  1  1  1  2  2       11 counts, 17 in total
    B = 1 1 1 1 1 1 1 1 1 1  2 2 2 2 2 2 2    ten 1s, then seven 2s
    V = 1  1  1  1  1  1  2  2  2  2  2

The first six counts add up to 10 and so fall inside B's run of 1s; the rest
fall in the run of 2s. A count of 1 takes one element, a count of 2 takes two,
and a count that is bigger takes that many.

    A = 2 2      B = 2 2 2 2      V = 2 2

Where the lists do not fit
--------------------------
A's counts should add up to the length of B. They are still read when they do
not, and INFO says what was wrong:

    B runs out       the counts that had nothing left to take are dropped,
                     and the last one is reported if it took a short block
    B has some over  the leftover elements are reported and ignored
    mixed block      a count that straddles a change in B -- say it takes a
                     1 and a 2 -- has no single value to give. The first
                     element of the block is used and the block is reported.
    count below 1    takes nothing, gives nothing, and is reported

Whole numbers only
------------------
Both lists are read as integers and nothing else. A number slider or an
Expression hands over a double, so 10.0 is read as 10, and text that spells a
whole number ("10", " 10 ") is read as 10 as well -- but a fraction, a word, a
point, a curve, True, or anything else is not a whole number. Such an item is
left out of the reading and named in INFO.

Trees
-----
The two are paired branch by branch: by path where both carry the same paths,
by position otherwise. V is given A's paths. A branch of A with no branch of B
to pair with has nothing to take from, and INFO says so.
"""

from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# ---------------------------------------------------------------------------
# reading the input
# ---------------------------------------------------------------------------


def branches_of(tree):
    """Work whether the input access is Tree, List or Item."""
    if tree is None:
        return []
    if hasattr(tree, "Branches") and hasattr(tree, "Paths"):
        return list(zip(list(tree.Paths), [list(b) for b in tree.Branches]))
    if isinstance(tree, (list, tuple)):
        return [(GH_Path(0), list(tree))]
    return [(GH_Path(0), [tree])]


def unwrap(item):
    """The value inside a Grasshopper wrapper, or the item as it came."""
    inner = getattr(item, "Value", None)
    return item if inner is None else inner


def as_int(item):
    """The item as a whole number, or None if it is not one.

    True and False are turned away on purpose: Python counts them as the
    numbers 1 and 0, which would quietly pass for counts and for values.
    """
    value = unwrap(item)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)                # "10", "-4"
        except ValueError:
            pass
        try:
            number = float(text)            # "10.0", written as a double
        except ValueError:
            return None
        return int(number) if number.is_integer() else None
    return None


def read_ints(items):
    """A branch -> (its whole numbers, what had to be left out)."""
    numbers = []
    skipped = []
    for item in items:
        if item is None:
            continue
        number = as_int(item)
        if number is None:
            skipped.append(item)
        else:
            numbers.append(number)
    return numbers, skipped


def name_of(item):
    """How a rejected item is named in INFO -- short, and never throws."""
    try:
        text = str(unwrap(item))
    except Exception:
        return "<unreadable>"
    text = " ".join(text.split())
    return text if len(text) <= 24 else text[:21] + "..."


def pair_up(a_branches, b_branches):
    """[(path, a items, b items)], paired by path where the paths agree."""
    by_path = dict((str(path), items) for path, items in b_branches)
    aligned = len(by_path) == len(b_branches) and all(
        str(path) in by_path for path, _items in a_branches)
    out = []
    for i, (path, items) in enumerate(a_branches):
        if aligned:
            other = by_path[str(path)]
        elif i < len(b_branches):
            other = b_branches[i][1]
        else:
            other = None            # nothing to pair with: takes nothing
        out.append((path, items, other))
    return out


# ---------------------------------------------------------------------------
# taking the blocks
# ---------------------------------------------------------------------------


def take_by_count(counts, values):
    """Walk B in blocks the size of each count. -> (values, notes).

    The blocks follow one another: a count of 2 takes the next two elements,
    and the count after it starts where that block ended. The value of a block
    is its first element, which is the whole story as long as the block does
    not straddle a change in B -- one that does is reported instead of being
    quietly averaged over.
    """
    out = []
    notes = []
    at = 0
    for i, count in enumerate(counts):
        if count < 1:
            notes.append("count %d of A is %d - it takes nothing"
                         % (i, count))
            continue
        if at >= len(values):
            notes.append("B ran out at count %d of %d - the last %d took "
                         "nothing and were dropped"
                         % (i, len(counts), len(counts) - i))
            break
        block = values[at:at + count]
        if len(block) < count:
            notes.append("count %d asked for %d but only %d were left in B"
                         % (i, count, len(block)))
        if len(set(block)) > 1:
            notes.append("count %d covers more than one value in B (%s) - "
                         "the first is used"
                         % (i, ", ".join(str(v) for v in block)))
        out.append(block[0])
        at += count
    if at < len(values):
        notes.append("%d element%s of B %s over at the end and %s ignored"
                     % (len(values) - at, "" if len(values) - at == 1 else "s",
                        "was" if len(values) - at == 1 else "were",
                        "was" if len(values) - at == 1 else "were"))
    return out, notes


# ---------------------------------------------------------------------------
# Grasshopper plumbing
# ---------------------------------------------------------------------------

V = DataTree[object]()
INFO = DataTree[object]()

a_branches = branches_of(A)
b_branches = branches_of(B)

if not a_branches:
    INFO.Add("nothing on A - no counts to read", GH_Path(0))
elif not b_branches:
    INFO.Add("nothing on B - the counts have nothing to take", GH_Path(0))

for path, a_items, b_items in pair_up(a_branches, b_branches):
    tag = str(path)
    if b_items is None:
        INFO.Add("%s   no branch of B to pair with - it takes nothing" % tag,
                 path)
        b_items = []

    counts, a_skipped = read_ints(a_items)
    values, b_skipped = read_ints(b_items)
    for side, skipped in (("A", a_skipped), ("B", b_skipped)):
        if skipped:
            shown = ", ".join(name_of(x) for x in skipped[:6])
            if len(skipped) > 6:
                shown += ", ..."
            one = len(skipped) == 1
            INFO.Add("%s   %d item%s of %s %s not a whole number and %s left "
                     "out of the reading (%s)"
                     % (tag, len(skipped), "" if one else "s", side,
                        "is" if one else "are", "was" if one else "were",
                        shown), path)

    if not counts:
        INFO.Add("%s   no counts on A - nothing to take" % tag, path)
        continue
    if not values:
        INFO.Add("%s   no values on B - the counts have nothing to take" % tag,
                 path)
        continue

    taken, notes = take_by_count(counts, values)
    for value in taken:
        V.Add(value, path)
    INFO.Add("%s   %d count%s over %d value%s -> %d out, %d taken in total"
             % (tag, len(counts), "" if len(counts) == 1 else "s",
                len(values), "" if len(values) == 1 else "s", len(taken),
                sum(c for c in counts if c > 0)), path)
    for note in notes:
        INFO.Add("%s   note: %s" % (tag, note), path)
