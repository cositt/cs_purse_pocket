from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PatientWalletAccount(models.Model):
    _name = "patient.wallet.account"
    _description = "Patient Wallet Account"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("New"), tracking=True)
    active = fields.Boolean(default=True, index=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company, index=True)
    center_id = fields.Many2one("res.partner", string="Centro", index=True)
    patient_id = fields.Many2one("res.partner", string="Paciente", required=True, index=True, tracking=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    allow_negative = fields.Boolean(string="Permitir saldo negativo", default=False)
    negative_limit = fields.Monetary(string="Límite negativo", default=0.0, currency_field="currency_id")
    move_ids = fields.One2many("patient.wallet.move", "account_id")
    balance = fields.Monetary(string="Saldo", compute="_compute_balance", store=True, currency_field="currency_id")
    total_recargas = fields.Monetary(
        string="Total recargas",
        compute="_compute_wallet_totals",
        currency_field="currency_id",
    )
    total_consumos = fields.Monetary(
        string="Total consumos",
        compute="_compute_wallet_totals",
        currency_field="currency_id",
    )
    last_move_date = fields.Date(compute="_compute_last_move_date", store=True, index=True)
    responsible_id = fields.Many2one("res.users", string="Responsable", default=lambda self: self.env.user, required=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("open", "Abierto"), ("blocked", "Bloqueado"), ("closed", "Cerrado")],
        string="Estado",
        default="open",
        index=True,
        tracking=True,
    )
    notes = fields.Text(string="Notas")

    _sql_constraints = [
        ("patient_company_unique", "unique(company_id, patient_id)", "Only one wallet per patient and company is allowed."),
    ]

    @api.depends("move_ids.signed_amount", "move_ids.state")
    def _compute_balance(self):
        for rec in self:
            posted_moves = rec.move_ids.filtered(lambda m: m.state == "posted")
            rec.balance = sum(posted_moves.mapped("signed_amount"))

    @api.depends("move_ids.state", "move_ids.move_type", "move_ids.amount", "move_ids.reversed_by_move_id")
    def _compute_wallet_totals(self):
        for rec in self:
            posted = rec.move_ids.filtered(lambda m: m.state == "posted")
            valid_fundings = posted.filtered(
                lambda m: m.move_type == "funding" and not m.reversed_by_move_id
            )
            valid_expenses = posted.filtered(
                lambda m: m.move_type == "expense" and not m.reversed_by_move_id
            )
            rec.total_recargas = sum(valid_fundings.mapped("amount"))
            rec.total_consumos = sum(valid_expenses.mapped("amount"))

    @api.depends("move_ids.date")
    def _compute_last_move_date(self):
        for rec in self:
            rec.last_move_date = max(rec.move_ids.mapped("date")) if rec.move_ids else False

    @api.constrains("allow_negative", "negative_limit")
    def _check_negative_policy(self):
        for rec in self:
            if not rec.allow_negative and rec.negative_limit != 0:
                raise ValidationError(_("Negative limit must be 0 when negative balance is disabled."))
            if rec.negative_limit < 0:
                raise ValidationError(_("Negative limit cannot be negative."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name") in (False, "New", _("New")):
                vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.account") or _("New")
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "name" in fields_list and (not vals.get("name") or vals.get("name") in ("New", _("New"))):
            vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.account") or _("New")
        return vals

    def _check_projected_balance(self, signed_amount):
        self.ensure_one()
        projected = self.balance + signed_amount
        if self.allow_negative:
            allowed_negative = -abs(self.negative_limit or 0.0)
            if projected < allowed_negative:
                raise UserError(
                    _(
                        "No se puede validar el movimiento.\n"
                        "Saldo actual: %(balance).2f\n"
                        "Saldo proyectado: %(projected).2f\n"
                        "Límite negativo permitido: %(limit).2f"
                    )
                    % {
                        "balance": self.balance,
                        "projected": projected,
                        "limit": allowed_negative,
                    }
                )
            return
        if projected < 0:
            raise UserError(
                _(
                    "No hay saldo suficiente para esta operación.\n"
                    "Saldo actual: %(balance).2f\n"
                    "Saldo proyectado: %(projected).2f"
                )
                % {
                    "balance": self.balance,
                    "projected": projected,
                }
            )

    def create_move(self, *, move_type, amount, direction, description, origin_model, origin_id, category_id=False, date=False, responsible_id=False, account_move_id=False):
        self.ensure_one()
        if self.state != "open":
            raise UserError(_("Wallet account must be in open state."))
        if amount <= 0:
            raise ValidationError(_("Amount must be greater than zero."))
        if not origin_model or not origin_id:
            raise ValidationError(_("Origin model and origin id are mandatory."))

        signed_amount = amount if direction == "in" else amount * -1
        self._check_projected_balance(signed_amount)

        return self.env["patient.wallet.move"].create({
            "account_id": self.id,
            "date": date or fields.Date.context_today(self),
            "move_type": move_type,
            "direction": direction,
            "amount": amount,
            "description": description,
            "origin_model": origin_model,
            "origin_id": origin_id,
            "category_id": category_id or False,
            "responsible_id": responsible_id or self.env.user.id,
            "state": "posted",
            "account_move_id": account_move_id or False,
        })
