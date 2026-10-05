"""CharterKeeper lifecycle tests (Direct Mode). Every test builds its own world."""
import pytest

from conftest import (
    CHARTER, CRITERIA, DAY, GOOD_PAGE, GOOD_URL, PLAN, ZERO,
    hexof, verdict_json,
)


# ----------------------------------------------------------------- creation
class TestCreateOrg:
    def test_creates_active_org_with_expected_state(self, world):
        org = world.make_org()
        assert org == 1
        o = world.c.get_org(org)
        assert o["status"] == "ACTIVE"
        assert o["balance"] == 1000 and o["total_contributed"] == 1000
        assert o["plan_version"] == 1 and o["criteria"] == CRITERIA
        assert o["charter"] == CHARTER and o["plan"] == PLAN
        assert o["founder"].lower() == hexof(world.alice)
        assert world.c.org_count() == 1
        assert world.c.is_active(org) is True
        assert world.c.contribution_of(org, world.alice) == 1000

    def test_ids_increment_and_orgs_are_independent(self, world):
        a = world.make_org(name="A")
        b = world.make_org(name="B", value=500)
        assert (a, b) == (1, 2)
        world.fund(a, 50)
        assert world.c.get_org(a)["balance"] == 1050
        assert world.c.get_org(b)["balance"] == 500
        assert world.c.get_org(a)["name"] == "A" and world.c.get_org(b)["name"] == "B"

    def test_charter_hash_commits_to_the_whole_definition(self, world):
        a = world.make_org()
        b = world.make_org()
        c = world.make_org(max_spend_bps=1999)
        d = world.make_org(charter=CHARTER + " ")
        assert world.c.charter_hash(a) == world.c.charter_hash(b)
        assert len({world.c.charter_hash(x) for x in (a, c, d)}) == 3

    def test_plan_is_not_part_of_the_charter_hash(self, world):
        a = world.make_org()
        b = world.make_org(plan="A completely different opening plan.")
        assert world.c.charter_hash(a) == world.c.charter_hash(b)
        assert world.c.get_org(a)["plan_hash"] != world.c.get_org(b)["plan_hash"]

    def test_no_founder_privileges(self, world):
        """The founder is provenance only: nothing in the public ABI is owner-gated."""
        names = [n for n in dir(world.c.__class__) if not n.startswith("_")]
        for forbidden in ("owner", "admin", "pause", "set_", "withdraw", "kill", "upgrade", "transfer_ownership"):
            assert not [n for n in names if forbidden in n.lower()], forbidden

    @pytest.mark.parametrize(
        "overrides,fragment",
        [
            (dict(name=""), "name length"),
            (dict(name="x" * 81), "name length"),
            (dict(charter=""), "charter length"),
            (dict(charter="x" * 2001), "charter length"),
            (dict(plan=""), "plan length"),
            (dict(plan="x" * 1501), "plan length"),
            (dict(criteria=[]), "criteria"),
            (dict(criteria=["c"] * 9), "criteria"),
            (dict(criteria=["ok", ""]), "criterion length"),
            (dict(criteria=["x" * 201]), "criterion length"),
            (dict(min_reserve=0), "min_reserve"),
            (dict(max_spend_bps=0), "max_spend_bps"),
            (dict(max_spend_bps=5001), "max_spend_bps"),
            (dict(spend_cooldown=10 * 365 * DAY + 1), "time parameter"),
            (dict(proposal_window=10 * 365 * DAY + 1), "time parameter"),
            (dict(grace=0), "grace"),
            (dict(proposal_window=0), "proposal_window"),
            (dict(min_criteria=0), "min_criteria"),
            (dict(min_criteria=4), "min_criteria"),
            (dict(value=99), "initial funding"),
        ],
    )
    def test_rejects_invalid_parameters(self, world, overrides, fragment):
        with world.vm.expect_revert(fragment):
            world.make_org(**overrides)
        assert world.c.org_count() == 0

    def test_successor_cannot_be_the_contract_itself(self, world):
        with world.vm.expect_revert("successor cannot be this contract"):
            world.make_org(successor=hexof(world.vm._contract_address))

    def test_boundary_values_are_accepted(self, world):
        org = world.make_org(
            name="x" * 80, charter="c" * 2000, plan="p" * 1500, criteria=["k" * 200] * 8,
            min_reserve=1, max_spend_bps=5000, min_criteria=8, grace=1, proposal_window=1,
            value=1, proposal_bond=0, spend_cooldown=0,
        )
        assert world.c.is_active(org)


# ------------------------------------------------------------------ funding
class TestFund:
    def test_fund_tracks_balance_and_contributors(self, world):
        org = world.make_org()
        world.fund(org, 300, sender=world.bob)
        world.fund(org, 200, sender=world.bob)
        world.fund(org, 5, sender=world.charlie)
        o = world.c.get_org(org)
        assert o["balance"] == 1505 and o["total_contributed"] == 1505
        assert world.c.contribution_of(org, world.bob) == 500
        assert world.c.contribution_of(org, world.charlie) == 5
        assert world.c.contribution_of(org, world.alice) == 1000

    def test_fund_unknown_org(self, world):
        world.vm.sender, world.vm.value = world.bob, 5
        with world.vm.expect_revert("unknown organization"):
            world.c.fund(99)

    def test_fund_requires_positive_value(self, world):
        org = world.make_org()
        world.vm.sender, world.vm.value = world.bob, 0
        with world.vm.expect_revert("positive amount"):
            world.c.fund(org)

    def test_funding_revives_a_dormant_org(self, world):
        org = world.make_org(value=120, max_spend_bps=5000)
        pid = world.spend_proposal(org, amount=60)
        assert world.resolve(pid) == "EXECUTED"
        assert world.c.get_org(org)["status"] == "DORMANT"
        assert world.c.is_active(org) is False
        world.fund(org, 100)
        assert world.c.get_org(org)["status"] == "ACTIVE"
        assert world.c.get_org(org)["dormant_since"] == 0
        assert world.c.is_active(org) is True

    def test_partial_funding_keeps_it_dormant(self, world):
        org = world.make_org(value=120, max_spend_bps=5000)
        world.resolve(world.spend_proposal(org, amount=60))
        world.fund(org, 10)  # 70 < reserve 100
        assert world.c.get_org(org)["status"] == "DORMANT"


# --------------------------------------------------------------- adaptation
class TestAdaptation:
    def test_conforming_adaptation_is_adopted_and_bond_returned(self, world):
        org = world.make_org()
        new_plan = "Also fund documentation of open climate datasets."
        pid = world.adapt_proposal(org, new_plan)
        assert world.resolve_adapt(pid) == "ADOPTED"
        o = world.c.get_org(org)
        assert o["plan"] == new_plan and o["plan_version"] == 2
        assert world.c.plan_state(org)["version"] == 2
        assert world.c.is_plan_current(org, o["plan_hash"]) is True
        assert world.paid_to(world.bob) == 10  # bond back to proposer
        assert world.c.is_action_authorized(pid) is True
        assert world.c.get_org(org)["balance"] == 1000  # treasury untouched

    def test_violating_adaptation_is_rejected_and_bond_forfeited(self, world):
        org = world.make_org()
        pid = world.adapt_proposal(org, "Pivot to building surveillance tools.")
        assert world.resolve_adapt(pid, llm=verdict_json("VIOLATES", 0, quote="")) == "REJECTED"
        o = world.c.get_org(org)
        assert o["plan"] == PLAN and o["plan_version"] == 1
        assert o["balance"] == 1010  # bond joined the treasury
        assert world.paid_to(world.bob) == 0
        assert world.c.get_proposal(pid)["bond"] == 0
        assert world.c.is_action_authorized(pid) is False

    def test_unclear_adaptation_retries_then_expires_with_bond_refund(self, world):
        org = world.make_org()
        pid = world.adapt_proposal(org)
        unclear = verdict_json("UNCLEAR", 0, quote="")
        assert world.resolve_adapt(pid, llm=unclear) == "PENDING"
        assert world.resolve_adapt(pid, llm=unclear) == "PENDING"
        assert world.c.get_proposal(pid)["attempts"] == 2
        assert world.resolve_adapt(pid, llm=unclear) == "EXPIRED"
        assert world.c.get_proposal(pid)["verdict"] == "UNCLEAR"
        assert world.paid_to(world.bob) == 10
        assert world.c.get_org(org)["plan_version"] == 1

    def test_adopted_plan_makes_sibling_proposals_stale(self, world):
        org = world.make_org()
        first = world.adapt_proposal(org, "Plan B: fund tools for open sea-level data.")
        second = world.adapt_proposal(org, "Plan C: fund tools for open glacier data.", sender=world.charlie)
        assert world.resolve_adapt(first) == "ADOPTED"
        with world.vm.expect_revert("plan changed"):
            world.resolve_adapt(second)
        world.vm.sender = world.alice
        world.c.expire_proposal(second)
        assert world.c.get_proposal(second)["status"] == "EXPIRED"
        assert world.paid_to(world.charlie) == 10
        assert world.c.get_org(org)["plan_version"] == 2

    def test_adaptation_bond_must_be_exact(self, world):
        org = world.make_org()
        for wrong in (0, 9, 11):
            world.vm.sender, world.vm.value = world.bob, wrong
            with world.vm.expect_revert("exact"):
                world.c.propose_adaptation(org, "x")

    def test_adaptation_plan_length_bounds(self, world):
        org = world.make_org()
        world.vm.sender, world.vm.value = world.bob, 10
        with world.vm.expect_revert("plan length"):
            world.c.propose_adaptation(org, "")
        with world.vm.expect_revert("plan length"):
            world.c.propose_adaptation(org, "x" * 1501)

    def test_adaptation_needs_no_web_access(self, world):
        """ADAPT is judged without any fetch: a registered web mock must stay unused."""
        org = world.make_org()
        pid = world.adapt_proposal(org)
        world.reset_mocks()
        world.vm.mock_llm(r"CHARTERKEEPER_JUDGE", verdict_json(met_mask=0, quote=""))
        world.vm.sender = world.charlie
        assert world.c.resolve(pid) == "ADOPTED"  # no web mock registered; any fetch would fail


# ------------------------------------------------------------------- spend
class TestSpend:
    def test_successful_spend_pays_recipient_and_returns_bond(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org, amount=150)
        assert world.resolve(pid) == "EXECUTED"
        p = world.c.get_proposal(pid)
        assert p["verdict"] == "CONFORMS" and p["met_mask"] == 0b111 and p["bond"] == 0
        assert world.c.get_org(org)["balance"] == 850
        assert world.paid_to(world.charlie) == 150
        assert world.paid_to(world.bob) == 10
        assert all(t["on"] == "finalized" for t in world.sent)
        assert world.c.is_action_authorized(pid) is True

    def test_state_is_final_before_transfers_so_replay_is_impossible(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        world.resolve(pid)
        with world.vm.expect_revert("already settled"):
            world.resolve(pid)
        assert world.paid_to(world.charlie) == 100  # exactly once

    def test_cooldown_blocks_second_spend_until_it_elapses(self, world):
        org = world.make_org()
        first = world.spend_proposal(org, amount=50)
        second = world.spend_proposal(org, amount=50)
        assert world.resolve(first) == "EXECUTED"
        with world.vm.expect_revert("cooldown"):
            world.resolve(second)
        assert world.c.next_spend_time(org) > 0
        world.at(DAY - 1)
        with world.vm.expect_revert("cooldown"):
            world.resolve(second)
        world.at(DAY)
        assert world.resolve(second) == "EXECUTED"
        assert world.c.get_org(org)["balance"] == 900

    def test_zero_cooldown_allows_back_to_back_spends(self, world):
        org = world.make_org(spend_cooldown=0)
        a, b = world.spend_proposal(org, amount=10), world.spend_proposal(org, amount=10)
        assert world.resolve(a) == "EXECUTED" and world.resolve(b) == "EXECUTED"

    def test_per_spend_cap_enforced_at_proposal(self, world):
        org = world.make_org()
        assert world.c.max_single_spend(org) == 200
        world.vm.sender, world.vm.value = world.bob, 10
        with world.vm.expect_revert("per-spend cap"):
            world.c.propose_spend(org, "p", GOOD_URL, world.charlie, 201, 0b111)
        pid = world.spend_proposal(org, amount=200)  # exactly the cap
        assert world.resolve(pid) == "EXECUTED"

    def test_cap_is_rechecked_at_resolution_after_the_treasury_shrinks(self, world):
        org = world.make_org(spend_cooldown=0)
        big = world.spend_proposal(org, amount=200)
        other = world.spend_proposal(org, amount=200)
        assert world.resolve(big) == "EXECUTED"  # balance 800 -> cap now 160
        with world.vm.expect_revert("per-spend cap"):
            world.resolve(other)

    def test_insufficient_criteria_is_not_paid(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org, mask=0b111)  # claims 3, min is 2
        assert world.resolve(pid, llm=verdict_json("CONFORMS", 0b001)) == "PENDING"
        p = world.c.get_proposal(pid)
        assert p["verdict"] == "INSUFFICIENT" and p["attempts"] == 1
        assert world.paid_to(world.charlie) == 0
        assert world.c.get_org(org)["balance"] == 1000

    def test_only_claimed_criteria_count(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org, mask=0b011)
        # the page demonstrates criterion 2 only, which was not claimed
        assert world.resolve(pid, llm=verdict_json("CONFORMS", 0b100)) == "PENDING"
        assert world.c.get_proposal(pid)["verdict"] == "INSUFFICIENT"

    def test_violating_spend_is_rejected_and_bond_forfeited(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org, purpose="Buy surveillance drones")
        assert world.resolve(pid, llm=verdict_json("VIOLATES", 0, quote="")) == "REJECTED"
        assert world.c.get_org(org)["balance"] == 1010
        assert world.total_paid() == 0

    def test_unclear_spend_expires_after_max_attempts_with_bond_refund(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        for expected in ("PENDING", "PENDING", "EXPIRED"):
            assert world.resolve(pid, llm=verdict_json("UNCLEAR", 0, quote="")) == expected
        assert world.paid_to(world.bob) == 10 and world.paid_to(world.charlie) == 0

    def test_unreachable_evidence_is_unavailable_not_a_verdict(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        assert world.resolve(pid, status=503) == "PENDING"
        p = world.c.get_proposal(pid)
        assert p["verdict"] == "UNAVAILABLE" and p["attempts"] == 1
        assert world.c.get_org(org)["plan_version"] == 1 and world.c.get_org(org)["balance"] == 1000
        # the source recovers: the same proposal can still succeed
        assert world.resolve(pid) == "EXECUTED"

    def test_unreachable_three_times_expires_with_bond_refund(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        results = [world.resolve(pid, status=404) for _ in range(3)]
        assert results == ["PENDING", "PENDING", "EXPIRED"]
        assert world.paid_to(world.bob) == 10 and world.paid_to(world.charlie) == 0

    def test_injection_flag_fails_closed_even_with_conforming_verdict(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        out = world.resolve(pid, llm=verdict_json("CONFORMS", 0b111, injection=True))
        assert out == "PENDING" and world.c.get_proposal(pid)["verdict"] == "UNCLEAR"
        assert world.total_paid() == 0

    def test_ungrounded_quote_downgrades_approval(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        out = world.resolve(pid, llm=verdict_json("CONFORMS", 0b111, quote="This sentence is not on the page at all"))
        assert out == "PENDING" and world.c.get_proposal(pid)["verdict"] == "UNCLEAR"
        assert world.total_paid() == 0

    def test_quote_grounding_ignores_case_and_whitespace(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        spaced = "release   1.0 PUBLISHED under the mit licence\nwith full docs"
        assert world.resolve(pid, llm=verdict_json("CONFORMS", 0b111, quote=spaced)) == "EXECUTED"

    def test_short_quote_is_not_grounding(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        assert world.resolve(pid, llm=verdict_json("CONFORMS", 0b111, quote="Release")) == "PENDING"

    def test_spend_can_push_the_org_into_dormancy(self, world):
        org = world.make_org(value=120, max_spend_bps=5000)
        pid = world.spend_proposal(org, amount=60)
        assert world.resolve(pid) == "EXECUTED"
        o = world.c.get_org(org)
        assert o["balance"] == 60 and o["status"] == "DORMANT" and o["dormant_since"] > 0
        assert world.c.dissolution_time(org) == o["dormant_since"] + o["grace"]
        assert world.c.is_active(org) is False

    def test_dormant_org_cannot_propose_or_resolve(self, world):
        org = world.make_org(value=120, max_spend_bps=5000, spend_cooldown=0)
        pending = world.spend_proposal(org, amount=10)
        other = world.spend_proposal(org, amount=60)
        world.resolve(other)  # -> dormant
        world.vm.sender, world.vm.value = world.bob, 10
        with world.vm.expect_revert("not active"):
            world.c.propose_adaptation(org, "x")
        with world.vm.expect_revert("not active"):
            world.resolve(pending)

    def test_spend_proposal_validation(self, world):
        org = world.make_org()
        world.vm.sender, world.vm.value = world.bob, 10
        bad = [
            (dict(purpose=""), "purpose length"),
            (dict(purpose="x" * 1001), "purpose length"),
            (dict(recipient=ZERO), "invalid recipient"),
            (dict(recipient=hexof(world.vm._contract_address)), "invalid recipient"),
            (dict(amount=0), "per-spend cap"),
            (dict(mask=0), "mask out of range"),
            (dict(mask=0b1000), "mask out of range"),
            (dict(mask=0b001), "below the charter minimum"),
        ]
        for override, fragment in bad:
            args = dict(purpose="p", url=GOOD_URL, recipient=world.charlie, amount=10, mask=0b011)
            args.update(override)
            with world.vm.expect_revert(fragment):
                world.c.propose_spend(org, args["purpose"], args["url"], args["recipient"], args["amount"], args["mask"])
        assert world.c.proposal_count() == 0

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.org/x",
            "ftp://example.org/x",
            "https://user:pw@example.org/x",
            "https://example.org:8443/x",
            "https://localhost/x",
            "https://app.localhost/x",
            "https://printer.local/x",
            "https://db.internal/x",
            "https://127.0.0.1/x",
            "https://10.0.0.5/x",
            "https://169.254.169.254/latest/meta-data",
            "https://0177.0.0.1/x",
            "https://2130706433/x",
            "https://[::1]/x",
            "https://exa mple.org/x",
            "https://-bad-.example.org/x",
            "https://example..org/x",
            "https://singlelabel/x",
            "https://",
            "https://example.org/" + "a" * 300,
            "",
        ],
    )
    def test_hostile_or_malformed_urls_are_rejected(self, world, url):
        org = world.make_org()
        world.vm.sender, world.vm.value = world.bob, 10
        with world.vm.expect_revert("evidence url"):
            world.c.propose_spend(org, "p", url, world.charlie, 10, 0b011)

    @pytest.mark.parametrize(
        "url",
        ["https://example.org/a", "https://sub.example.org/a?q=1#f", "https://EXAMPLE.org/A", "https://a-b.example.co.uk"],
    )
    def test_ordinary_https_urls_are_accepted(self, world, url):
        org = world.make_org()
        assert world.spend_proposal(org, url=url, amount=10) == 1


# ------------------------------------------------------------ expiry / ids
class TestExpiry:
    def test_cannot_expire_a_resolvable_proposal(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        with world.vm.expect_revert("still resolvable"):
            world.c.expire_proposal(pid)

    def test_expire_after_deadline_refunds_bond_once(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        world.at(14 * DAY)  # exactly the deadline: still resolvable
        with world.vm.expect_revert("still resolvable"):
            world.c.expire_proposal(pid)
        world.at(14 * DAY + 1)
        world.vm.sender = world.alice
        world.c.expire_proposal(pid)
        assert world.c.get_proposal(pid)["status"] == "EXPIRED"
        assert world.paid_to(world.bob) == 10
        with world.vm.expect_revert("already settled"):
            world.c.expire_proposal(pid)
        assert world.paid_to(world.bob) == 10

    def test_resolve_after_deadline_is_refused(self, world):
        org = world.make_org()
        pid = world.spend_proposal(org)
        world.at(14 * DAY + 1)
        with world.vm.expect_revert("window closed"):
            world.resolve(pid)

    def test_unknown_ids(self, world):
        with world.vm.expect_revert("unknown proposal"):
            world.c.resolve(5)
        with world.vm.expect_revert("unknown proposal"):
            world.c.expire_proposal(5)
        with world.vm.expect_revert("unknown proposal"):
            world.c.get_proposal(5)
        with world.vm.expect_revert("unknown organization"):
            world.c.get_org(5)
        with world.vm.expect_revert("unknown organization"):
            world.c.heartbeat(5)
        with world.vm.expect_revert("unknown organization"):
            world.c.is_active(5)


# ---------------------------------------------------- liveness / dissolution
class TestLiveness:
    def _dormant(self, world, **kw):
        org = world.make_org(value=120, max_spend_bps=5000, **kw)
        world.resolve(world.spend_proposal(org, amount=60))
        assert world.c.get_org(org)["status"] == "DORMANT"
        return org

    def test_heartbeat_does_not_dissolve_an_active_org(self, world):
        org = world.make_org()
        world.at(365 * DAY)
        world.vm.sender = world.charlie
        assert world.c.heartbeat(org) == "ACTIVE"

    def test_heartbeat_waits_for_the_grace_period(self, world):
        org = self._dormant(world)
        world.at(7 * DAY - 1)
        assert world.c.heartbeat(org) == "DORMANT"
        world.at(7 * DAY)
        assert world.c.heartbeat(org) == "DISSOLVED"

    def test_dissolution_without_successor_opens_a_refund_pool(self, world):
        org = self._dormant(world)
        world.at(7 * DAY)
        world.c.heartbeat(org)
        o = world.c.get_org(org)
        assert o["status"] == "DISSOLVED" and o["balance"] == 0
        assert o["refund_pool"] == 60 and o["refund_total"] == 120

    def test_refunds_are_pro_rata_and_drain_the_pool_exactly(self, world):
        org = self._dormant(world)
        world.fund(org, 30, sender=world.charlie)  # still < reserve: 90, stays dormant
        # alice contributed 120, charlie 30 -> pool 90, total 150
        world.at(7 * DAY)
        world.c.heartbeat(org)
        world.vm.sender = world.alice
        a = world.c.claim_refund(org)
        world.vm.sender = world.charlie
        c = world.c.claim_refund(org)
        assert (a, c) == (72, 18)
        assert world.paid_to(world.alice) == 72
        assert world.paid_to(world.charlie) == 60 + 18  # 60 was the earlier spend payout
        assert world.c.get_org(org)["refund_pool"] == 0 and world.c.get_org(org)["refund_total"] == 0

    def test_refund_cannot_be_claimed_twice_or_by_strangers(self, world):
        org = self._dormant(world)
        world.at(7 * DAY)
        world.c.heartbeat(org)
        world.vm.sender = world.alice
        world.c.claim_refund(org)
        before = world.total_paid()
        with world.vm.expect_revert("nothing to claim"):
            world.c.claim_refund(org)
        world.vm.sender = world.bob  # never contributed to this org
        with world.vm.expect_revert("nothing to claim"):
            world.c.claim_refund(org)
        assert world.total_paid() == before

    def test_refund_not_available_before_dissolution_or_with_successor(self, world):
        org = world.make_org()
        world.vm.sender = world.alice
        with world.vm.expect_revert("no refund pool"):
            world.c.claim_refund(org)

    def test_successor_receives_the_balance_on_dissolution(self, world):
        successor = hexof(world.charlie)
        org = self._dormant(world, successor=successor)
        world.at(7 * DAY)
        world.c.heartbeat(org)
        assert world.c.get_org(org)["balance"] == 0
        assert world.sent[-1] == {"to": successor, "value": 60, "on": "finalized"}
        world.vm.sender = world.alice
        with world.vm.expect_revert("no refund pool"):
            world.c.claim_refund(org)

    def test_funding_before_dissolution_revives_the_org(self, world):
        org = self._dormant(world)
        world.at(7 * DAY - 10)
        world.fund(org, 50)
        world.at(30 * DAY)
        assert world.c.heartbeat(org) == "ACTIVE"
        assert world.c.is_active(org)

    def test_dissolved_org_is_terminal(self, world):
        org = self._dormant(world)
        world.at(7 * DAY)
        world.c.heartbeat(org)
        world.vm.sender, world.vm.value = world.bob, 10
        with world.vm.expect_revert("dissolved"):
            world.c.fund(org)
        with world.vm.expect_revert("dissolved"):
            world.c.heartbeat(org)
        with world.vm.expect_revert("not active"):
            world.c.propose_adaptation(org, "x")

    def test_pending_proposals_of_a_dissolved_org_can_be_expired_for_their_bonds(self, world):
        org = world.make_org(value=120, max_spend_bps=5000, spend_cooldown=0)
        pending = world.spend_proposal(org, amount=10)
        world.resolve(world.spend_proposal(org, amount=60))  # -> dormant
        world.at(7 * DAY)
        world.c.heartbeat(org)
        before = world.paid_to(world.bob)
        world.vm.sender = world.alice
        world.c.expire_proposal(pending)
        assert world.paid_to(world.bob) - before == 10


# ------------------------------------------------------------ consumer views
class TestConsumerSurface:
    def test_views_need_no_llm_or_web_access(self, world):
        org = world.make_org()
        world.reset_mocks()  # strict mocks: any nondet call would raise
        assert world.c.is_active(org) is True
        assert world.c.status_of(org) == "ACTIVE"
        assert len(world.c.charter_hash(org)) == 64
        assert world.c.plan_state(org) == {"version": 1, "hash": world.c.get_org(org)["plan_hash"]}
        assert world.c.max_single_spend(org) == 200
        assert world.c.next_spend_time(org) == 0
        assert world.c.dissolution_time(org) == 0

    def test_is_action_authorized_only_for_conforming_settled_proposals(self, world):
        org = world.make_org()
        pending = world.spend_proposal(org)
        assert world.c.is_action_authorized(pending) is False
        assert world.resolve(pending) == "EXECUTED"
        assert world.c.is_action_authorized(pending) is True
        rejected = world.adapt_proposal(org, "Pivot to surveillance.")
        world.resolve_adapt(rejected, llm=verdict_json("VIOLATES", 0, quote=""))
        assert world.c.is_action_authorized(rejected) is False

    def test_is_plan_current_detects_stale_expectations(self, world):
        org = world.make_org()
        original = world.c.get_org(org)["plan_hash"]
        world.resolve_adapt(world.adapt_proposal(org))
        assert world.c.is_plan_current(org, original) is False
        assert world.c.is_plan_current(org, world.c.get_org(org)["plan_hash"]) is True

    def test_charter_hash_is_stable_across_plan_changes(self, world):
        org = world.make_org()
        before = world.c.charter_hash(org)
        world.resolve_adapt(world.adapt_proposal(org))
        assert world.c.charter_hash(org) == before


# ---------------------------------------------------------- value accounting
class TestValueConservation:
    def test_every_unit_is_accounted_for_across_a_busy_lifecycle(self, world):
        org = world.make_org(value=1000, spend_cooldown=0)
        world.fund(org, 400, sender=world.charlie)
        assert world.resolve(world.spend_proposal(org, amount=100)) == "EXECUTED"
        assert world.resolve(world.spend_proposal(org, amount=100), llm=verdict_json("VIOLATES", 0, quote="")) == "REJECTED"
        pid = world.spend_proposal(org, amount=100)
        assert world.resolve(pid, status=500) == "PENDING"  # bond stays escrowed
        world.resolve_adapt(world.adapt_proposal(org))
        assert world.deposited == world.total_paid() + world.held()

    def test_conservation_through_dissolution_and_refunds(self, world):
        org = world.make_org(value=120, max_spend_bps=5000)
        world.fund(org, 30, sender=world.charlie)
        world.resolve(world.spend_proposal(org, amount=60))
        world.at(7 * DAY)
        world.c.heartbeat(org)
        for who in (world.alice, world.charlie):
            world.vm.sender = who
            world.c.claim_refund(org)
        assert world.deposited == world.total_paid() + world.held()
        assert world.c.get_org(org)["refund_pool"] == 0

    def test_expired_and_rejected_bond_paths_conserve_value(self, world):
        org = world.make_org()
        a = world.spend_proposal(org)
        b = world.adapt_proposal(org, sender=world.charlie)
        world.resolve(a, llm=verdict_json("VIOLATES", 0, quote=""))
        world.at(14 * DAY + 1)
        world.c.expire_proposal(b)
        assert world.deposited == world.total_paid() + world.held()
