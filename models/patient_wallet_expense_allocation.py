from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PatientWalletExpenseAllocation(models.Model):
    _name = "patient.wallet.expense.allocation"
    _description = "Patient Wallet Expense Allocation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Referencia", required=True, copy=False, default=lambda self: _("New"), index=True)
    company_id = fields.Many2one("res.company", string="Compañía", required=True, default=lambda self: self.env.company, index=True)
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today, index=True)
    description = fields.Char(string="Descripción", required=True)
    category_id = fields.Many2one("patient.wallet.category", index=True)
    total_amount = fields.Monetary(string="Importe total", required=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    allocation_method = fields.Selection(
        [("manual", "Manual"), ("equal", "Igualitario"), ("percentage", "Por porcentaje")],
        string="Método de reparto",
        required=True,
        default="manual",
    )
    line_ids = fields.One2many("patient.wallet.expense.allocation.line", "allocation_id")
    state = fields.Selection(
        [("draft", "Borrador"), ("validated", "Validada"), ("cancelled", "Cancelada")],
        string="Estado",
        default="draft",
        index=True,
    )
    responsible_id = fields.Many2one("res.users", string="Responsable", required=True, default=lambda self: self.env.user)
    origin_model = fields.Char(required=True, default="manual.expense")
    origin_id = fields.Integer(required=True, default=0)
    notes = fields.Text(string="Notas")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name") in (False, "New", _("New")):
                vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.expense.allocation") or _("New")
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "name" in fields_list and (not vals.get("name") or vals.get("name") in ("New", _("New"))):
            vals["name"] = self.env["ir.sequence"].next_by_code("patient.wallet.expense.allocation") or _("New")
        return vals

    @api.constrains("total_amount")
    def _check_total_amount(self):
        for rec in self:
            if rec.total_amount <= 0:
                raise ValidationError(_("Total amount must be greater than zero."))

    def _validate_distribution(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_("At least one allocation line is required."))
            allocated_total = sum(rec.line_ids.mapped("amount"))
            if abs(allocated_total - rec.total_amount) > 0.01:
                raise ValidationError(_("Allocated amount must match total amount."))

    @api.onchange("line_ids", "total_amount", "allocation_method")
    def _onchange_auto_distribution(self):
        """Reparte automáticamente por cantidad:
        - 1 paciente: 100% del importe total
        - N pacientes: reparto equitativo por defecto
        Se puede editar manualmente después.
        """
        for rec in self:
            lines = rec.line_ids.filtered("patient_id")
            if not lines or rec.total_amount <= 0:
                continue
            if rec.allocation_method == "percentage":
                continue
            amounts = [line.amount or 0.0 for line in lines]
            has_empty_amounts = any(amount <= 0 for amount in amounts)
            all_equal = all(abs(amount - amounts[0]) <= 0.0001 for amount in amounts)
            # Si el usuario ya está editando importes manualmente (no vacíos y no iguales),
            # no volver a repartir automáticamente para no pisar su trabajo.
            if not has_empty_amounts and not all_equal:
                continue
            # Si hay pacientes repetidos, la constraint SQL se encargará al guardar.
            total = rec.total_amount
            count = len(lines)
            if count == 1:
                lines[0].amount = total
                lines[0].percentage = 100.0
                continue
            even = round(total / count, 2)
            assigned = 0.0
            for idx, line in enumerate(lines, start=1):
                if idx < count:
                    line.amount = even
                    assigned += even
                else:
                    line.amount = round(total - assigned, 2)
                line.percentage = round((line.amount / total) * 100, 4) if total else 0.0

    def action_validate(self):
        self._validate_distribution()
        for rec in self.filtered(lambda r: r.state == "draft"):
            for line in rec.line_ids:
                if line.amount <= 0:
                    raise ValidationError(_("Line amount must be greater than zero."))
                line.balance_before = line.account_id.balance
                move = line.account_id.create_move(
                    move_type="expense",
                    amount=line.amount,
                    direction="out",
                    description=rec.description,
                    origin_model=rec._name,
                    origin_id=rec.id,
                    category_id=rec.category_id.id,
                    date=rec.date,
                    responsible_id=rec.responsible_id.id,
                )
                line.wallet_move_id = move.id
                line.status = "posted"
                line.balance_after = line.account_id.balance
            rec.state = "validated"

    def action_cancel(self):
        if not self.env.user.has_group("cs_purse_pocket.group_wallet_admin"):
            raise ValidationError(_("Solo el administrador de monederos puede cancelar imputaciones."))
        for rec in self.filtered(lambda r: r.state == "validated"):
            for line in rec.line_ids.filtered("wallet_move_id"):
                line.wallet_move_id.action_reverse(_("Expense allocation cancellation"))
                line.status = "rejected"
                line.rejection_reason = _("Allocation cancelled")
            rec.state = "cancelled"


class PatientWalletExpenseAllocationLine(models.Model):
    _name = "patient.wallet.expense.allocation.line"
    _description = "Patient Wallet Expense Allocation Line"

    allocation_id = fields.Many2one("patient.wallet.expense.allocation", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", related="allocation_id.company_id", store=True, index=True)
    patient_id = fields.Many2one(
        "res.partner",
        string="Paciente",
        required=True,
        index=True,
        domain="[('category_id.name', 'ilike', 'paciente')]",
    )
    account_id = fields.Many2one(
        "patient.wallet.account",
        string="Monedero",
        required=True,
        index=True,
        domain="[('patient_id', '=', patient_id), ('company_id', '=', company_id), ('state', '=', 'open')]",
    )
    amount = fields.Monetary(string="Importe", required=True)
    percentage = fields.Float(string="Porcentaje", digits=(16, 4))
    currency_id = fields.Many2one("res.currency", related="allocation_id.currency_id", store=True)
    wallet_move_id = fields.Many2one("patient.wallet.move", string="Movimiento", ondelete="restrict")
    balance_before = fields.Monetary(string="Saldo antes", currency_field="currency_id", readonly=True)
    balance_after = fields.Monetary(string="Saldo después", currency_field="currency_id", readonly=True)
    status = fields.Selection(
        [("pending", "Pendiente"), ("posted", "Publicado"), ("rejected", "Rechazado")],
        string="Estado",
        default="pending",
        index=True,
    )
    rejection_reason = fields.Char(string="Motivo de rechazo")

    _sql_constraints = [
        ("allocation_patient_unique", "unique(allocation_id, patient_id)", "Patient cannot be repeated in the same allocation."),
        ("amount_positive", "check(amount > 0)", "Amount must be greater than zero."),
    ]

    @api.constrains("account_id", "patient_id")
    def _check_patient_account(self):
        for rec in self:
            if rec.account_id and rec.patient_id and rec.account_id.patient_id != rec.patient_id:
                raise UserError(_("Wallet account does not belong to selected patient."))

    @api.onchange("patient_id", "company_id")
    def _onchange_patient_wallet(self):
        for rec in self:
            rec.account_id = False
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

    @api.onchange("company_id", "allocation_id")
    def _onchange_patient_domain(self):
        for rec in self:
            domain = [("category_id.name", "ilike", "paciente")]
            if rec.patient_id and not rec.patient_id.filtered_domain(domain):
                rec.patient_id = False
                rec.account_id = False
            return {"domain": {"patient_id": domain}}

    @api.onchange("account_id")
    def _onchange_account_patient(self):
        for rec in self:
            if rec.account_id:
                rec.patient_id = rec.account_id.patient_id

    @api.onchange("amount")
    def _onchange_amount_rebalance_remaining(self):
        """Si el usuario edita una línea, el resto se ajusta al importe restante.
        - 2 pacientes: editar uno recalcula el otro al remanente.
        - N pacientes: el remanente se reparte equitativamente entre los demás.
        """
        for rec in self:
            allocation = rec.allocation_id
            if not allocation or allocation.total_amount <= 0:
                continue
            if allocation.allocation_method == "percentage":
                continue
            lines = allocation.line_ids.filtered("patient_id")
            if len(lines) <= 1:
                continue
            siblings = lines - rec
            if not siblings:
                continue
            remaining = allocation.total_amount - (rec.amount or 0.0)
            count = len(siblings)
            even = round(remaining / count, 2)
            assigned = 0.0
            for idx, line in enumerate(siblings, start=1):
                if idx < count:
                    line.amount = even
                    assigned += even
                else:
                    line.amount = round(remaining - assigned, 2)
            total = allocation.total_amount
            for line in lines:
                line.percentage = round(((line.amount or 0.0) / total) * 100, 4) if total else 0.0
