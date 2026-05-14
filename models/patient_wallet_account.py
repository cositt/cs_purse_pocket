from datetime import timedelta

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
    low_balance_threshold = fields.Monetary(
        string="Umbral alerta saldo bajo",
        default=50.0,
        currency_field="currency_id",
        help="Se enviará una alerta a la familia cuando el saldo baje de este importe.",
    )
    low_balance_alert_enabled = fields.Boolean(
        string="Activar alerta saldo bajo",
        default=True,
    )
    last_low_balance_alert = fields.Date(
        string="Última alerta saldo bajo",
        readonly=True,
    )
    auto_statement_enabled = fields.Boolean(
        string="Extracto semanal automático",
        default=True,
        help="Enviar automáticamente un extracto semanal a los familiares vinculados.",
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

    # ------------------------------------------------------------------
    # Cron methods
    # ------------------------------------------------------------------

    @api.model
    def _send_low_balance_alerts(self):
        """Cron diario: notifica a familias cuando el saldo baja del umbral."""
        today = fields.Date.context_today(self)
        cooldown_cutoff = today - timedelta(days=7)
        accounts = self.search([
            ("state", "=", "open"),
            ("low_balance_alert_enabled", "=", True),
        ]).filtered(
            lambda a: a.balance < a.low_balance_threshold
            and (not a.last_low_balance_alert or a.last_low_balance_alert < cooldown_cutoff)
        )
        for account in accounts:
            account._notify_families_low_balance()
            account.last_low_balance_alert = today

    @api.model
    def _send_weekly_statements(self):
        """Cron semanal: genera extracto de la semana pasada y lo envía a familias."""
        today = fields.Date.context_today(self)
        date_from = today - timedelta(days=7)
        date_to = today - timedelta(days=1)
        accounts = self.search([
            ("state", "=", "open"),
            ("auto_statement_enabled", "=", True),
        ])
        for account in accounts:
            has_moves = self.env["patient.wallet.move"].search_count([
                ("account_id", "=", account.id),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("state", "=", "posted"),
            ])
            if not has_moves:
                continue
            existing = self.env["patient.wallet.statement"].search([
                ("account_id", "=", account.id),
                ("date_from", "=", date_from),
                ("date_to", "=", date_to),
            ], limit=1)
            stmt = existing or self.env["patient.wallet.statement"].create({
                "patient_id": account.patient_id.id,
                "account_id": account.id,
                "date_from": date_from,
                "date_to": date_to,
            })
            if stmt.state == "draft":
                stmt.action_generate()
            account._notify_families_statement(stmt)

    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------

    def _get_active_family_links(self):
        self.ensure_one()
        return self.env["patient.wallet.family.link"].search([
            ("patient_id", "=", self.patient_id.id),
            ("company_id", "=", self.company_id.id),
            ("active", "=", True),
        ])

    def _notify_families_low_balance(self):
        self.ensure_one()
        links = self._get_active_family_links()
        if not links:
            return
        email_tmpl = self.env.ref("cs_purse_pocket.mail_template_low_balance", raise_if_not_found=False)
        wa_tmpl = self.env.ref("cs_purse_pocket.whatsapp_template_low_balance", raise_if_not_found=False)
        for link in links:
            payer = link.payer_id
            if link.notification_channel in ("email", "both") and payer.email and email_tmpl:
                email_tmpl.with_context(payer_name=payer.name).send_mail(
                    self.id,
                    email_values={"email_to": payer.email, "email_cc": False},
                    force_send=True,
                )
            if link.notification_channel in ("whatsapp", "both") and payer.mobile and wa_tmpl:
                self._send_whatsapp_via_template(
                    payer=payer,
                    template=wa_tmpl,
                    free_text_json={
                        "free_text_1": payer.name,
                        "free_text_2": self.patient_id.name,
                        "free_text_3": "%.2f" % self.balance,
                    },
                )

    def _notify_families_statement(self, stmt):
        self.ensure_one()
        links = self._get_active_family_links()
        if not links:
            return
        email_tmpl = self.env.ref("cs_purse_pocket.mail_template_weekly_statement", raise_if_not_found=False)
        wa_tmpl = self.env.ref("cs_purse_pocket.whatsapp_template_weekly_statement", raise_if_not_found=False)
        for link in links:
            payer = link.payer_id
            if link.notification_channel in ("email", "both") and payer.email and email_tmpl:
                email_tmpl.with_context(
                    payer_name=payer.name,
                    stmt_date_from=str(stmt.date_from),
                    stmt_date_to=str(stmt.date_to),
                ).send_mail(
                    self.id,
                    email_values={"email_to": payer.email, "email_cc": False},
                    force_send=True,
                )
            if link.notification_channel in ("whatsapp", "both") and payer.mobile and wa_tmpl:
                self._send_whatsapp_via_template(
                    payer=payer,
                    template=wa_tmpl,
                    free_text_json={
                        "free_text_1": payer.name,
                        "free_text_2": self.patient_id.name,
                        "free_text_3": str(stmt.date_from),
                        "free_text_4": str(stmt.date_to),
                        "free_text_5": "%.2f" % stmt.closing_balance,
                    },
                )

    def _send_whatsapp_via_template(self, payer, template, free_text_json):
        """Crea y encola un mensaje WhatsApp para un familiar pagador."""
        self.ensure_one()
        WaMessage = self.env.get("whatsapp.message")
        if WaMessage is None or not payer.mobile:
            return
        notice = _("Notificación WhatsApp de monedero enviada a %(name)s (%(mobile)s)", name=payer.name, mobile=payer.mobile)
        mail_msg = payer._message_log(body=notice)
        WaMessage.create({
            "mail_message_id": mail_msg.id,
            "mobile_number": payer.mobile,
            "wa_template_id": template.id,
            "wa_account_id": template.wa_account_id.id if template.wa_account_id else False,
            "free_text_json": free_text_json,
        })._send()
