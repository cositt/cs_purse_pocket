from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PatientWalletFamilyLink(models.Model):
    _name = "patient.wallet.family.link"
    _description = "Vínculo familiar paciente-pagador"
    _inherit = ["cs.family.relationship.mixin"]
    _order = "patient_id, payer_id"

    active = fields.Boolean(string="Activo", default=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company, index=True)
    patient_id = fields.Many2one(
        "res.partner",
        string="Paciente",
        required=True,
        index=True,
        domain="[('category_id.name', 'ilike', 'paciente')]",
    )
    payer_id = fields.Many2one(
        "res.partner",
        string="Familiar pagador",
        required=True,
        index=True,
        domain="[('category_id.name', 'ilike', 'famil')]",
    )
    relationship = fields.Char(
        string="Parentesco",
        help="Parentesco del familiar respecto al paciente (p. ej. Padre, Madre, Tutor).",
    )
    relationship_reciprocal = fields.Char(
        string="Parentesco (desde familiar)",
        compute="_compute_relationship_reciprocal",
        help="Parentesco del paciente respecto al familiar (p. ej. Hijo/a).",
    )
    notification_channel = fields.Selection(
        [("email", "Solo email"), ("whatsapp", "Solo WhatsApp"), ("both", "Email y WhatsApp")],
        string="Canal de notificación",
        default="email",
        required=True,
    )
    notes = fields.Text(string="Notas")

    _sql_constraints = [
        (
            "patient_payer_company_unique",
            "unique(company_id, patient_id, payer_id)",
            "Ese vínculo familiar ya existe para la compañía.",
        ),
    ]

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, _("%s -> %s") % (rec.patient_id.name, rec.payer_id.name)))
        return result

    @api.depends("relationship")
    def _compute_relationship_reciprocal(self):
        for rec in self:
            rec.relationship_reciprocal = rec.reciprocal_family_relationship(rec.relationship)

    @api.constrains("patient_id", "payer_id")
    def _check_patient_payer_not_same(self):
        for rec in self:
            if rec.patient_id and rec.payer_id and rec.patient_id == rec.payer_id:
                raise ValidationError(_("Paciente y pagador no pueden ser el mismo contacto."))
