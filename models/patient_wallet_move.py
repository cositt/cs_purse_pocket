import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PatientWalletMove(models.Model):
    _name = "patient.wallet.move"
    _description = "Patient Wallet Move"
    _order = "date desc, id desc"

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("New"), index=True)
    account_id = fields.Many2one("patient.wallet.account", string="Monedero", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one("res.company", related="account_id.company_id", store=True, index=True)
    currency_id = fields.Many2one("res.currency", related="account_id.currency_id", store=True)
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today, index=True)
    datetime = fields.Datetime(string="Fecha y hora", default=fields.Datetime.now, required=True, index=True)
    move_type = fields.Selection(
        [
            ("funding", "Recarga"),
            ("expense", "Consumo"),
            ("adjustment_in", "Ajuste de entrada"),
            ("adjustment_out", "Ajuste de salida"),
            ("statement_opening", "Apertura de liquidación"),
            ("statement_closing", "Cierre de liquidación"),
        ],
        string="Tipo de movimiento",
        required=True,
        index=True,
    )
    direction = fields.Selection([("in", "Entrada"), ("out", "Salida")], string="Dirección", required=True, index=True)
    amount = fields.Monetary(string="Importe", required=True, currency_field="currency_id")
    signed_amount = fields.Monetary(string="Importe firmado", compute="_compute_signed_amount", store=True, index=True, currency_field="currency_id")
    description = fields.Char(string="Descripción", required=True)
    category_id = fields.Many2one("patient.wallet.category", string="Categoría", index=True)
    origin_model = fields.Char(string="Modelo origen", required=True, index=True)
    origin_id = fields.Integer(string="ID origen", required=True, index=True)
    responsible_id = fields.Many2one("res.users", string="Responsable", required=True, default=lambda self: self.env.user, index=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("posted", "Publicado"), ("cancelled", "Cancelado")],
        string="Estado",
        default="posted",
        index=True,
    )
    account_move_id = fields.Many2one("account.move", string="Asiento contable", ondelete="restrict", index=True)
    reversal_move_id = fields.Many2one("patient.wallet.move", ondelete="restrict", index=True)
    reversed_by_move_id = fields.Many2one("patient.wallet.move", ondelete="restrict", index=True)
    hash = fields.Char(readonly=True, index=True, copy=False)

    _sql_constraints = [
        ("amount_positive", "check(amount > 0)", "Amount must be greater than zero."),
        (
            "origin_unique",
            "unique(origin_model, origin_id, account_id, move_type)",
            "There is already a move with the same origin for this account and move type.",
        ),
    ]

    @api.depends("amount", "direction")
    def _compute_signed_amount(self):
        for rec in self:
            rec.signed_amount = rec.amount if rec.direction == "in" else rec.amount * -1

    @api.constrains("move_type", "direction")
    def _check_move_direction(self):
        mapping = {
            "funding": "in",
            "expense": "out",
            "adjustment_in": "in",
            "adjustment_out": "out",
            "statement_opening": "in",
            "statement_closing": "out",
        }
        for rec in self:
            expected = mapping.get(rec.move_type)
            if expected and rec.direction != expected:
                raise ValidationError(_("Direction is inconsistent with move type."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name") in (False, "New", _("New")):
                vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.move") or _("New")
        records = super().create(vals_list)
        for rec in records:
            rec.hash = hashlib.sha256(f"{rec.account_id.id}|{rec.origin_model}|{rec.origin_id}|{rec.amount}|{rec.date}".encode()).hexdigest()
        return records

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "name" in fields_list and (not vals.get("name") or vals.get("name") in ("New", _("New"))):
            vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.move") or _("New")
        return vals

    def unlink(self):
        if any(rec.state == "posted" for rec in self):
            raise UserError(_("Posted wallet moves cannot be deleted."))
        return super().unlink()

    def action_reverse(self, reason):
        self.ensure_one()
        if not self.env.user.has_group("cs_purse_pocket.group_wallet_admin"):
            raise UserError(_("Solo el administrador de monederos puede revertir movimientos."))
        if self.state != "posted":
            raise UserError(_("Only posted moves can be reversed."))
        if self.reversed_by_move_id:
            raise UserError(_("Move is already reversed."))

        reverse_type = "adjustment_in" if self.direction == "out" else "adjustment_out"
        reverse_direction = "in" if self.direction == "out" else "out"

        reverse_move = self.account_id.create_move(
            move_type=reverse_type,
            amount=self.amount,
            direction=reverse_direction,
            description=_("Reversal of %s: %s") % (self.name, reason),
            origin_model=self._name,
            origin_id=self.id,
            category_id=self.category_id.id,
            responsible_id=self.env.user.id,
        )
        self.reversed_by_move_id = reverse_move.id
        reverse_move.reversal_move_id = self.id
        return reverse_move
