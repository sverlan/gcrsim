# A filter function that cuts the words longer than 7 symbols and marks every word that it cuts. With the context ctx, ctx.mark flags
# a string even though keep then rejects it, so the run shows what the limit removed (the setting reject_max_len would drop the
# words without a trace).
def keep(s, component, ctx):
    if len(s) > 7:
        ctx.mark("too_long")
        return False
    return True


keep.pure = True
