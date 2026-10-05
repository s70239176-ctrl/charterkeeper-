"""
OPTIONAL, TEST-ONLY host workaround for Windows. Not needed on Linux/macOS.

genlayer-test 0.29.2 (the newest release at time of writing) fails on Windows
inside its Direct Mode loader, BEFORE any contract code runs:

    PermissionError: [WinError 32] ... being used by another process
    gltest/direct/loader.py, _inject_message_to_fd0: os.unlink(path)

The loader deletes a temp file while it is still open as stdin (dup2'd onto fd 0),
which Windows forbids. This plugin replaces ONLY that one loader function with a
copy whose single difference is that the unlink is deferred until the session ends.
It does not patch file deletion globally and it does not touch the contract.

    PYTHONPATH=scripts python -m pytest tests/direct -p windows_direct_plugin
"""
import os
import sys

_deferred = []


def _inject_message_to_fd0(vm):
    import tempfile

    from genlayer.py import calldata
    from genlayer.py.types import Address

    sender_addr = vm.sender
    if isinstance(sender_addr, bytes):
        sender_addr = Address(sender_addr)
    contract_addr = vm._contract_address
    if isinstance(contract_addr, bytes):
        contract_addr = Address(contract_addr)
    origin_addr = vm.origin
    if isinstance(origin_addr, bytes):
        origin_addr = Address(origin_addr)

    message_data = {
        "contract_address": contract_addr,
        "sender_address": sender_addr,
        "origin_address": origin_addr,
        "stack": [],
        "value": vm._value,
        "datetime": vm._datetime,
        "is_init": False,
        "chain_id": vm._chain_id,
        "entry_kind": 0,
        "entry_data": b"",
        "entry_stage_data": None,
    }
    encoded = calldata.encode(message_data)

    fd, path = tempfile.mkstemp()
    try:
        os.write(fd, encoded)
        os.lseek(fd, 0, os.SEEK_SET)
        vm._original_stdin_fd = os.dup(0)
        os.dup2(fd, 0)
    finally:
        os.close(fd)
        try:
            os.unlink(path)
        except PermissionError:
            _deferred.append(path)  # the only change versus upstream


def pytest_configure(config):
    if sys.platform != "win32":
        return
    import gltest.direct.loader as loader

    loader._inject_message_to_fd0 = _inject_message_to_fd0


def pytest_unconfigure(config):
    for path in _deferred:
        try:
            os.unlink(path)
        except OSError:
            pass
