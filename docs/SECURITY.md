# Threat model

CharterKeeper is a Studionet development-network contribution. It has had automated adversarial testing but
**no independent audit**; do not put funds into it that you cannot afford to lose.

## Assets

- **Treasury funds** held per organization (`Org.balance`) and, after dissolution, the refund pool.
- **Proposal bonds** held in escrow until a proposal settles.
- **The charter**: its immutability and its hash (`charter_hash`) as a commitment consumers can pin.
- **The operating plan**: only changeable through a validated adaptation.
- **Liveness**: an organization must not be killable or seizable by a party, only by lapse of funding.

## Actors

| Actor | Powers |
|---|---|
| Founder | **None.** Recorded as provenance only; the contract has no owner, admin, pause, upgrade or withdraw method (asserted by `test_no_founder_privileges`). |
| Funder | Adds funds; can claim a pro-rata refund only if the organization dissolves without a successor. |
| Proposer | Posts a bond and proposes a plan change or a spend. |
| Anyone | Calls `resolve`, `expire_proposal`, `heartbeat`. These are permissionless and only apply deterministic rules or consensus-judged results. |
| Evidence-page owner | Controls what validators read. Treated as hostile. |
| Malicious leader | Can submit any well-formed result. |
| Honest validators | Independently fetch, judge and compare. |
| Malicious validator minority | Assumed unable to reach the validator majority. |
| Downstream consumer | Reads the small view surface. |

## Trust assumptions

1. An honest majority of GenLayer validators for the round.
2. The validators' LLMs can usually tell a plainly conforming proposal from a plainly violating one. When they
   cannot, the contract **fails closed** (no money moves) rather than guessing.
3. Evidence pages are reachable and stable for the duration of a round.
4. The charter is well written. A vague charter yields vague judgments; it is immutable by design.

## Input attacks and mitigations

| Attack | Mitigation | Test |
|---|---|---|
| Prompt injection in an evidence page | Instructions precede a JSON payload; the judge must flag `injection`; a flagged result can never pay (`UNCLEAR`); an excerpt must be verbatim in each validator's own snapshot | `test_hostile_evidence_is_json_framed...`, `test_injection_flag_fails_closed...` |
| Forged semantic output from the leader | Custom validator re-observes and compares the settlement-critical dimensions; shape-only forgeries are rejected | `TestForgedLeader` (37 cases) |
| Type confusion (bool-as-int, float, hex string, unknown enum/bit) | Exact `type(x) is ...` checks and range checks; anything off becomes `UNCLEAR` | `HOSTILE_OUTPUTS`, `TestParseJudgment`, `TestEnvelopeShape` |
| SSRF / hostile URLs | HTTPS only; no credentials, ports, IPs, `localhost`, `.local`, `.internal`; DNS-label validation; length cap | `test_hostile_or_malformed_urls_are_rejected` |
| Oversized inputs | Hard caps on every string, criteria count, quote length, fetched source (6000 chars), attempts, ids | `test_rejects_invalid_parameters`, `test_source_text_is_truncated...` |
| Replaying a settled proposal | Status is set before any transfer; terminal states reject re-entry | `test_state_is_final_before_transfers...` |
| Executing a decision under a changed plan | Every proposal is bound to `plan_version`; stale proposals cannot resolve and can only be expired | `test_adopted_plan_makes_sibling_proposals_stale` |
| Griefing with spam proposals | Exact bond per organization, forfeited to the treasury on a `VIOLATES` verdict; bounded attempts | `test_violating_*` |
| Model choosing a recipient or amount | Amount and recipient come only from the stored proposal | `test_model_cannot_choose_the_recipient_or_amount` |
| Double refund claim / refund inflation | Contribution zeroed and pool shrunk before the transfer | `test_refund_cannot_be_claimed_twice...`, mutation checks |
| Address-type surprises (`bytes` vs `Address`) | Every address coming from the message or arguments is coerced with `_as_address` | exercised in all tests |

Mutation check: 17 deliberate defects were injected into the contract (for example removing quote grounding,
accepting a bool as a mask, dropping the cooldown, refunding a forfeited bond, skipping the stale-plan check);
the suite caught 16. The 17th was a genuinely redundant duplicate cap check, which was then removed.

## Fail-open / fail-closed policy

| Condition | Default |
|---|---|
| Source unreachable | `UNAVAILABLE` - no state change besides an attempt counter |
| Model output unparseable, out of range, or the call raises | `UNCLEAR` - no payout, no plan change |
| Injection flagged | `UNCLEAR` |
| Excerpt not found in the snapshot | `UNCLEAR` |
| Criteria floor not met | `INSUFFICIENT` - no payout |
| Validators cannot agree | Transaction not accepted - no state change |
| Funding below reserve | `DORMANT`: no proposals, no resolutions, funding revives |
| Dormant past grace | Dissolution to the fixed successor, else pro-rata refunds |

No unknown value can create a positive outcome.

## Known limitations (read these)

- **Not an audit.** Studionet is a development network.
- **Semantic judgments can be wrong.** Validators are LLMs reading a web page. The design bounds the damage
  (capped per-spend share of the treasury, cooldown, criteria floor, bond, bounded attempts) but cannot make a
  judgment infallible.
- **A governing charter is forever.** There is no amend path for the charter; a badly written charter cannot be
  fixed. Only the operating plan is adaptable.
- **Adaptation can drift within the charter.** Repeated conforming adaptations may move the plan far from where
  it started while staying inside the letter of the charter.
- **Evidence liveness.** If every evidence source disappears, spends cannot execute; funds stay safe.
- **Truncation.** Only the first 6000 characters of a page are judged; a decisive fact beyond that is invisible.
- **SSRF is defence in depth only.** URL validation in the contract does not replace validator egress policy.
- **Timing.** Funding can revive a dormant organization at any moment before someone calls `heartbeat` after the
  grace deadline; a revival and a dissolution racing in the same block is decided by transaction order.
- **Finalization.** State changes at ACCEPTED; transfers are emitted `on="finalized"`. If a transaction is
  appealed and overturned, its transfers are not emitted.
- **Bounded, not infinite, history.** Proposals and organizations are append-only in storage; there is no pruning.
