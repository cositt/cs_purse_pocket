from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StatementGenerateWizard(models.TransientModel):
    _name = "patient.wallet.statement.generate.wizard"
    _description = "Statement Generate Wizard"

    patient_id = fields.Many2one("res.partner", string="Paciente", required=True)
    account_id = fields.Many2one("patient.wallet.account", string="Monedero", readonly=True)
    date_from = fields.Date(string="Desde", required=True)
    date_to = fields.Date(string="Hasta", required=True)

    @api.onchange("patient_id")
    def _onchange_patient_wallet(self):
        for rec in self:
            rec.account_id = False
            if not rec.patient_id:
                continue
            rec.account_id = self.env["patient.wallet.account"].search(
                [
                    ("patient_id", "=", rec.patient_id.id),
                    ("company_id", "=", self.env.company.id),
                    ("state", "=", "open"),
                ],
                limit=1,
            )

    def action_generate_statement(self):
        self.ensure_one()
        if not self.account_id and self.patient_id:
            self._onchange_patient_wallet()
        if not self.account_id:
            raise ValidationError(_("El paciente seleccionado no tiene un monedero abierto."))
        statement = self.env["patient.wallet.statement"].create({
            "patient_id": self.patient_id.id,
            "account_id": self.account_id.id,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "generated_by": self.env.user.id,
        })
        statement.action_generate()
        return {
            "type": "ir.actions.act_window",
            "res_model": "patient.wallet.statement",
            "res_id": statement.id,
            "view_mode": "form",
            "target": "current",
        }
