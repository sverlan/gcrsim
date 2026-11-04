# The gate of the valence grammar written as the filter function keep, instead of a function in the filters of component 2
# (valence.py). keep is called for the candidates of every component, so it tests the component itself: the components count from 0
# here, and 1 is component 2, the gate. A word enters it only when its weights add up to zero.
def keep(s, component):
    return component != 1 or s.count("P") == s.count("M")


keep.pure = True      # no state: --streaming can be used

components = {3: {"marks": {"terminal": r"\A[ab]*\Z"}}}
