from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    family_link_as_patient_ids = fields.One2many(
        "patient.wallet.family.link",
        "patient_id",
        string="Familiares vinculados",
    )
    family_link_as_payer_ids = fields.One2many(
        "patient.wallet.family.link",
        "payer_id",
        string="Pacientes vinculados",
    )
    is_wallet_patient = fields.Boolean(
        string="Etiqueta paciente",
        compute="_compute_wallet_contact_flags",
    )
    is_wallet_family = fields.Boolean(
        string="Etiqueta familia",
        compute="_compute_wallet_contact_flags",
    )

    @api.depends("category_id.name")
    def _compute_wallet_contact_flags(self):
        for rec in self:
            tags = [name.lower() for name in rec.category_id.mapped("name")]
            rec.is_wallet_patient = any("paciente" in name for name in tags)
            rec.is_wallet_family = any("famil" in name for name in tags)
