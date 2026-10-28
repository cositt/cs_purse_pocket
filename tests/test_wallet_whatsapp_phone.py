from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestWalletWhatsappPhone(TransactionCase):
    """Odoo 19 eliminó res.partner.mobile: los avisos WhatsApp usan el teléfono."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.patient = Partner.create({"name": "Paciente WhatsApp Test"})
        cls.payer = Partner.create({"name": "Familiar WhatsApp Test", "phone": "+34600111222"})
        cls.payer_sin_telefono = Partner.create({"name": "Familiar Sin Telefono"})
        cls.account = cls.env["patient.wallet.account"].create({"patient_id": cls.patient.id})
        cls.wa_template = cls.env.ref("cs_purse_pocket.whatsapp_template_low_balance")

    def _link(self, payer, channel="whatsapp"):
        return self.env["patient.wallet.family.link"].create({
            "patient_id": self.patient.id,
            "payer_id": payer.id,
            "notification_channel": channel,
        })

    def test_aviso_saldo_bajo_usa_telefono_del_familiar(self):
        self._link(self.payer)
        with patch.object(type(self.account), "_send_whatsapp_via_template") as send:
            self.account._notify_families_low_balance()
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["payer"], self.payer)

    def test_aviso_saldo_bajo_sin_telefono_no_envia(self):
        self._link(self.payer_sin_telefono, channel="both")
        with patch.object(type(self.account), "_send_whatsapp_via_template") as send:
            self.account._notify_families_low_balance()
        send.assert_not_called()

    def test_mensaje_whatsapp_lleva_el_telefono(self):
        WaMessage = self.env["whatsapp.message"]
        with patch.object(type(WaMessage), "_send") as wa_send:
            self.account._send_whatsapp_via_template(
                payer=self.payer,
                template=self.wa_template,
                free_text_json={"free_text_1": self.payer.name},
            )
        wa_send.assert_called_once()
        message = WaMessage.search([("mobile_number", "=", "+34600111222")], limit=1)
        self.assertTrue(message)

    def test_mensaje_whatsapp_sin_telefono_no_se_crea(self):
        WaMessage = self.env["whatsapp.message"]
        antes = WaMessage.search_count([])
        self.account._send_whatsapp_via_template(
            payer=self.payer_sin_telefono,
            template=self.wa_template,
            free_text_json={},
        )
        self.assertEqual(WaMessage.search_count([]), antes)
