from odoo.tests import TransactionCase, tagged

from ..models.wallet_sequences import WALLET_SEQUENCE_MODELS, rename_unnamed_records


@tagged("post_install", "-at_install")
class TestWalletSequences(TransactionCase):
    """Wallet references must be numbered in every company, not only in the first one."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_company = cls.env["res.company"].create({"name": "Segunda Empresa Monedero"})
        cls.env.user.company_ids |= cls.other_company
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=[cls.other_company.id]))
        cls.patient = cls.env["res.partner"].create({"name": "Paciente Segunda Empresa"})
        cls.wallet = cls.env["patient.wallet.account"].create({
            "patient_id": cls.patient.id, "company_id": cls.other_company.id,
        })

    def test_sequences_are_shared_by_all_companies(self):
        for model in WALLET_SEQUENCE_MODELS:
            seq = self.env["ir.sequence"].sudo().search([("code", "=", model)])
            self.assertTrue(seq, model)
            self.assertFalse(seq.company_id, model)

    def test_funding_and_move_get_reference_in_other_company(self):
        funding = self.env["patient.wallet.funding"].create({
            "company_id": self.other_company.id,
            "patient_id": self.patient.id,
            "payer_id": self.patient.id,
            "account_id": self.wallet.id,
            "amount": 10.0,
        })
        funding.action_confirm()
        self.assertTrue(self.wallet.name.startswith("WAL/"))
        self.assertTrue(funding.name.startswith("FND/"))
        self.assertTrue(funding.wallet_move_id.name.startswith("MVE/"))

    def test_rename_unnamed_records(self):
        funding = self.env["patient.wallet.funding"].create({
            "company_id": self.other_company.id,
            "patient_id": self.patient.id,
            "payer_id": self.patient.id,
            "account_id": self.wallet.id,
            "amount": 10.0,
        })
        self.env.cr.execute("UPDATE patient_wallet_funding SET name = 'New' WHERE id = %s", [funding.id])
        funding.invalidate_recordset(["name"])
        renamed = rename_unnamed_records(self.env)
        self.assertEqual(renamed.get("patient.wallet.funding"), 1)
        self.assertTrue(funding.name.startswith("FND/"))
