from odoo import SUPERUSER_ID, api

from odoo.addons.cs_purse_pocket.models.wallet_sequences import rename_unnamed_records


def migrate(cr, version):
    """Number the wallet records of non-first companies that were left as 'New'."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    rename_unnamed_records(env)
