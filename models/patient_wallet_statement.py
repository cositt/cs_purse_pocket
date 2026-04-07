from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PatientWalletStatement(models.Model):
    _name = "patient.wallet.statement"
    _description = "Patient Wallet Statement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_to desc, id desc"

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("New"), index=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company, index=True)
    center_id = fields.Many2one("res.partner", string="Centro", index=True)
    account_id = fields.Many2one("patient.wallet.account", string="Monedero", required=True, index=True, readonly=True)
    patient_id = fields.Many2one("res.partner", string="Paciente", required=True, index=True)
    date_from = fields.Date(string="Desde", required=True, index=True)
    date_to = fields.Date(string="Hasta", required=True, index=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    opening_balance = fields.Monetary(string="Saldo inicial", currency_field="currency_id", readonly=True)
    funding_total = fields.Monetary(string="Total recargas", currency_field="currency_id", readonly=True)
    expense_total = fields.Monetary(string="Total consumos", currency_field="currency_id", readonly=True)
    adjustment_total = fields.Monetary(string="Total ajustes", currency_field="currency_id", readonly=True)
    closing_balance = fields.Monetary(string="Saldo final", currency_field="currency_id", readonly=True)
    line_move_ids = fields.Many2many("patient.wallet.move")
    state = fields.Selection(
        [("draft", "Borrador"), ("confirmed", "Confirmada"), ("locked", "Bloqueada")],
        string="Estado",
        default="draft",
        index=True,
    )
    generated_by = fields.Many2one("res.users", string="Generado por", required=True, default=lambda self: self.env.user)
    generated_at = fields.Datetime(string="Generado el", readonly=True)
    pdf_attachment_id = fields.Many2one("ir.attachment", string="Documento")
    liquidation_move_id = fields.Many2one("patient.wallet.move", string="Movimiento de liquidación", readonly=True)
    liquidated_at = fields.Datetime(string="Liquidado el", readonly=True)
    notes = fields.Text(string="Notas")

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_("Date from cannot be greater than date to."))

    @api.constrains("patient_id", "account_id")
    def _check_patient_account(self):
        for rec in self:
            if rec.patient_id and rec.account_id and rec.account_id.patient_id != rec.patient_id:
                raise ValidationError(_("El monedero no corresponde al paciente seleccionado."))

    def _find_open_wallet_for_patient(self, patient, company):
        if not patient:
            return self.env["patient.wallet.account"]
        return self.env["patient.wallet.account"].search(
            [
                ("patient_id", "=", patient.id),
                ("company_id", "=", company.id),
                ("state", "=", "open"),
            ],
            limit=1,
        )

    @api.onchange("patient_id", "company_id")
    def _onchange_patient_wallet(self):
        for rec in self:
            rec.account_id = False
            if not rec.patient_id:
                continue
            rec.account_id = rec._find_open_wallet_for_patient(rec.patient_id, rec.company_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name") in (False, "New", _("New")):
                vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.statement") or _("New")
            if not vals.get("account_id") and vals.get("patient_id"):
                patient = self.env["res.partner"].browse(vals["patient_id"])
                company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
                account = self._find_open_wallet_for_patient(patient, company)
                if not account:
                    raise ValidationError(_("El paciente seleccionado no tiene un monedero abierto."))
                vals["account_id"] = account.id
            if not vals.get("account_id"):
                raise ValidationError(_("Debes seleccionar un paciente con monedero abierto."))
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "name" in fields_list and (not vals.get("name") or vals.get("name") in ("New", _("New"))):
            vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.statement") or _("New")
        return vals

    def action_generate(self):
        for rec in self:
            if not rec.account_id:
                rec.account_id = rec._find_open_wallet_for_patient(rec.patient_id, rec.company_id)
            if not rec.account_id:
                raise ValidationError(_("El paciente seleccionado no tiene un monedero abierto."))
            domain = [
                ("date", ">=", rec.date_from),
                ("date", "<=", rec.date_to),
                ("state", "=", "posted"),
            ]
            domain.append(("account_id", "=", rec.account_id.id))

            moves = self.env["patient.wallet.move"].search(domain)
            rec.line_move_ids = [(6, 0, moves.ids)]

            base_domain = [("date", "<", rec.date_from), ("state", "=", "posted")]
            base_domain.append(("account_id", "=", rec.account_id.id))

            opening_moves = self.env["patient.wallet.move"].search(base_domain)
            rec.opening_balance = sum(opening_moves.mapped("signed_amount"))
            rec.funding_total = sum(moves.filtered(lambda m: m.move_type == "funding").mapped("amount"))
            rec.expense_total = sum(moves.filtered(lambda m: m.move_type == "expense").mapped("amount"))
            adjustment_signed = sum(moves.filtered(lambda m: "adjustment" in m.move_type).mapped("signed_amount"))
            rec.adjustment_total = adjustment_signed
            rec.closing_balance = rec.opening_balance + sum(moves.mapped("signed_amount"))
            rec.generated_at = fields.Datetime.now()
            rec.state = "confirmed"

    def action_lock(self):
        self.write({"state": "locked"})

    def action_liquidate(self):
        for rec in self:
            if rec.state != "confirmed":
                raise ValidationError(_("Solo se puede liquidar una liquidación confirmada."))
            if not rec.account_id:
                raise ValidationError(_("No existe monedero para liquidar."))
            if rec.account_id.state != "open" and abs(rec.account_id.balance) > 0.0001:
                raise ValidationError(_("El monedero debe estar abierto para poder liquidarlo."))

            current_balance = rec.account_id.balance
            move = self.env["patient.wallet.move"]
            if current_balance > 0.0001:
                move = rec.account_id.create_move(
                    move_type="statement_closing",
                    amount=current_balance,
                    direction="out",
                    description=_("Liquidación final: cierre de saldo a cero"),
                    origin_model=rec._name,
                    origin_id=rec.id,
                    date=rec.date_to,
                    responsible_id=self.env.user.id,
                )
            elif current_balance < -0.0001:
                move = rec.account_id.create_move(
                    move_type="adjustment_in",
                    amount=abs(current_balance),
                    direction="in",
                    description=_("Liquidación final: regularización de deuda"),
                    origin_model=rec._name,
                    origin_id=rec.id,
                    date=rec.date_to,
                    responsible_id=self.env.user.id,
                )

            if move:
                rec.liquidation_move_id = move.id
            rec.liquidated_at = fields.Datetime.now()
            rec.action_generate()
            rec.state = "locked"
            rec.account_id.state = "closed"
