from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWalletCollectionMethod(TransactionCase):
    """Domiciliación (SEPA) como forma de pago y forma de cobro habitual por monedero."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.patient = cls.env["res.partner"].create({"name": "Paciente Cobro Test"})
        cls.account = cls.env["patient.wallet.account"].create({
            "patient_id": cls.patient.id,
            "collection_method": "sepa",
        })

    def _funding_vals(self, **extra):
        vals = {
            "patient_id": self.patient.id,
            "payer_id": self.patient.id,
            "account_id": self.account.id,
            "amount": 100.0,
        }
        vals.update(extra)
        return vals

    def test_sepa_is_a_funding_payment_method(self):
        methods = dict(self.env["patient.wallet.funding"]._fields["payment_method"].selection)
        self.assertIn("sepa", methods)

    def test_funding_by_direct_debit_confirms(self):
        funding = self.env["patient.wallet.funding"].create(self._funding_vals(payment_method="sepa"))
        funding.action_confirm()
        self.assertEqual(funding.state, "confirmed")
        self.assertEqual(self.account.balance, 100.0)

    def test_funding_defaults_to_account_collection_method(self):
        funding = self.env["patient.wallet.funding"].create(self._funding_vals())
        self.assertEqual(funding.payment_method, "sepa")

    def test_explicit_payment_method_wins(self):
        funding = self.env["patient.wallet.funding"].create(self._funding_vals(payment_method="cash"))
        self.assertEqual(funding.payment_method, "cash")

    def test_onchange_account_proposes_collection_method(self):
        with Form(self.env["patient.wallet.funding"]) as form:
            form.patient_id = self.patient
            self.assertEqual(form.account_id, self.account)
            self.assertEqual(form.payment_method, "sepa")
            form.amount = 50.0

    def test_account_without_collection_method_keeps_transfer_default(self):
        other = self.env["res.partner"].create({"name": "Paciente Sin Forma"})
        account = self.env["patient.wallet.account"].create({"patient_id": other.id})
        funding = self.env["patient.wallet.funding"].create({
            "patient_id": other.id,
            "payer_id": other.id,
            "account_id": account.id,
            "amount": 10.0,
        })
        self.assertEqual(funding.payment_method, "transfer")
