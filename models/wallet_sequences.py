"""Wallet reference sequences.

They used to be created for the first company only, so every wallet record of
any other company kept the reference 'New'. The sequences are now shared by all
companies and existing unnamed records are numbered by the 19.0.2.1.0 migration.
"""
import logging

_logger = logging.getLogger(__name__)

WALLET_SEQUENCE_MODELS = (
    "patient.wallet.account",
    "patient.wallet.move",
    "patient.wallet.funding",
    "patient.wallet.expense.allocation",
    "patient.wallet.statement",
)
UNNAMED = ("New", "Nuevo", "/", "")


def rename_unnamed_records(env) -> dict:
    """Give a sequence number to every wallet record still called 'New'. Returns {model: count}."""
    renamed = {}
    Sequence = env["ir.sequence"].sudo()
    for model in WALLET_SEQUENCE_MODELS:
        records = env[model].sudo().with_context(active_test=False).search(
            [("name", "in", list(UNNAMED))], order="id")
        for record in records:
            record.name = Sequence.next_by_code(model) or record.name
        if records:
            renamed[model] = len(records)
            _logger.info("cs_purse_pocket: numbered %s unnamed %s records", len(records), model)
    return renamed
