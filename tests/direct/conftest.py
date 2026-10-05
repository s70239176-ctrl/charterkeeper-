"""Shared helpers for CharterKeeper Direct Mode tests."""
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

CONTRACT = "contracts/charterkeeper.py"
MODULE = "_contract_charterkeeper"
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAY = 86400
ZERO = "0x" + "00" * 20

CHARTER = (
    "Mission: fund and maintain open-source climate-data tooling. Never fund weapons, "
    "surveillance, or anything unrelated to open climate data."
)
CRITERIA = [
    "A public release was published",
    "The release has documentation",
    "The code is under an open-source licence",
]
PLAN = "Fund maintainers of existing open climate-data libraries with small grants."
GOOD_URL = "https://example.org/reports/release-1"
GOOD_QUOTE = "Release 1.0 published under the MIT licence with full docs"
GOOD_PAGE = f"Weekly report. {GOOD_QUOTE}. Thanks to all contributors."


def iso(offset_seconds: int = 0) -> str:
    return (T0 + timedelta(seconds=offset_seconds)).isoformat().replace("+00:00", "Z")


def verdict_json(verdict="CONFORMS", met_mask=0b111, injection=False, quote=GOOD_QUOTE, **extra):
    body = {"verdict": verdict, "met_mask": met_mask, "injection": injection, "quote": quote}
    body.update(extra)
    return json.dumps(body)


def hexof(addr) -> str:
    """Canonical lower-case hex for bytes / Address / hex-string."""
    if isinstance(addr, (bytes, bytearray)):
        return "0x" + bytes(addr).hex()
    if hasattr(addr, "as_hex"):
        return addr.as_hex.lower()
    return str(addr).lower()


DEFAULTS = dict(
    name="Open Climate Trust",
    charter=CHARTER,
    criteria=CRITERIA,
    plan=PLAN,
    min_reserve=100,
    max_spend_bps=2000,
    spend_cooldown=DAY,
    grace=7 * DAY,
    min_criteria=2,
    proposal_bond=10,
    proposal_window=14 * DAY,
    successor=ZERO,
)


def set_clock(vm, seconds: int) -> None:
    """
    Pin the transaction time the contract sees.

    gltest 0.29.2's vm.warp() updates sender/value but not gl.message_raw["datetime"],
    which is what a contract must read for the transaction timestamp. Update both.
    """
    vm.warp(iso(seconds))
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = iso(seconds)


def contract_module():
    return sys.modules[MODULE]


@pytest.fixture
def world(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    """A fresh deployed contract, named actors, a pinned clock and a transfer recorder."""
    direct_vm.strict_mocks = True
    for addr in (direct_alice, direct_bob, direct_charlie):
        direct_vm.deal(addr, 10**9)

    transfers = []

    def hook(vm, request):
        if "PostMessage" in request:
            msg = request["PostMessage"]
            transfers.append({"to": hexof(msg["address"]), "value": int(msg["value"]), "on": msg["on"]})
            return {"ok": None}
        return None

    direct_vm._gl_call_hook = hook
    contract = direct_deploy(CONTRACT)
    set_clock(direct_vm, 0)

    class World:
        vm = direct_vm
        c = contract
        alice = direct_alice
        bob = direct_bob
        charlie = direct_charlie
        sent = transfers
        deposited = 0

        # ---------------------------------------------------------- actions
        @classmethod
        def make_org(cls, sender=None, value=1000, **overrides):
            params = dict(DEFAULTS)
            params.update(overrides)
            direct_vm.sender = sender or direct_alice
            direct_vm.value = value
            org_id = contract.create_org(
                params["name"], params["charter"], params["criteria"], params["plan"],
                params["min_reserve"], params["max_spend_bps"], params["spend_cooldown"],
                params["grace"], params["min_criteria"], params["proposal_bond"],
                params["proposal_window"], params["successor"],
            )
            direct_vm.value = 0
            cls.deposited += value
            return org_id

        @classmethod
        def fund(cls, org_id, value, sender=None):
            direct_vm.sender = sender or direct_bob
            direct_vm.value = value
            contract.fund(org_id)
            direct_vm.value = 0
            cls.deposited += value

        @classmethod
        def spend_proposal(cls, org_id, amount=100, mask=0b111, url=GOOD_URL, recipient=None,
                           sender=None, bond=10, purpose="Ship release 1.0"):
            direct_vm.sender = sender or direct_bob
            direct_vm.value = bond
            pid = contract.propose_spend(org_id, purpose, url, recipient or direct_charlie, amount, mask)
            direct_vm.value = 0
            cls.deposited += bond
            return pid

        @classmethod
        def adapt_proposal(cls, org_id, new_plan="Also fund documentation of open climate datasets.",
                           sender=None, bond=10):
            direct_vm.sender = sender or direct_bob
            direct_vm.value = bond
            pid = contract.propose_adaptation(org_id, new_plan)
            direct_vm.value = 0
            cls.deposited += bond
            return pid

        @staticmethod
        def reset_mocks():
            strict, direct_vm.strict_mocks = direct_vm.strict_mocks, False
            direct_vm.clear_mocks()
            direct_vm.strict_mocks = strict

        @classmethod
        def mock_world(cls, page=GOOD_PAGE, status=200, llm=None):
            cls.reset_mocks()
            direct_vm.mock_web(r"example\.org", {"method": "GET", "status": status, "body": page})
            direct_vm.mock_llm(r"CHARTERKEEPER_JUDGE", llm if llm is not None else verdict_json())

        @classmethod
        def resolve(cls, pid, page=GOOD_PAGE, status=200, llm=None, sender=None):
            cls.mock_world(page=page, status=status, llm=llm)
            direct_vm.sender = sender or direct_charlie
            return contract.resolve(pid)

        @classmethod
        def resolve_adapt(cls, pid, llm=None, sender=None):
            cls.reset_mocks()
            direct_vm.mock_llm(r"CHARTERKEEPER_JUDGE", llm if llm is not None else verdict_json(met_mask=0, quote=""))
            direct_vm.sender = sender or direct_charlie
            return contract.resolve(pid)

        @staticmethod
        def at(seconds: int):
            set_clock(direct_vm, seconds)

        # ------------------------------------------------------------ reads
        @classmethod
        def paid_to(cls, who) -> int:
            return sum(t["value"] for t in transfers if t["to"] == hexof(who))

        @classmethod
        def total_paid(cls) -> int:
            return sum(t["value"] for t in transfers)

        @classmethod
        def held(cls) -> int:
            """Value the contract should still hold: org treasuries + refund pools + live bonds."""
            total = 0
            for oid in range(1, int(contract.org_count()) + 1):
                o = contract.get_org(oid)
                total += o["balance"] + o["refund_pool"]
            for pid in range(1, int(contract.proposal_count()) + 1):
                total += contract.get_proposal(pid)["bond"]
            return total

    return World
