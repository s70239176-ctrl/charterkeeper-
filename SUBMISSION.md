# Submission notes (copy-ready)

| Field | Value |
|---|---|
| Category | Unstoppable Organizations (GenLayer Intelligent Contracts) |
| Title | CharterKeeper - charter-bound, funding-live organizations with no owner key |
| One-line thesis | CharterKeeper is a reusable GenLayer primitive that keeps an organization alive, funded and bound to its immutable charter: validators judge whether a plan change or a spend conforms, and deterministic code decides everything else. |
| Repository | https://github.com/s70239176-ctrl/charterkeeper- |
| Canonical Studionet address | `0x92597B7a2676fdA74eF772bBC95D124853d91240` |
| Explorer URL (contract) | https://explorer-studio.genlayer.com/address/0x92597B7a2676fdA74eF772bBC95D124853d91240 |
| Deployment tx | `0xfb5fd7cb176fea538058267dde38a93486ae3cf773b1c0928341e88d36820bf6` (FINALIZED, MAJORITY_AGREE) |
| Deployment source | commit `cc1cde4`, `contracts/charterkeeper.py`, git blob `4a1e937d1decf16b6a6ab92d8422d658933eceb5`; on-chain bytes verified identical to `HEAD` |
| Contribution date | the date you submit (not the build date) |

## Portal description (809 characters)

```text
CharterKeeper is a standalone GenLayer Intelligent Contract for unstoppable organizations: an immutable charter, no owner or admin key, a treasury that keeps it alive while funded. Validators independently fetch public evidence and judge whether a plan change or a spend conforms to the charter; a custom validator rejects well-formed but false leader results. Deterministic code owns caps, cooldowns, bonds, dormancy, dissolution (successor or pro-rata refunds) and all value movement; anything unclear fails closed. Other contracts read is_active, charter_hash and is_action_authorized. Verified: 231 Direct Mode tests, GenVM lint/validation, 6 live Studionet tests (plus 5 run individually), and a FINALIZED Studionet deployment whose on-chain source is byte-identical to main. Studionet only, not audited.
```

## Why GenLayer is required

An organization that must interpret an English charter and read live public evidence needs someone to do the reading.
Without GenLayer that someone is an operator, multisig or single off-chain model - the controller an unstoppable
organization exists to remove. Details: `DECISION.md`, README "Why GenLayer".

## Consensus mechanism

One `gl.vm.run_nondet_unsafe` round per `resolve`. The leader fetches the evidence and judges it; each validator
independently re-fetches and re-judges, then compares reachability, parse success, verdict, injection flag and whether
the claimed-criteria floor is met, and checks that every excerpt fragment is word-for-word in its **own** snapshot.
Forged but well-formed leader results are rejected (37 forged-leader tests). `docs/CONSENSUS.md`.

## Deterministic responsibilities

URL admission, bounds, bond amount, per-spend cap, cooldown, criteria floor, plan-version binding, attempt counting,
dormancy and dissolution timing, successor/refund distribution, ledger, effects-before-transfers ordering and
type/range validation of all model output.

## Failure policy

Unknown, unparseable, ungrounded, injected, unreachable or unclear results can only become a non-payment
(`UNCLEAR` / `UNAVAILABLE` / `INSUFFICIENT`) and, after three attempts, an expiry with the bond refunded. No unknown
value can create a positive outcome. `docs/SECURITY.md`.

## Reuse surface

`is_active`, `charter_hash`, `plan_state`, `is_plan_current`, `is_action_authorized`, `max_single_spend`,
`next_spend_time`, `dissolution_time`. A lint-checked consumer contract is in `docs/INTEGRATION.md`.

## Test results (final commit)

| Gate | Result |
|---|---|
| Direct Mode | 231 passed, 0 failed, 0 skipped |
| Mutation check | 21 of 21 deliberate defects caught |
| GenVM AST lint and SDK validation (`genvm-lint` 0.11.0) | passed |
| Live Studionet integration, whole suite | 6 passed (12m37s) |
| Live Studionet integration, each behavioural test alone | 5 of 5 passed |
| Canonical deployment | FINALIZED; source parity MATCH |
| Contract native balance vs. value accounting | 1900 on-chain = 1900 expected |

Environment: Windows 11, Python 3.12.10, genlayer-test 0.29.2, genlayer-py 0.16.3. On Windows the Direct Mode results
used the optional test-only `scripts/windows_direct_plugin.py` (genlayer-test 0.29.2 fails in its own loader before any
contract code runs). The contract is unaffected. See `docs/DEPLOYMENT.md`.

## Live evidence (all transactions FINALIZED, MAJORITY_AGREE when last read)

| Scenario | Tx | Stored result |
|---|---|---|
| success: conforming release report | `0x66982366583aa6b8d8ec0db20a75490d07f7ec83b307b308f9e217777bf527ee` | `EXECUTED`, `CONFORMS`, balance 1000 -> 900 |
| negative: prompt-injection page (3 rounds) | `0x3e81e507...`, `0x1b0cf8a4...`, `0xfc12c421...` | `EXPIRED`, `UNCLEAR`, nothing paid, bond refunded |
| lifecycle: dormancy -> dissolution -> refund | `0x4f356e00...`, `0xe2b14972...`, `0xef517eb9...` | `DISSOLVED`, refund pool 60 -> 0 |

Full hashes: `docs/DEPLOYMENT.md`.

## Limitations

Studionet development deployment, not audited. LLM judgments can be wrong (bounded by cap, cooldown, criteria floor,
bond, three attempts). The charter is immutable including its mistakes. Plans can drift within the charter's letter.
Only the first 6000 characters of an evidence page are judged. Evidence must remain reachable. In-contract URL checks
are defence in depth. Honest-majority assumption. The hosted network was observed to stall or return gateway errors
occasionally; one such stall in an earlier individual run was not root-caused (`docs/DEPLOYMENT.md`).

## Reviewer fast path

```bash
git clone https://github.com/s70239176-ctrl/charterkeeper-.git charterkeeper && cd charterkeeper
python3.12 -m venv .venv-test && source .venv-test/bin/activate && pip install -r requirements-test.txt
pytest tests/direct -q          # Windows: PYTHONPATH=scripts pytest tests/direct -q -p windows_direct_plugin
gltest tests/integration/ -v -s --network studionet
```

## Before pressing submit

- the address in the form equals `0x92597B7a2676fdA74eF772bBC95D124853d91240`;
- the Explorer **address** page opens (this is the `genlayer-explorer-contract` evidence URL, not a transaction URL);
- the repository is public and `main` contains `contracts/charterkeeper.py`;
- the description above still matches the portal's current character limit and test counts.
