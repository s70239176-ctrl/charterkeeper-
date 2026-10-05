# Consensus design

CharterKeeper uses **one** nondeterministic round, in `resolve(proposal_id)`. Everything before and after it is
deterministic.

## The exact nondeterministic calls

| Call | Where | Data in | Data out | Why code cannot replace it |
|---|---|---|---|---|
| `gl.nondet.web.get(url)` | `_fetch`, `SPEND` proposals only | A bounded, validated HTTPS evidence URL | Status + up to 6000 characters of body | The evidence lives on the live web; the contract cannot observe it. |
| `gl.nondet.exec_prompt(..., response_format="json")` | `_observe_and_judge` | One JSON payload: charter, current plan, criteria, proposal, evidence | `verdict`, `met_mask`, `injection`, `quote` | "Does this plan serve this mission?" and "does this page demonstrate this milestone?" are semantic. |
| `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)` | `resolve` | Plain copies of the above (no storage references) | The typed envelope | A custom validator is needed because the leader's result is treated as adversarial (see below). |

Both calls happen inside the same `run_nondet_unsafe`; the web fetch and the judgment use the **same snapshot**
(the validator classifies and grounds its excerpt against one fetch, not two).

`ADAPT` proposals make no web call: the plan text is already on-chain, so only the judgment is nondeterministic.

## What the model is asked, and what it is not

The model is never asked "should we pay". For `SPEND` it is asked which milestone criteria the evidence demonstrates
(`met_mask`) and whether the purpose conforms to the charter. Whether money moves is then decided by deterministic
code: the amount comes from the stored proposal, the recipient from the stored proposal, the cap from the treasury,
and the criteria floor from the charter. The model can neither choose nor change an amount or a recipient.

## Leader

1. Fetch the evidence (SPEND only). Unreachable or non-200 -> envelope `verdict=UNAVAILABLE`, no model call.
2. Build the prompt: instructions first, then the payload as **JSON** (`json.dumps`) so attacker text is data.
3. Call the model; parse strictly (see below). Unparseable -> `UNCLEAR`.
4. If the verdict is `CONFORMS` for a spend but the quoted excerpt is not found verbatim in the leader's own
   snapshot, downgrade to `UNCLEAR` (an ungrounded approval is never an approval).
5. Return the envelope `{reachable, verdict, met_mask, injection, quote, parsed}`.

## Validator (`_validator_agrees`)

The validator does **not** just check JSON shape. It repeats steps 1-4 on its own, then:

1. rejects the leader result unless it is exactly the typed envelope (`_envelope_well_formed`);
2. requires equal `reachable` and `parsed`;
3. requires equal `verdict` and equal `injection`;
4. for spends, requires that both sides agree on whether the **claimed criteria floor** is met
   (`popcount(met_mask & claimed) >= min_criteria`);
5. for a leader `CONFORMS` spend, requires the leader's `quote` to appear (whitespace/case-normalised, at least
   12 characters) in the **validator's own snapshot**.

A forged leader that claims `CONFORMS` where the validator sees `VIOLATES`, `UNCLEAR`, an injection, an unreachable
page, fewer qualifying criteria, or an invented excerpt, is rejected. These cases are covered by
`TestForgedLeader` in `tests/direct/test_charterkeeper_hardening.py` using `direct_vm.run_validator`.

## Equivalence

| Must match across validators | May differ |
|---|---|
| reachability; parse success; verdict; injection flag; whether the criteria floor is met | the exact `met_mask` bits (diagnostic) once both clear the floor; the wording of the excerpt (it only has to be grounded) |

Why: those are the only dimensions that change a state transition. The diagnostic bits are stored but never move
value on their own, so forcing identical bits would only create needless disagreement between honest validators.

`strict_eq` is deliberately **not** used: raw model output is not stable under it.

## Type hardening of the leader result

Rejected before any comparison: a boolean where an integer is required (`True` passes `isinstance(x, int)` in
Python, so exact `type(x) is int` is used), floats, hex or decimal strings, negative values, mask bits beyond the
number of criteria, unknown verdict values, truthy strings where a boolean is required, missing or extra fields,
oversized excerpts, a list/string/None instead of a dict, and inconsistent combinations such as `reachable=true`
with `UNAVAILABLE`.

## Failure

| Situation | Handling |
|---|---|
| Source unreachable / non-200 / fetch raises | envelope `UNAVAILABLE`; counts as an attempt; **not** treated as a verdict about the charter |
| Model output unparseable / out of range / LLM call raises | `UNCLEAR` (fail closed); counts as an attempt |
| Injection flagged by the judge | `UNCLEAR`, even if the verdict said `CONFORMS` |
| `CONFORMS` but criteria floor not met | stored as `INSUFFICIENT`; counts as an attempt |
| Three failed attempts | proposal `EXPIRED`, bond refunded neutrally |
| Validators disagree | the transaction is not accepted (protocol-level `UNDETERMINED`); no application state changes. Retrying is normal and safe. |

Protocol-level `UNDETERMINED` (the network could not agree on the transaction) is distinct from the contract-level
`UNCLEAR` verdict (the contract deliberately recorded "could not tell").

## After consensus

`resolve` re-checks the envelope shape before using it and then applies deterministic rules only. Effects (state
changes, bond bookkeeping) happen **before** `emit_transfer`, and transfers use `on="finalized"`, so value only
leaves once the transaction is final.

## Why consensus is load-bearing

Remove consensus and the contract has no way to know (a) whether a replacement plan stays inside an English
charter, or (b) whether a public page demonstrates a milestone. The only substitutes are an owner key, a vote,
or a single off-chain judge, each of which reintroduces the controller the organization is meant not to have.
