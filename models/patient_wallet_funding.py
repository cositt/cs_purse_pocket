from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PatientWalletFunding(models.Model):
    _name = "patient.wallet.funding"
    _description = "Patient Wallet Funding"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("New"), index=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company, index=True)
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today, index=True)
    patient_id = fields.Many2one(
        "res.partner",
        string="Paciente",
        required=True,
        index=True,
        domain="[('category_id.name', 'ilike', 'paciente')]",
    )
    allowed_payer_ids = fields.Many2many(
        "res.partner",
        string="Pagadores permitidos",
        compute="_compute_allowed_payer_ids",
    )
    payer_id = fields.Many2one(
        "res.partner",
        string="Familiar pagador",
        required=True,
        index=True,
        domain="[('id', 'in', allowed_payer_ids)]",
    )
    account_id = fields.Many2one(
        "patient.wallet.account",
        string="Monedero",
        required=True,
        index=True,
        domain="[('patient_id', '=', patient_id), ('company_id', '=', company_id), ('state', '=', 'open')]",
    )
    amount = fields.Monetary(string="Importe", required=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    payment_method = fields.Selection(
        [("cash", "Efectivo"), ("transfer", "Transferencia"), ("card", "Tarjeta"), ("other", "Otro")],
        string="Método de pago",
        required=True,
        default="transfer",
    )
    external_reference = fields.Char(string="Referencia externa", index=True)
    responsible_id = fields.Many2one("res.users", string="Responsable", required=True, default=lambda self: self.env.user)
    state = fields.Selection(
        [("draft", "Borrador"), ("confirmed", "Confirmada"), ("cancelled", "Cancelada")],
        string="Estado",
        default="draft",
        index=True,
    )
    wallet_move_id = fields.Many2one("patient.wallet.move", string="Movimiento de monedero", ondelete="restrict")
    account_move_id = fields.Many2one("account.move", string="Asiento contable", ondelete="restrict")
    notes = fields.Text(string="Notas")

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Funding amount must be greater than zero."))

    @api.constrains("account_id", "patient_id")
    def _check_patient_account(self):
        for rec in self:
            if rec.account_id and rec.account_id.patient_id != rec.patient_id:
                raise ValidationError(_("Wallet account does not belong to selected patient."))
            if rec.account_id and rec.account_id.state != "open":
                raise ValidationError(_("Wallet account must be open to receive fundings."))
            if rec.account_id and rec.account_id.company_id != rec.company_id:
                raise ValidationError(_("Wallet account company must match funding company."))
            if rec.patient_id and rec.payer_id:
                if rec.payer_id == rec.patient_id:
                    continue
                valid_link = self.env["patient.wallet.family.link"].search_count(
                    [
                        ("patient_id", "=", rec.patient_id.id),
                        ("payer_id", "=", rec.payer_id.id),
                        ("active", "=", True),
                    ]
                )
                if not valid_link:
                    raise ValidationError(_("El pagador no está vinculado al paciente en el vínculo familiar."))

    @api.depends("patient_id", "company_id")
    def _compute_allowed_payer_ids(self):
        link_model = self.env["patient.wallet.family.link"]
        for rec in self:
            if not rec.patient_id:
                rec.allowed_payer_ids = False
                continue
            links = link_model.search(
                [
                    ("patient_id", "=", rec.patient_id.id),
                    ("company_id", "=", rec.company_id.id),
                    ("active", "=", True),
                ]
            )
            rec.allowed_payer_ids = rec.patient_id | links.mapped("payer_id")

    @api.onchange("patient_id", "company_id")
    def _onchange_patient_wallet(self):
        for rec in self:
            rec.account_id = False
            rec.payer_id = False
            if not rec.patient_id:
                continue
            account = self.env["patient.wallet.account"].search(
                [
                    ("patient_id", "=", rec.patient_id.id),
                    ("company_id", "=", rec.company_id.id),
                    ("state", "=", "open"),
                ],
                limit=1,
            )
            rec.account_id = account
            rec.payer_id = rec.patient_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name") in (False, "New", _("New")):
                vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.funding") or _("New")
            if vals.get("patient_id") and not vals.get("account_id"):
                account = self.env["patient.wallet.account"].search(
                    [
                        ("patient_id", "=", vals["patient_id"]),
                        ("company_id", "=", vals.get("company_id", self.env.company.id)),
                        ("state", "=", "open"),
                    ],
                    limit=1,
                )
                if account:
                    vals["account_id"] = account.id
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "name" in fields_list and (not vals.get("name") or vals.get("name") in ("New", _("New"))):
            vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.funding") or _("New")
        return vals

    def action_confirm(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            move = rec.account_id.create_move(
                move_type="funding",
                amount=rec.amount,
                direction="in",
                description=_("Funding: %s") % rec.name,
                origin_model=rec._name,
                origin_id=rec.id,
                date=rec.date,
                responsible_id=rec.responsible_id.id,
                account_move_id=rec.account_move_id.id if rec.account_move_id else False,
            )
            rec.wallet_move_id = move.id
            rec.state = "confirmed"

    def action_cancel(self):
        if not self.env.user.has_group("cs_purse_pocket.group_wallet_admin"):
            raise ValidationError(_("Solo el administrador de monederos puede cancelar recargas."))
        for rec in self.filtered(lambda r: r.state == "confirmed" and r.wallet_move_id):
            rec.wallet_move_id.action_reverse(_("Funding cancellation"))
            rec.state = "cancelled"
