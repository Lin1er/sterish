"""The buyer side of x402 `exact` on Stellar, in Python (STE-43).

A line-by-line port of `ExactStellarScheme.createPaymentPayload` from `@x402/stellar`
plus the v2 envelope `@x402/core` wraps around it — the same client
`demo/x402-buyer/buy.js` uses, and whose payments the facilitator settled in STE-19
and STE-42. The API image is Python only, so the demo buyer cannot shell out to Node.

What the payer signs is a Soroban authorization entry, not a transaction envelope
(developers.stellar.org, "Built on Stellar x402 Facilitator", "What the client
signs"): a `transfer(from, to, amount)` on the USDC SAC with an expiration ledger.
The facilitator rebuilds the transaction around it with its own source account and
pays the fee, which is why the buyer holds no XLM of its own for the payment.

The facilitator's verify (read from `@x402/stellar/exact/facilitator`) checks, and
this module is written to satisfy exactly:

* one `invokeHostFunction` op calling `transfer` on `requirements.asset` with
  3 args, `to == payTo`, `amount == requirements.amount`;
* a successful simulation with exactly one transfer event matching the above;
* every auth entry has address credentials, no sub-invocations, and an expiration
  no later than `latest + ceil(maxTimeoutSeconds / ledger seconds) + 2`;
* the payer has signed and no other signature is pending.

Legacy `ADDRESS` credentials are requested (`use_upgraded_auth=False`). The
facilitator accepts `ADDRESS_V2` too, but `ADDRESS` is what the proven JS client
produced, so the payload the facilitator sees is the one it has already settled.
"""

from __future__ import annotations

import math
import re
from typing import Any

import httpx
from stellar_sdk import Account, Address, Keypair, SorobanServer, TransactionBuilder, scval
from stellar_sdk import xdr as stellar_xdr
from stellar_sdk.auth import authorize_entry

X402_VERSION = 2

# @x402/stellar constants.
NETWORK_PASSPHRASES = {
    "stellar:testnet": "Test SDF Network ; September 2015",
    "stellar:pubnet": "Public Global Stellar Network ; September 2015",
}
DEFAULT_LEDGER_SECONDS = 5
LEDGER_SAMPLE_SIZE = 20
# The JS AssembledTransaction builds from this throwaway source when no public key is
# given; the facilitator replaces the source when it settles.
NULL_ACCOUNT = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
TX_TIMEOUT_SECONDS = 300

_DESTINATION_RE = re.compile(r"^(?:[GC][ABCD][A-Z2-7]{54}|M[ABCD][A-Z2-7]{67})$")
_ASSET_RE = re.compile(r"^C[ABCD][A-Z2-7]{54}$")


class PaymentBuildError(Exception):
    """The payment could not be built. `reason` is safe to show a user."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def select_requirements(payment_required: dict[str, Any], network: str) -> dict[str, Any]:
    """The first `exact` offer on our network, validated as the JS client validates it."""
    if payment_required.get("x402Version") != X402_VERSION:
        raise PaymentBuildError(f"unsupported x402Version {payment_required.get('x402Version')!r}")
    for offer in payment_required.get("accepts") or []:
        if offer.get("scheme") == "exact" and offer.get("network") == network:
            amount = offer.get("amount")
            if not isinstance(amount, str) or not amount.isdigit() or int(amount) <= 0:
                raise PaymentBuildError(f"invalid amount {amount!r}: must be a positive integer")
            if not _DESTINATION_RE.match(str(offer.get("payTo") or "")):
                raise PaymentBuildError(f"invalid payTo {offer.get('payTo')!r}")
            if not _ASSET_RE.match(str(offer.get("asset") or "")):
                raise PaymentBuildError(f"invalid asset {offer.get('asset')!r}")
            if not (offer.get("extra") or {}).get("areFeesSponsored"):
                raise PaymentBuildError("exact scheme requires areFeesSponsored to be true")
            return offer
    raise PaymentBuildError(f"no exact offer for network {network}")


def estimated_ledger_seconds(horizon_url: str, *, client: httpx.Client | None = None) -> int:
    """Average close time over the last 20 ledgers, rounded up; 5 on any failure.

    Same estimate the facilitator uses for its expiration ceiling, so the two agree.
    """
    http = client or httpx.Client(timeout=10)
    try:
        response = http.get(
            f"{horizon_url.rstrip('/')}/ledgers",
            params={"limit": LEDGER_SAMPLE_SIZE, "order": "desc"},
        )
        response.raise_for_status()
        records = response.json()["_embedded"]["records"]
        if len(records) < 2:
            return DEFAULT_LEDGER_SECONDS
        from datetime import datetime

        newest = datetime.fromisoformat(records[0]["closed_at"].replace("Z", "+00:00"))
        oldest = datetime.fromisoformat(records[-1]["closed_at"].replace("Z", "+00:00"))
        return max(1, math.ceil((newest - oldest).total_seconds() / (len(records) - 1)))
    except Exception:  # noqa: BLE001 - an estimate, never a reason to fail a payment
        return DEFAULT_LEDGER_SECONDS
    finally:
        if client is None:
            http.close()


def _check_simulation(sim: Any, stage: str) -> None:
    if sim is None:
        raise PaymentBuildError(f"{stage}: simulation returned nothing")
    if getattr(sim, "error", None):
        raise PaymentBuildError(f"{stage}: simulation failed: {sim.error}")
    if getattr(sim, "restore_preamble", None):
        raise PaymentBuildError(f"{stage}: ledger entries need a restore before paying")
    if not getattr(sim, "results", None):
        raise PaymentBuildError(f"{stage}: simulation returned no result")


def _address_credentials(entry: stellar_xdr.SorobanAuthorizationEntry) -> Any:
    creds = entry.credentials
    kind = creds.type
    if kind == stellar_xdr.SorobanCredentialsType.SOROBAN_CREDENTIALS_ADDRESS:
        return creds.address
    v2 = getattr(stellar_xdr.SorobanCredentialsType, "SOROBAN_CREDENTIALS_ADDRESS_V2", None)
    if v2 is not None and kind == v2:
        return creds.address_v2
    return None


def signature_status(
    entries: list[stellar_xdr.SorobanAuthorizationEntry],
) -> tuple[set[str], set[str]]:
    """(already signed, pending) addresses, the way the facilitator reads them."""
    signed: set[str] = set()
    pending: set[str] = set()
    for entry in entries:
        creds = _address_credentials(entry)
        if creds is None:
            continue
        address = Address.from_xdr_sc_address(creds.address).address
        if creds.signature.type == stellar_xdr.SCValType.SCV_VOID:
            pending.add(address)
        else:
            signed.add(address)
    return signed, pending


def build_payment(
    payment_required: dict[str, Any],
    signer: Keypair,
    *,
    rpc_url: str,
    horizon_url: str,
    network: str = "stellar:testnet",
    server: SorobanServer | None = None,
    ledger_seconds: int | None = None,
) -> dict[str, Any]:
    """Build and sign the `X-PAYMENT` payload for a PAYMENT-REQUIRED challenge.

    Returns the full v2 envelope: `{x402Version, payload: {transaction}, resource,
    accepted}`. Raises PaymentBuildError with a displayable reason.
    """
    passphrase = NETWORK_PASSPHRASES.get(network)
    if passphrase is None:
        raise PaymentBuildError(f"unknown network {network}")
    requirements = select_requirements(payment_required, network)
    payer = signer.public_key

    rpc = server or SorobanServer(rpc_url)
    try:
        current_ledger = rpc.get_latest_ledger().sequence
    except Exception as exc:  # noqa: BLE001
        raise PaymentBuildError(f"RPC unreachable: {exc}") from exc
    seconds = ledger_seconds or estimated_ledger_seconds(horizon_url)
    max_ledger = current_ledger + math.ceil(int(requirements["maxTimeoutSeconds"]) / seconds)

    tx = (
        TransactionBuilder(Account(NULL_ACCOUNT, 0), passphrase, base_fee=100)
        .append_invoke_contract_function_op(
            requirements["asset"],
            "transfer",
            [
                scval.to_address(payer),
                scval.to_address(requirements["payTo"]),
                scval.to_int128(int(requirements["amount"])),
            ],
        )
        .set_timeout(TX_TIMEOUT_SECONDS)
        .build()
    )

    try:
        sim = rpc.simulate_transaction(tx, use_upgraded_auth=False)
    except Exception as exc:  # noqa: BLE001
        raise PaymentBuildError(f"simulation unreachable: {exc}") from exc
    _check_simulation(sim, "first simulation")

    entries = [
        stellar_xdr.SorobanAuthorizationEntry.from_xdr(raw) for raw in (sim.results[0].auth or [])
    ]
    _, pending = signature_status(entries)
    if pending != {payer}:
        # Mirrors the JS client: exactly one signer, and it is us. Anything else means
        # this transfer needs someone else's consent, which a payment must never need.
        raise PaymentBuildError(
            f"expected to sign with [{payer}], "
            f"but the transfer needs [{', '.join(sorted(pending))}]"
        )

    signed_entries = []
    for entry in entries:
        creds = _address_credentials(entry)
        if creds is not None and Address.from_xdr_sc_address(creds.address).address == payer:
            entry = authorize_entry(entry, signer, max_ledger, passphrase)
        signed_entries.append(entry)

    # Existing auth entries are preferred over the simulation's when assembling, so
    # the signed ones survive; the second simulation recomputes the footprint and the
    # resource fee now that the signature verification is part of the work.
    tx.transaction.operations[0].auth = signed_entries
    try:
        assembled = rpc.prepare_transaction(tx, sim)
        second = rpc.simulate_transaction(assembled, use_upgraded_auth=False)
    except Exception as exc:  # noqa: BLE001
        raise PaymentBuildError(f"re-simulation failed: {exc}") from exc
    _check_simulation(second, "second simulation")
    final = rpc.prepare_transaction(assembled, second)

    signed, still_pending = signature_status(final.transaction.operations[0].auth)
    if still_pending or payer not in signed:
        raise PaymentBuildError(
            f"unexpected signer(s) required: [{', '.join(sorted(still_pending))}]"
        )

    envelope: dict[str, Any] = {
        "x402Version": X402_VERSION,
        "payload": {"transaction": final.to_xdr()},
        "accepted": requirements,
    }
    if payment_required.get("resource") is not None:
        envelope["resource"] = payment_required["resource"]
    return envelope
