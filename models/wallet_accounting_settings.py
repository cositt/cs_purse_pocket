from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    wallet_liability_account_id = fields.Many2one(
        "account.account",
        string="Cuenta pasivo monedero",
        domain="[('deprecated', '=', False), ('company_ids', 'in', [id])]",
    )
    wallet_bank_account_id = fields.Many2one(
        "account.account",
        string="Cuenta banco/caja monedero",
        domain="[('deprecated', '=', False), ('company_ids', 'in', [id])]",
    )
    wallet_journal_id = fields.Many2one(
        "account.journal",
        string="Diario monedero",
        domain="[('company_id', '=', id)]",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    wallet_liability_account_id = fields.Many2one(
        "account.account",
        string="Cuenta pasivo monedero",
        related="company_id.wallet_liability_account_id",
        readonly=False,
    )
    wallet_bank_account_id = fields.Many2one(
        "account.account",
        string="Cuenta banco/caja monedero",
        related="company_id.wallet_bank_account_id",
        readonly=False,
    )
    wallet_journal_id = fields.Many2one(
        "account.journal",
        string="Diario monedero",
        related="company_id.wallet_journal_id",
        readonly=False,
    )
