# Integrating with CharterKeeper

A consumer contract needs **no web access, no prompts and no equivalence principle**. It only reads a handful of
views.

## The consumer surface

| View | Meaning |
|---|---|
| `is_active(org_id) -> bool` | ACTIVE and funded at or above its reserve. |
| `status_of(org_id) -> str` | `ACTIVE`, `DORMANT` or `DISSOLVED`. |
| `charter_hash(org_id) -> str` | SHA-256 commitment to the charter, criteria, economic parameters and successor. Immutable. |
| `plan_state(org_id) -> {version, hash}` | The plan currently in force. |
| `is_plan_current(org_id, plan_hash) -> bool` | Was a receipt produced against the plan I expect? |
| `is_action_authorized(proposal_id) -> bool` | Proposal settled as `EXECUTED` or `ADOPTED` with verdict `CONFORMS`. |
| `max_single_spend(org_id) -> u256` | Largest amount a single spend could take right now. |
| `next_spend_time(org_id)`, `dissolution_time(org_id)` | Timestamps for cooldown and lapse; compare to your own `datetime`. |

## Example: an AI-DAO agent that refuses to act outside its charter

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *


@gl.contract_interface
class ICharterKeeper:
    class View:
        def is_active(self, org_id: u256) -> bool: ...
        def charter_hash(self, org_id: u256) -> str: ...
        def is_action_authorized(self, proposal_id: u256) -> bool: ...


class AgentGate(gl.Contract):
    keeper: Address
    org_id: u256
    pinned_charter: str          # the hash this agent was built to serve

    def __init__(self, keeper: Address, org_id: u256, pinned_charter: str):
        self.keeper = keeper
        self.org_id = org_id
        self.pinned_charter = pinned_charter

    @gl.public.write
    def act(self, proposal_id: u256) -> None:
        ck = ICharterKeeper(self.keeper).view()
        if not ck.is_active(self.org_id):
            raise gl.vm.UserError("EXPECTED: organization is not active")
        if ck.charter_hash(self.org_id) != self.pinned_charter:
            raise gl.vm.UserError("EXPECTED: charter is not the one this agent serves")
        if not ck.is_action_authorized(proposal_id):
            raise gl.vm.UserError("EXPECTED: action was not authorized by consensus")
        # ... perform the agent's real work here
```

## Example: an autonomous trust and a maintainer fund

- **Autonomous trust**: create the organization with `successor` set to the heir. If funding lapses and
  `heartbeat` is called after the grace period, the remaining balance goes to the heir automatically; with
  `successor` unset, funders claim pro rata via `claim_refund`.
- **Maintainer / public-goods fund**: maintainers (or anyone on their behalf) call `propose_spend` with a link to
  their public release notes and the milestone criteria they claim; anyone calls `resolve`.

## Notes for integrators

- **Pin the charter hash, not the name.** `charter_hash` changes if any charter text, criterion, parameter or the
  successor differs.
- **Pin the plan hash when your logic depends on the plan** and use `is_plan_current`.
- **Transfers are emitted on finalization.** State flips at ACCEPTED; funds leave when the transaction finalizes.
  Treat a spend as paid once finalized, and re-read `get_proposal` rather than trusting a callback argument.
- **Cross-contract writes are asynchronous in GenLayer.** CharterKeeper's creation/proposal methods return ids,
  but a consumer calling them through `emit()` should read the new id afterwards instead of expecting a
  synchronous return; the consumer surface above is all views and is synchronous.
- **`dissolution_time` and `next_spend_time`** are stored timestamps (seconds since the epoch); compare them with
  your own transaction time rather than expecting the view to know "now".
- **A dormant organization can be revived** by anyone funding it above its reserve before `heartbeat` dissolves
  it; do not treat `DORMANT` as final.
