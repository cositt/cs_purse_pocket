from odoo import fields, models


class ExpenseAllocationWizard(models.TransientModel):
    _name = "patient.wallet.expense.allocation.wizard"
    _description = "Expense Allocation Wizard"

    description = fields.Char(required=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    category_id = fields.Many2one("patient.wallet.category")
    total_amount = fields.Monetary(required=True)
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)

    def action_open_allocation(self):
        self.ensure_one()
        allocation = self.env["patient.wallet.expense.allocation"].create({
            "description": self.description,
            "date": self.date,
            "category_id": self.category_id.id,
            "total_amount": self.total_amount,
            "responsible_id": self.env.user.id,
            "origin_model": self._name,
            "origin_id": self.id,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "patient.wallet.expense.allocation",
            "res_id": allocation.id,
            "view_mode": "form",
            "target": "current",
        }
