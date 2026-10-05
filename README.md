# CharterKeeper

**An unstoppable-organization primitive for GenLayer.** An organization is born with an *immutable charter*, has
**no owner, admin, pause or withdraw key**, lives while its treasury stays funded, and can adapt - but only when
independent validators agree a change or a spend still conforms to its charter, judged from public evidence they each
fetch themselves.

- **Who calls it:** AI DAOs, autonomous trusts, maintainer / public-goods funds - or any contract that wants to know
  "is this organization alive, and was this action authorized by its charter?"
- **What it decides (consensus):** does a proposed plan change, or a spend backed by a public web page, conform to the
  charter and demonstrate its milestones? **Everything else is deterministic**: caps, cooldowns, bonds, liveness,
  dissolution and every unit of value.
- **Why GenLayer:** without it, *someone* must be trusted to read the charter and the evidence - an operator, which is
  exactly the controller an unstoppable organization exists to remove.
- **Live contract:** [`0x92597B7a2676fdA74eF772bBC95D124853d91240`](https://explorer-studio.genlayer.com/address/0x92597B7a2676fdA74eF772bBC95D124853d91240) on Studionet.
- **Tests:** 231 Direct Mode tests, GenVM lint/validation, and a live Studionet suite - results below.

## Canonical deployment

| | |
|---|---|
| Network | GenLayer Studionet (hosted development network), chain 61999 |
| Contract | `0x92597B7a2676fdA74eF772bBC95D124853d91240` |
| Explorer | https://explorer-studio.genlayer.com/address/0x92597B7a2676fdA74eF772bBC95D124853d91240 |
| Deployment tx | `0xfb5fd7cb176fea538058267dde38a93486ae3cf773b1c0928341e88d36820bf6` |
| Status / consensus | **FINALIZED**, `MAJORITY_AGREE` (3 agree, 2 idle) |
| Deployment source | commit `cc1cde4`, blob `4a1e937d1decf16b6a6ab92d8422d658933eceb5` |
| Source parity | **MATCH** - code read back from the chain is byte-identical to `contracts/charterkeeper.py` at `HEAD` |

Full evidence, every transaction hash and the value-accounting check: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## The problem

An organization that is supposed to continue its mission without a controller still has to make judgments: *is this
new plan still within our mission? did this grantee actually ship what they claim?* A deterministic contract can
enforce a spending cap but cannot read English or a web page. Today the judgment is made by a multisig, a token
vote, or an off-chain operator - each one a party who can steer, stall or seize the organization.

## Why GenLayer, and what breaks without it

| Alternative | Why it fails |
|---|---|
| Off-chain operator / multisig | A trusted authority decides what the charter means. The organization is no longer unstoppable. |
| One LLM behind an API | A different single operator; its answer is unverifiable and can be steered by the evidence page. |
| Deterministic parser | Cannot judge whether a plan serves a mission or a page proves a milestone. |
| Normal oracle | Delivers a number, not a semantic ruling over text. |

**Delete GenLayer, and what breaks?** The step "decide whether this change or spend conforms to the charter" has to
be done by a person or a server, which becomes the controller. The charter would be decoration.

## Why this is not a rejected pattern

- **Not a thin LLM wrapper.** The model only labels (`verdict`, which milestone criteria the evidence supports); amounts,
  recipients, caps, cooldowns, bonds, state transitions and payments are code. See `docs/CONSENSUS.md`.
- **Not format-only validation.** The validator re-fetches the evidence, re-judges it, and rejects a well-formed but
  substantively false leader result (37 forged-leader tests).
- **Not caller-authored evidence.** Evidence is a public URL every validator fetches; excerpts must be word-for-word on
  that page.
- **Not a toy or a full application.** One contract, a small view surface, no frontend, no backend, no keys.
- **Distinct from the author's other repos.** The spend path resembles tranche/escrow adjudication; what is new is the
  charter-hash + plan-version + funding-liveness lifecycle. Honest overlap analysis: [DECISION.md](DECISION.md).

## State machine

```
organization:   ACTIVE --(balance < reserve)--> DORMANT --(funded >= reserve)--> ACTIVE
                                                   |
                          (grace elapsed, anyone calls heartbeat)
                                                   v
                                              DISSOLVED  --> fixed successor, or pro-rata refunds (claim_refund)

proposal:       PENDING --resolve--> ADOPTED | EXECUTED   (CONFORMS)
                   |  ----------> REJECTED                (VIOLATES; bond forfeited to treasury)
                   |  ----------> PENDING again           (UNCLEAR / UNAVAILABLE / INSUFFICIENT; max 3 attempts)
                   +--expire----> EXPIRED                 (3 attempts, deadline, stale plan, dissolved; bond refunded)
```

Value accounting for every terminal state is in `docs/DEPLOYMENT.md` and asserted by the conservation tests.

## Contract surface

Writes: `create_org` (payable), `fund` (payable), `propose_adaptation` (payable bond), `propose_spend` (payable bond),
`resolve`, `expire_proposal`, `heartbeat`, `claim_refund`.

Consumer views (no web, no LLM, no equivalence knowledge needed): `is_active`, `status_of`, `charter_hash`,
`plan_state`, `is_plan_current`, `is_action_authorized`, `max_single_spend`, `next_spend_time`, `dissolution_time`,
plus `get_org`, `get_proposal`, `org_count`, `proposal_count`, `contribution_of`.

## Nondeterministic operations

| Call | Where | Why irreducibly nondeterministic |
|---|---|---|
| `gl.nondet.web.get` | `resolve`, spends only | live public evidence |
| `gl.nondet.exec_prompt` | `resolve` | semantic conformance and milestone judgment |
| `gl.vm.run_nondet_unsafe` | `resolve` | custom validator that treats the leader as adversarial |

One nondeterministic round per `resolve`; both calls share the same snapshot.

## Deterministic responsibilities (the much larger surface)

URL admission; length/count bounds; bond amount; per-spend cap (a basis-point share of the treasury); cooldown;
criteria floor; plan-version binding; attempt counting; dormancy and dissolution timing; successor/refund
distribution; contribution ledger; effects-before-transfers ordering; enum/range/type validation of everything the
model returns.

## Equivalence / validator design

Validators must agree on: reachability, parse success, verdict, injection flag, and whether the claimed-criteria floor
is met. The diagnostic criteria bits and the excerpt wording may differ. The leader's excerpt must be grounded
word-for-word in the **validator's own** snapshot. Details: [docs/CONSENSUS.md](docs/CONSENSUS.md).

## Safety / failure semantics

Anything unknown, unparseable, ungrounded, injected, unreachable or unclear can only become a non-payment
(`UNCLEAR` / `UNAVAILABLE` / `INSUFFICIENT`); no unknown value can create a positive outcome. Threat model:
[docs/SECURITY.md](docs/SECURITY.md).

## Reuse surface

```python
ck = ICharterKeeper(keeper_address).view()
if not (ck.is_active(org_id) and ck.charter_hash(org_id) == PINNED and ck.is_action_authorized(proposal_id)):
    raise gl.vm.UserError("EXPECTED: not authorized by the organization's charter")
```

A complete, lint-checked consumer example is in [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Limitations

- A Studionet development deployment; **not audited**.
- Validators are LLMs reading a web page: judgments can be wrong. Damage is bounded (per-spend cap, cooldown, criteria
  floor, bond, three attempts) but not eliminated.
- The charter is immutable forever - including its mistakes. Only the operating plan adapts.
- Repeated conforming adaptations can drift the plan within the letter of the charter.
- Only the first 6000 characters of an evidence page are judged.
- Evidence must stay reachable; if it vanishes, spends cannot execute (funds stay safe).
- In-contract URL checks are defence in depth, not a complete SSRF defence.
- Honest-majority and semantic-label-variance assumptions apply. Full list: `docs/SECURITY.md`.

## Verification

Environment: Windows 11, Python 3.12.10, genlayer-test 0.29.2, genlayer-py 0.16.3, genvm-lint 0.11.0.

| Gate | Result |
|---|---|
| Direct Mode, `tests/direct` | **231 passed**, 0 failed, 0 skipped |
| GenVM AST lint and SDK validation | passed |
| Mutation check of the security-critical rules | 21 of 21 deliberate breakages caught |
| Live Studionet integration, whole suite | **6 passed**, 0 failed, 0 skipped (12m37s, real consensus, no retries needed) |
| Live Studionet integration, each behavioural test alone | **5 of 5 passed** run alone (conforming spend, each of the two hostile pages, adaptation, funding lapse + refund) |
| Canonical deployment | FINALIZED, source byte-identical to `HEAD` |
| Live success / negative / lifecycle scenarios | all verified, all transactions FINALIZED - see `docs/DEPLOYMENT.md` |

The live suite deploys **disposable** contracts; they are not the canonical deployment.

## Reviewer fast path

```bash
git clone https://github.com/s70239176-ctrl/charterkeeper-.git charterkeeper && cd charterkeeper
python3.12 -m venv .venv-test && source .venv-test/bin/activate         # Windows: .venv-test\Scripts\activate
pip install -r requirements-test.txt
pytest tests/direct -q                          # Windows only: PYTHONPATH=scripts pytest tests/direct -q -p windows_direct_plugin

python3.12 -m venv .venv-lint && source .venv-lint/bin/activate
pip install -r requirements.txt
genvm-lint check contracts/charterkeeper.py     # Windows: set PYTHONUTF8=1 first

gltest tests/integration/ -v -s --network studionet     # real consensus; takes ~15 minutes
```

On Windows, genlayer-test 0.29.2 needs an optional test-only plugin (`scripts/windows_direct_plugin.py`) because its
Direct Mode loader fails *before any contract code runs*; see `docs/DEPLOYMENT.md`. Linux and macOS do not need it.

## Repository map

```
contracts/charterkeeper.py        the one deployable contract
tests/direct/                     231 Direct Mode tests (lifecycle + adversarial + forged-leader)
tests/integration/                live Studionet suite (disposable deployments)
tests/evidence/                   the canonical deployment + live scenario run
fixtures/                         public evidence pages the live tests fetch
docs/                             CONSENSUS, SECURITY, INTEGRATION, DEPLOYMENT
DECISION.md  SUBMISSION.md        idea selection / collision audit, and copy-ready submission notes
```
