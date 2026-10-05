# DECISION: why CharterKeeper, and why it is not one of the existing repos

Mission being answered: **Unstoppable Organizations** - "autonomous entities like DAOs that can adapt and
continue their missions indefinitely as long as they remain funded, including AI DAOs and autonomous trusts"
(GenLayer *Build with GenLayer* ideas list).

## Selected primitive

**CharterKeeper** is a reusable GenLayer primitive that keeps an organization *alive, funded and bound to its
charter* with no owner key: validators judge whether a proposed plan change, or a proposed spend backed by public
evidence, conforms to the organization's immutable charter, and deterministic code decides everything else.

State of the repository when this decision was made: **STATE A** (empty repository, no prior concept).

## Portfolio collision audit (all 58 repositories under `s70239176-ctrl`)

Repositories that are GenLayer contracts or adjacent were read (README, contract surface). The test-only repos
(`gradient*`, `LOCKER*`, `*savings-jar*`, `*faucet*`, `quant-chain`, `oracle*`, etc.) are not on a GenLayer
primitive lane.

| Repo | Core trust question | Evidence | Consensus decision | Stateful primitive | Same lane? |
|---|---|---|---|---|---|
| Treasury Release Court | Did committee work meet a written charter, so a DAO tranche is released? | URLs filed as work packets | DONE / NOT_DONE jury, bonded appeal | One tranche + appeal rounds | **Closest.** Overlaps only CharterKeeper's *spend* path. It is one-shot tranche adjudication with a committee and a frontend; it has no organization identity, no plan evolution, no funding-driven liveness, no successor/dissolution. |
| DeliverableQA / intelligent-escrow-protocol | Did a deliverable satisfy a buyer's rubric? | Delivery URLs | Accept / reject, payout | Buyer-seller escrow | Different: two-party escrow with a *per-deal* rubric, not a standing entity. |
| Meridian | Which side wins a cross-chain escrow dispute? | Case evidence | Verdict relayed to a Solidity vault | Case + settlement outbox | Different: dispute adjudication, custody on another chain. |
| BlameCourt | Who is at fault in a multi-agent failure? | Logs/evidence | Fault assignment | Case | Different question. |
| Cross-Model Commitment Receipt | Did a frozen, falsifiable claim hold? | Primary sources | Holds / broken | Commitment | Different: single claim, no treasury or lifecycle. |
| Tally | Was an endpoint up (SLA)? | Live probes | UP / DOWN | SLA + probes | Different: service uptime. |
| Credo | What collateral terms does a public identity earn? | Identity page | Standing band | Quote | Different: credit standing. |
| Parish / ResolveMarket | Which outcome occurred? | Web | Market resolution | Market | Different: prediction resolution. |
| SemanticDuplicateRegistry | Is a submission a semantic duplicate? | Registry entries | Duplicate / original | Registry | Different. |
| APPS Oracle | Do independent sources corroborate a parametric fact? | Multiple URLs | Corroborated value | Oracle | Different: truth corroboration. |
| circle-court / ParcelCourt / Splitbench / Sky-Verdict / Gen-Harmony / ArcRelay / pulsenet / RfpFit / OpenNotum / Taxforge | Each is its own application or domain primitive | - | - | - | Different domains; none holds a standing charter-bound entity. |
| red-dao, stunner-dao | Test projects (non-GenLayer DAO experiments) | - | - | - | Not a GenLayer primitive. |

**Honest overlap statement.** CharterKeeper's `propose_spend` is the same *shape* of judgment as Treasury Release
Court and DeliverableQA: "does public evidence satisfy written criteria, so money moves". It is included because an
unstoppable organization has to be able to act. What is new, and what the repo is about, is everything around it:

1. a **charter** that is immutable and committed by hash, with a separately **versioned operating plan** that can
   only change when validators agree the new plan still conforms to the charter (`propose_adaptation`);
2. every proposal **bound to the plan version** it was made under, so a stale decision can never execute against
   a different plan;
3. **funding-driven liveness**: the organization is ACTIVE while funded above a reserve, DORMANT below it, and is
   dissolved permissionlessly after a grace period, to a fixed successor or into pro-rata refunds;
4. **no authority**: no owner, admin, pause, or withdraw. Nobody can stop it or seize it; the charter and consensus
   are the only governors.

## Ecosystem collision

The official ideas list carries "Unstoppable Organizations" as a domain to explore, adjacent to "Retroactive Public
Goods Funding", "AI Arbitration" and "Fair and Transparent Moderation". It names a *domain*, not a design. No public
repository was found that provides a charter-hash + plan-version + funding-liveness lifecycle as a reusable contract
interface; this was a best-effort search, not a proof of absence.

## Candidates considered (10)

Scores are 0-10 per axis: **N**ecessity of GenLayer, **V**novelty vs. the owner portfolio, **R**euse across
unrelated consumers, **E**vidence is independently verifiable, **Q** clarity of the validator equivalence rule,
**S**tate design, **T** live testability, **F** fit for a standalone-contract submission.

| # | Candidate | N | V | R | E | Q | S | T | F | Total |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **CharterKeeper** - charter-bound, funding-live, operator-less organization | 9 | 8 | 9 | 7 | 8 | 9 | 8 | 9 | **67** |
| 2 | Amendment guard only (does an amendment conform to a charter?) | 8 | 7 | 8 | 8 | 8 | 5 | 8 | 7 | 59 |
| 3 | Retroactive public-goods attestor (did a contribution have impact?) | 8 | 6 | 7 | 5 | 5 | 6 | 6 | 7 | 50 |
| 4 | Crowd-sourced claim registry (is a claim sourced?) | 7 | 5 | 7 | 7 | 6 | 7 | 7 | 7 | 53 |
| 5 | Moderation arbiter (does content violate a published policy?) | 8 | 5 | 8 | 6 | 6 | 6 | 7 | 7 | 53 |
| 6 | Source-independence auditor (are the sources really independent?) | 8 | 6 | 7 | 8 | 7 | 5 | 7 | 7 | 55 |
| 7 | Successor selector (which organization is the legitimate heir?) | 8 | 8 | 4 | 5 | 5 | 6 | 5 | 6 | 47 |
| 8 | Policy drift watcher (did a public rule materially change?) | 9 | 5 | 8 | 8 | 7 | 7 | 7 | 8 | 59 |
| 9 | Dependency health attestor (is an external dependency still safe to rely on?) | 8 | 6 | 8 | 7 | 7 | 7 | 7 | 7 | 57 |
| 10 | Agent mandate guard (does an agent still follow its published behavior spec?) | 9 | 7 | 8 | 6 | 6 | 7 | 6 | 8 | 57 |

Rejected, with reasons:

- **2 Amendment guard only** - a strict subset of the selected design; as a standalone it has no state worth a
  primitive (a pure function of two strings), which fails the "model is not the contract" test.
- **3 Retroactive attestor** - "impact" evidence is soft and mostly private/off-chain; validators cannot
  independently re-observe it (fails the evidence rule).
- **4 / 5** - well-trodden lanes, and the model's answer is close to the whole product (thin wrapper risk).
- **6, 8, 9** - strong, but the owner's portfolio and the wider ecosystem already contain neighbours (APPS Oracle,
  policy/dependency watchers); the mission being answered here is Unstoppable Organizations.
- **7 Successor selector** - consumers are too few (fails the three-consumer test).
- **10 Agent mandate guard** - good, but belongs to the "agents" mission and overlaps conformance work already
  in the portfolio.

## Delete-GenLayer test

If GenLayer is removed, an organization that must (a) interpret an English charter and (b) read live public
evidence has exactly one option: someone is trusted to do the reading. That someone becomes the **operator**
who decides whether a plan change is "within the mission" and whether a milestone happened, which is precisely the
single point of control an *unstoppable* organization exists to eliminate. A deterministic contract can enforce caps
and timers, but cannot know whether a plan serves a mission or whether a web page proves a milestone. A single
off-chain LLM is just a different single operator.

## Three-consumer test (no change to the core contract)

1. **An AI DAO** - an agent contract acts only if `is_active`, its expected `charter_hash` matches, and its
   `is_action_authorized(proposal_id)` is true.
2. **An autonomous trust** - fixed beneficiary successor; trustees are replaced by the charter, and the trust
   dissolves into the heir if funding lapses.
3. **A grants/maintainer fund or a public-goods pool** - pays maintainers against public release evidence, keeps
   its plan evolving within a fixed mission, and refunds its funders pro rata if it dies.

## Hardest technical risk

Validators must agree on a *semantic* judgment (does this conform?) while an attacker controls the evidence page.
Mitigations designed in: consensus-critical fields are only the verdict, reachability, injection flag and whether
the criteria floor is met; excerpts must be verbatim in each validator's *own* snapshot; unknown or ambiguous
output can only ever become UNCLEAR, which never moves value; and a validator rejects any well-formed but
substantively false leader result. See `docs/CONSENSUS.md`.

## Why this belongs in standalone Intelligent Contracts

It is one contract with a small machine-readable surface, no frontend, no backend, and no off-chain component:
other Intelligent Contracts consume it through four or five view methods without touching web access, prompts or
equivalence principles.
