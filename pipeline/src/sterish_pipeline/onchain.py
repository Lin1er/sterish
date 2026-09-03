"""Interact with deployed Soroban contracts via stellar-sdk."""

import logging

from stellar_sdk import Keypair, Server, scval
from stellar_sdk.contract import Contract

from sterish_pipeline.config import PipelineConfig
from sterish_pipeline.models import FinalVerdict

logger = logging.getLogger(__name__)

_VERDIT_MAP: dict[FinalVerdict, int] = {
    FinalVerdict.SAFE: 1,
    FinalVerdict.DANGEROUS: 2,
    FinalVerdict.WARNING: 3,
}


def submit_verdict_to_chain(
    contract_id: str,
    skill_id: str,
    verdict: FinalVerdict,
    score: int,
    evidence_hash: str,
    secret_key: str,
    public_key: str,
    config: PipelineConfig | None = None,
) -> str:
    """Submit an audit verdict to the deployed SkillRegistry contract.

    Returns the transaction hash.
    """
    cfg = config or PipelineConfig()
    kp = Keypair.from_secret(secret_key)
    assert kp.public_key == public_key, "Secret key does not match public key"
    server = Server(cfg.rpc_url)
    account = server.load_account(public_key)

    contract = Contract(contract_id)
    evidence_bytes = bytes.fromhex(evidence_hash)

    tx = server.prepare_transaction(
        contract.call(
            "submit_verdict",
            scval.to_string(skill_id),
            scval.to_uint32(_VERDIT_MAP[verdict]),
            scval.to_uint32(score),
            scval.to_bytes(evidence_bytes),
        ),
        source_account=account,
        network_passphrase=cfg.network_passphrase,
    ).build()

    tx.sign(kp)
    response = server.submit_transaction(tx)
    return response.hash


def query_skill_from_chain(
    contract_id: str,
    skill_id: str,
    public_key: str,
    config: PipelineConfig | None = None,
) -> dict:
    """Query a skill entry from the deployed SkillRegistry contract.

    Returns a dict with the parsed skill entry data.
    """
    cfg = config or PipelineConfig()
    server = Server(cfg.rpc_url)
    account = server.load_account(public_key)

    contract = Contract(contract_id)
    tx = server.prepare_transaction(
        contract.call(
            "query_skill",
            scval.to_string(skill_id),
        ),
        source_account=account,
        network_passphrase=cfg.network_passphrase,
    ).build()

    response = server.simulate_transaction(tx)
    result_xdr = ""
    if response.results:
        result_xdr = response.results[0].xdr
    return {"xdr": result_xdr}
