import re

from odoo import api, fields, models


class PatientWalletCategory(models.Model):
    _name = "patient.wallet.category"
    _description = "Patient Wallet Category"
    _order = "code"

    name = fields.Char(string="Nombre", required=True)
    code = fields.Char(string="Código", index=True, copy=False)
    company_id = fields.Many2one("res.company", string="Compañía", index=True)
    category_type = fields.Selection(
        [
            ("funding", "Recarga"),
            ("expense", "Consumo"),
            ("adjustment", "Ajuste"),
            ("both", "Ambos"),
        ],
        string="Tipo",
        required=True,
        default="both",
        index=True,
    )
    active = fields.Boolean(string="Activo", default=True, index=True)
    description = fields.Text(string="Descripción")

    _sql_constraints = [
        ("code_company_unique", "unique(company_id, code)", "Category code must be unique per company."),
    ]

    @api.model
    def _build_code_base(self, name):
        base = (name or "").strip().upper()
        base = re.sub(r"[^A-Z0-9]+", "_", base).strip("_")
        return base or "CAT"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                continue
            company_id = vals.get("company_id") or self.env.company.id
            base = self._build_code_base(vals.get("name"))
            candidate = base
            suffix = 1
            while self.search_count([("company_id", "=", company_id), ("code", "=", candidate)]):
                suffix += 1
                candidate = f"{base}_{suffix}"
            vals["code"] = candidate
        return super().create(vals_list)
