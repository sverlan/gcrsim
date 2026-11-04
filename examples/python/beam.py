# A beam: at most 3 strings are kept in each component in each step, the first 3 that arrive. keep has state (a counter per step and
# component), so it is not pure: it is not declared with keep.pure, and --streaming refuses it. ctx.step is the number of the step.
kept = {}


def keep(s, component, ctx):
    key = (ctx.step, component)
    kept[key] = kept.get(key, 0) + 1
    return kept[key] <= 3


components = {1: {"marks": {"terminal": r"\A[ab]*\Z"}}}
