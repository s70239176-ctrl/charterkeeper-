"""
Real-network CharterKeeper tests: real deployment, real validators, real consensus,
real web fetches and real LLM judgments on hosted Studionet.

    gltest tests/integration/ -v -s --network studionet

Each test deploys its own disposable contract, so tests are independent and can be run
alone. These deployments are NOT the canonical submission deployment (see docs/DEPLOYMENT.md).

The evidence fixtures are fetched by the validators from raw.githubusercontent.com, so they
must be pushed to the default branch before these tests can pass.

Assertions are on settlement-critical state (status, verdict class, balances), never on LLM prose.
"""
import os
import secrets

import pytest
from gltest import get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

ZERO = "0x" + "00" * 20
RAW = os.environ.get(
    "CHARTERKEEPER_FIXTURE_BASE",
    "https://raw.githubusercontent.com/s70239176-ctrl/charterkeeper-/main/fixtures",
)
GOOD_URL = f"{RAW}/release_report_good.md"
EMPTY_URL = f"{RAW}/release_report_empty.md"
HOSTILE_URL = f"{RAW}/release_report_hostile.md"

CHARTER = (
    "Mission: fund and maintain open-source climate-data tooling. Never fund weapons, "
    "surveillance, or anything unrelated to open climate data."
)
CRITERIA = [
    "A new software release was publicly published",
    "The release ships with user documentation",
    "The code is released under an open-source licence",
]
PLAN = "Fund maintainers of existing open climate-data libraries with small grants."
BOND = 5
ROTATIONS = 3


def random_address() -> str:
    return "0x" + secrets.token_hex(20)


def deploy():
    factory = get_contract_factory(contract_file_path="charterkeeper.py")
    return factory.deploy(account=get_default_account(), consensus_max_rotations=ROTATIONS)


def send(method, args, value=0):
    """Submit a write and assert the transaction itself executed (never trust setup blindly)."""
    receipt = method(args=args).transact(value=value, consensus_max_rotations=ROTATIONS)
    assert tx_execution_succeeded(receipt), f"{receipt.get('status_name')} / {receipt.get('result_name')}"
    return receipt


def create_org(contract, **overrides):
    params = dict(
        name="Open Climate Trust", charter=CHARTER, criteria=CRITERIA, plan=PLAN,
        min_reserve=100, max_spend_bps=5000, spend_cooldown=0, grace=1, min_criteria=2,
        proposal_bond=BOND, proposal_window=86400, successor=ZERO, value=1000,
    )
    params.update(overrides)
    value = params.pop("value")
    send(contract.create_org, [
        params["name"], params["charter"], params["criteria"], params["plan"],
        params["min_reserve"], params["max_spend_bps"], params["spend_cooldown"],
        params["grace"], params["min_criteria"], params["proposal_bond"],
        params["proposal_window"], params["successor"],
    ], value=value)
    org_id = int(contract.org_count(args=[]).call())
    assert org_id >= 1
    assert contract.get_org(args=[org_id]).call()["status"] == "ACTIVE"
    return org_id


def propose_spend(contract, org_id, url, amount=100, mask=0b111, purpose="Ship Open Climate Data Toolkit 2.0"):
    send(contract.propose_spend, [org_id, purpose, url, random_address(), amount, mask], value=BOND)
    pid = int(contract.proposal_count(args=[]).call())
    p = contract.get_proposal(args=[pid]).call()
    assert p["status"] == "PENDING" and p["bond"] == BOND  # setup really happened
    return pid


def test_deploy_and_public_surface():
    contract = deploy()
    assert int(contract.org_count(args=[]).call()) == 0
    org_id = create_org(contract)
    o = contract.get_org(args=[org_id]).call()
    assert o["balance"] == 1000 and o["plan_version"] == 1 and o["criteria"] == CRITERIA
    assert contract.is_active(args=[org_id]).call() is True
    assert contract.status_of(args=[org_id]).call() == "ACTIVE"
    assert len(contract.charter_hash(args=[org_id]).call()) == 64
    assert contract.plan_state(args=[org_id]).call()["version"] == 1
    assert int(contract.max_single_spend(args=[org_id]).call()) == 500


def test_conforming_spend_is_judged_by_validators_and_settles():
    contract = deploy()
    org_id = create_org(contract)
    pid = propose_spend(contract, org_id, GOOD_URL, amount=100)
    send(contract.resolve, [pid])
    p = contract.get_proposal(args=[pid]).call()
    assert p["status"] == "EXECUTED" and p["verdict"] == "CONFORMS"
    assert bin(p["met_mask"] & 0b111).count("1") >= 2  # at least the charter minimum
    assert p["bond"] == 0
    assert contract.get_org(args=[org_id]).call()["balance"] == 900
    assert contract.is_action_authorized(args=[pid]).call() is True


@pytest.mark.parametrize("url", [HOSTILE_URL, EMPTY_URL], ids=["prompt_injection_page", "irrelevant_page"])
def test_hostile_or_irrelevant_evidence_never_releases_funds(url):
    contract = deploy()
    org_id = create_org(contract)
    pid = propose_spend(contract, org_id, url, amount=100)
    send(contract.resolve, [pid])
    p = contract.get_proposal(args=[pid]).call()
    assert p["status"] != "EXECUTED"
    assert p["verdict"] != "CONFORMS"
    assert contract.is_action_authorized(args=[pid]).call() is False
    # the treasury only ever grew (a forfeited bond) - nothing was released
    assert contract.get_org(args=[org_id]).call()["balance"] >= 1000


def test_adaptation_must_conform_to_the_charter():
    contract = deploy()
    org_id = create_org(contract)

    good = "Also fund documentation efforts for open climate datasets."
    send(contract.propose_adaptation, [org_id, good], value=BOND)
    send(contract.resolve, [int(contract.proposal_count(args=[]).call())])
    o = contract.get_org(args=[org_id]).call()
    assert o["plan"] == good and o["plan_version"] == 2

    bad = "Pivot to buying surveillance drones and weapons for private clients."
    send(contract.propose_adaptation, [org_id, bad], value=BOND)
    bad_id = int(contract.proposal_count(args=[]).call())
    send(contract.resolve, [bad_id])
    p = contract.get_proposal(args=[bad_id]).call()
    o = contract.get_org(args=[org_id]).call()
    assert p["status"] != "ADOPTED" and p["verdict"] in ("VIOLATES", "UNCLEAR")
    assert o["plan"] == good and o["plan_version"] == 2  # the charter-violating plan never took effect


def test_funding_lapse_dormancy_dissolution_and_refund():
    contract = deploy()
    # 120 funded, reserve 100, cap 50%: one conforming 60 spend drops the org below its reserve
    org_id = create_org(contract, value=120, min_reserve=100, max_spend_bps=5000, grace=1)
    pid = propose_spend(contract, org_id, GOOD_URL, amount=60)
    send(contract.resolve, [pid])
    assert contract.get_proposal(args=[pid]).call()["status"] == "EXECUTED"
    o = contract.get_org(args=[org_id]).call()
    assert o["balance"] == 60 and o["status"] == "DORMANT"
    assert contract.is_active(args=[org_id]).call() is False

    # the 1-second grace period has passed by the time the next transaction lands
    send(contract.heartbeat, [org_id])
    o = contract.get_org(args=[org_id]).call()
    assert o["status"] == "DISSOLVED" and o["refund_pool"] == 60

    send(contract.claim_refund, [org_id])
    o = contract.get_org(args=[org_id]).call()
    assert o["refund_pool"] == 0 and o["refund_total"] == 0
    # a second claim has nothing left to take
    with pytest.raises(Exception):
        contract.claim_refund(args=[org_id]).transact(consensus_max_rotations=ROTATIONS)
