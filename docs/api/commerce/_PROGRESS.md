# Commerce Domains — Implementation Progress

Live checkpoint for the incremental commerce-domain work. Each committed step toggles its box.
Git history (`git -C back log --oneline`) is the source of truth; this file mirrors it.

- [x] Step 1 — Wishlist
- [ ] Step 2 — PreOrder
- [ ] Step 3 — Cart
- [ ] Step 4 — Order, payments, reservation

## Resume rules

If work is interrupted, to continue:

1. Run `git -C back status` and `git -C back log --oneline -3` to see the last
   completed (committed) step.
2. Finish any uncommitted work, re-run that step's checks, commit, then move on.
   A committed step is never reopened by a later step (later steps only add files
   and mount URL/settings lines).