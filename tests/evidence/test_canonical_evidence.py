"""
Canonical Studionet deployment + live evidence run. NOT part of the regular suites.

    gltest tests/evidence/ -s --network studionet

Deploys ONE contract, exercises a success path, a negative (hostile evidence) path and a
lifecycle path (dormancy -> dissolution -> refund) with real consensus, and prints a single
`EVIDENCE {json}` line per step containing only public data (hashes, addresses, stored state).
No private key is ever read or printed. Copy the output into docs/DEPLOYMENT.md.
"""
import json
import sys
import time

sys.path.insert(0, "tests/integration")
import test_charterkeeper_studionet as t  # noqa: E402
from gltest import get_contract_factory, get_default_account  # noqa: E402
from gltest.assertions import tx_execution_succeeded  # noqa: E402
from gltest.contracts.utils import extract_contract_address  # noqa: E402
from genlayer_py.types import TransactionStatus  # noqa: E402


def emit(step, **data):
    print("EVIDENCE " + json.dumps({"step": step, **data}, default=str), flush=True)


def receipt_facts(receipt):
    return {
        "tx": receipt.get("hash"),
        "status": receipt.get("status_name"),
        "result": receipt.get("result_name"),
        "rounds": receipt.get("num_of_rounds"),
        "votes": sorted((receipt.get("consensus_data") or {}).get("votes", {}).values()),
    }


def send_logged(step, method, args, value=0):
    receipt = method(args=args).transact(value=value, consensus_max_rotations=t.ROTATIONS)
    assert tx_execution_succeeded(receipt), f"{step}: {receipt.get('status_name')} {receipt.get('result_name')}"
    emit(step, **receipt_facts(receipt))
    return receipt


def settle_logged(step, contract, pid):
    """resolve() until the proposal leaves PENDING (bounded by the contract's own attempt limit)."""
    for round_no in range(1, t.MAX_ATTEMPTS + 1):
        send_logged(f"{step}.resolve#{round_no}", contract.resolve, [pid])
        p = t.read(lambda: contract.get_proposal(args=[pid]).call())
        emit(f"{step}.state#{round_no}", **{k: p[k] for k in ("status", "verdict", "attempts", "met_mask", "amount", "bond")})
        if p["status"] != "PENDING":
            return p
    return p


def test_canonical_evidence():
    account = get_default_account()
    factory = get_contract_factory(contract_file_path="charterkeeper.py")

    # ---- canonical deployment, waiting for real finality
    receipt = factory.deploy_contract_tx(
        account=account,
        consensus_max_rotations=t.ROTATIONS,
        wait_transaction_status=TransactionStatus.FINALIZED,
        wait_interval=10000,
        wait_retries=120,
    )
    assert tx_execution_succeeded(receipt)
    address = extract_contract_address(receipt)
    emit("deploy", deployer=account.address, address=address, **receipt_facts(receipt))
    contract = factory.build_contract(contract_address=address, account=account)

    # ---- A. success path: a conforming, evidenced spend executes
    org_a = t.create_org(contract)
    emit("A.org", org_id=org_a, **{k: v for k, v in t.read(lambda: contract.get_org(args=[org_a]).call()).items() if k in ("status", "balance", "charter_hash")})
    pid_a = t.propose_spend(contract, org_a, t.GOOD_URL, amount=100)
    p = settle_logged("A.spend", contract, pid_a)
    assert p["status"] == "EXECUTED" and p["verdict"] == "CONFORMS"
    emit("A.result", balance=t.read(lambda: contract.get_org(args=[org_a]).call())["balance"],
         authorized=t.read(lambda: contract.is_action_authorized(args=[pid_a]).call()))

    # ---- B. negative path: prompt-injection evidence never releases funds
    org_b = t.create_org(contract)
    pid_b = t.propose_spend(contract, org_b, t.HOSTILE_URL, amount=100)
    p = settle_logged("B.hostile", contract, pid_b)
    assert p["status"] != "EXECUTED" and p["verdict"] != "CONFORMS"
    emit("B.result", balance=t.read(lambda: contract.get_org(args=[org_b]).call())["balance"],
         authorized=t.read(lambda: contract.is_action_authorized(args=[pid_b]).call()))

    # ---- C. lifecycle path: dormancy -> dissolution -> pro-rata refund
    org_c = t.create_org(contract, value=120, min_reserve=100, max_spend_bps=5000, grace=1)
    pid_c = t.propose_spend(contract, org_c, t.GOOD_URL, amount=60)
    p = settle_logged("C.spend", contract, pid_c)
    assert p["status"] == "EXECUTED"
    o = t.read(lambda: contract.get_org(args=[org_c]).call())
    assert o["status"] == "DORMANT" and o["balance"] == 60
    emit("C.dormant", status=o["status"], balance=o["balance"], dormant_since=o["dormant_since"])
    time.sleep(3)  # grace is 1 second
    send_logged("C.heartbeat", contract.heartbeat, [org_c])
    o = t.read(lambda: contract.get_org(args=[org_c]).call())
    assert o["status"] == "DISSOLVED" and o["refund_pool"] == 60
    emit("C.dissolved", status=o["status"], refund_pool=o["refund_pool"], refund_total=o["refund_total"])
    send_logged("C.claim_refund", contract.claim_refund, [org_c])
    o = t.read(lambda: contract.get_org(args=[org_c]).call())
    assert o["refund_pool"] == 0 and o["refund_total"] == 0
    emit("C.refunded", refund_pool=o["refund_pool"], refund_total=o["refund_total"])

    emit("done", address=address, org_count=t.read(lambda: contract.org_count(args=[]).call()),
         proposal_count=t.read(lambda: contract.proposal_count(args=[]).call()))
