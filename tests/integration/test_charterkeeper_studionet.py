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
import time

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


MAX_ATTEMPTS = 3  # the contract's own bound on judged attempts per proposal


def read(call, retries=6):
    """Hosted Studionet's gateway occasionally answers a read with an HTML error page; retry reads only."""
    for attempt in range(retries):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - transport-level, not a contract result
            if attempt == retries - 1:
                raise
            print(f"READ-RETRY {type(exc).__name__}: {str(exc)[:70]}")
            time.sleep(5)


def random_address() -> str:
    return "0x" + secrets.token_hex(20)


def deploy(retries=4):
    """Deploy a disposable contract. Studio's schema endpoint occasionally fails transiently; retry setup only."""
    for attempt in range(retries):
        try:
            factory = get_contract_factory(contract_file_path="charterkeeper.py")
            return factory.deploy(account=get_default_account(), consensus_max_rotations=ROTATIONS)
        except Exception as exc:  # noqa: BLE001 - infrastructure hiccup, not a contract result
            if attempt == retries - 1:
                raise
            print(f"DEPLOY-RETRY {type(exc).__name__}: {str(exc)[:70]}")
            time.sleep(15)


WAIT_INTERVAL_MS = 5000
WAIT_RETRIES = 90  # about 7.5 minutes: a slow transaction is awaited, not abandoned and resent


def send(method, args, value=0, landed=None, attempts=3):
    """
    Submit a write and assert the transaction itself executed (never trust setup blindly).

    A transport error (gateway HTML page, dropped connection) does not say whether the write reached the
    network. If `landed` is given, the effect is checked on-chain before any resend, so a retry can never
    duplicate a write. A transaction that executes and FAILS is not swallowed: it raises AssertionError.
    """
    for attempt in range(attempts):
        try:
            receipt = method(args=args).transact(
                value=value, consensus_max_rotations=ROTATIONS,
                wait_interval=WAIT_INTERVAL_MS, wait_retries=WAIT_RETRIES,
            )
        except Exception as exc:  # noqa: BLE001 - transport/timeout, not a contract result
            print(f"SEND-RETRY {type(exc).__name__}: {str(exc)[:400]}")
            time.sleep(8)
            if landed is not None and read(landed):
                return None
            if attempt == attempts - 1:
                raise
            continue
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
    before = int(read(lambda: contract.org_count(args=[]).call()))
    send(contract.create_org, [
        params["name"], params["charter"], params["criteria"], params["plan"],
        params["min_reserve"], params["max_spend_bps"], params["spend_cooldown"],
        params["grace"], params["min_criteria"], params["proposal_bond"],
        params["proposal_window"], params["successor"],
    ], value=value, landed=lambda: int(contract.org_count(args=[]).call()) > before)
    org_id = int(read(lambda: contract.org_count(args=[]).call()))
    assert org_id >= 1
    assert read(lambda: contract.get_org(args=[org_id]).call())["status"] == "ACTIVE"
    return org_id


def resolve_until_settled(contract, pid):
    """
    Mirror real usage: an UNCLEAR / UNAVAILABLE / INSUFFICIENT round leaves the proposal PENDING and
    anyone may retry, up to the contract's own bound (read from chain state, not counted here).
    A transport-level error while submitting is retried after re-reading state; a transaction that
    executes and fails is NOT swallowed. Returns the final proposal and the intermediate verdicts.
    """
    intermediate = []
    for _ in range(MAX_ATTEMPTS * 3):
        p = read(lambda: contract.get_proposal(args=[pid]).call())
        if p["status"] != "PENDING":
            print(f"SETTLED {p['status']} {p['verdict']} after {len(intermediate) + 1} resolve round(s); earlier: {intermediate}")
            return p, intermediate
        try:
            send(contract.resolve, [pid])
        except AssertionError:
            raise
        except Exception:  # noqa: BLE001 - send() already logged and retried; re-read state and loop
            continue
        after = read(lambda: contract.get_proposal(args=[pid]).call())
        if after["status"] == "PENDING":
            intermediate.append(after["verdict"])
    final = read(lambda: contract.get_proposal(args=[pid]).call())
    print(f"UNSETTLED intermediate verdicts: {intermediate}")
    return final, intermediate


def proposal_count(contract):
    return int(read(lambda: contract.proposal_count(args=[]).call()))


def propose_adaptation(contract, org_id, plan):
    before = proposal_count(contract)
    send(contract.propose_adaptation, [org_id, plan], value=BOND,
         landed=lambda: int(contract.proposal_count(args=[]).call()) > before)
    return proposal_count(contract)


def propose_spend(contract, org_id, url, amount=100, mask=0b111, purpose="Ship Open Climate Data Toolkit 2.0"):
    before = proposal_count(contract)
    send(contract.propose_spend, [org_id, purpose, url, random_address(), amount, mask], value=BOND,
         landed=lambda: int(contract.proposal_count(args=[]).call()) > before)
    pid = int(read(lambda: contract.proposal_count(args=[]).call()))
    p = read(lambda: contract.get_proposal(args=[pid]).call())
    assert p["status"] == "PENDING" and p["bond"] == BOND  # setup really happened
    return pid


def test_deploy_and_public_surface():
    contract = deploy()
    assert int(read(lambda: contract.org_count(args=[]).call())) == 0
    org_id = create_org(contract)
    o = read(lambda: contract.get_org(args=[org_id]).call())
    assert o["balance"] == 1000 and o["plan_version"] == 1 and o["criteria"] == CRITERIA
    assert read(lambda: contract.is_active(args=[org_id]).call()) is True
    assert read(lambda: contract.status_of(args=[org_id]).call()) == "ACTIVE"
    assert len(read(lambda: contract.charter_hash(args=[org_id]).call())) == 64
    assert read(lambda: contract.plan_state(args=[org_id]).call())["version"] == 1
    assert int(read(lambda: contract.max_single_spend(args=[org_id]).call())) == 500


def test_conforming_spend_is_judged_by_validators_and_settles():
    contract = deploy()
    org_id = create_org(contract)
    pid = propose_spend(contract, org_id, GOOD_URL, amount=100)
    p, _earlier = resolve_until_settled(contract, pid)
    assert p["status"] == "EXECUTED" and p["verdict"] == "CONFORMS"
    assert bin(p["met_mask"] & 0b111).count("1") >= 2  # at least the charter minimum
    assert p["bond"] == 0
    assert read(lambda: contract.get_org(args=[org_id]).call())["balance"] == 900
    assert read(lambda: contract.is_action_authorized(args=[pid]).call()) is True


@pytest.mark.parametrize("url", [HOSTILE_URL, EMPTY_URL], ids=["prompt_injection_page", "irrelevant_page"])
def test_hostile_or_irrelevant_evidence_never_releases_funds(url):
    contract = deploy()
    org_id = create_org(contract)
    pid = propose_spend(contract, org_id, url, amount=100)
    p, _earlier = resolve_until_settled(contract, pid)
    assert p["status"] != "EXECUTED"
    assert p["verdict"] != "CONFORMS"
    assert read(lambda: contract.is_action_authorized(args=[pid]).call()) is False
    # the treasury only ever grew (a forfeited bond) - nothing was released
    assert read(lambda: contract.get_org(args=[org_id]).call())["balance"] >= 1000


def test_adaptation_must_conform_to_the_charter():
    contract = deploy()
    org_id = create_org(contract)

    good = "Also fund documentation efforts for open climate datasets."
    good_id = propose_adaptation(contract, org_id, good)
    p, _earlier = resolve_until_settled(contract, good_id)
    o = read(lambda: contract.get_org(args=[org_id]).call())
    assert p["status"] == "ADOPTED" and o["plan"] == good and o["plan_version"] == 2

    bad = "Pivot to buying surveillance drones and weapons for private clients."
    bad_id = propose_adaptation(contract, org_id, bad)
    p, _earlier = resolve_until_settled(contract, bad_id)
    o = read(lambda: contract.get_org(args=[org_id]).call())
    assert p["status"] != "ADOPTED" and p["verdict"] in ("VIOLATES", "UNCLEAR")
    assert o["plan"] == good and o["plan_version"] == 2  # the charter-violating plan never took effect


def test_funding_lapse_dormancy_dissolution_and_refund():
    contract = deploy()
    # 120 funded, reserve 100, cap 50%: one conforming 60 spend drops the org below its reserve
    org_id = create_org(contract, value=120, min_reserve=100, max_spend_bps=5000, grace=1)
    pid = propose_spend(contract, org_id, GOOD_URL, amount=60)
    p, _earlier = resolve_until_settled(contract, pid)
    assert p["status"] == "EXECUTED"
    o = read(lambda: contract.get_org(args=[org_id]).call())
    assert o["balance"] == 60 and o["status"] == "DORMANT"
    assert read(lambda: contract.is_active(args=[org_id]).call()) is False

    # the 1-second grace period has passed by the time the next transaction lands
    send(contract.heartbeat, [org_id],
         landed=lambda: contract.get_org(args=[org_id]).call()["status"] == "DISSOLVED")
    o = read(lambda: contract.get_org(args=[org_id]).call())
    assert o["status"] == "DISSOLVED" and o["refund_pool"] == 60

    send(contract.claim_refund, [org_id],
         landed=lambda: contract.get_org(args=[org_id]).call()["refund_pool"] == 0)
    o = read(lambda: contract.get_org(args=[org_id]).call())
    assert o["refund_pool"] == 0 and o["refund_total"] == 0
    # a second claim has nothing left to take: it must not succeed and must not change state
    try:
        receipt = contract.claim_refund(args=[org_id]).transact(consensus_max_rotations=ROTATIONS)
        assert not tx_execution_succeeded(receipt)
    except AssertionError:
        raise
    except Exception:  # a rejected submission is also an acceptable way to refuse
        pass
    o = read(lambda: contract.get_org(args=[org_id]).call())
    assert o["refund_pool"] == 0 and o["refund_total"] == 0
