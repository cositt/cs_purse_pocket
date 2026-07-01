from odoo import _, api, models
from odoo.exceptions import ValidationError
import unicodedata

# Parentesco del familiar respecto al paciente -> vista desde el familiar.
_RECIPROCAL_FAMILY_RELATIONSHIPS = {
    "padre": "Hijo/a",
    "madre": "Hijo/a",
    "hijo": "Padre/Madre",
    "hija": "Padre/Madre",
    "abuelo": "Nieto/a",
    "abuela": "Nieto/a",
    "nieto": "Abuelo/a",
    "nieta": "Abuelo/a",
    "tio": "Sobrino/a",
    "tia": "Sobrino/a",
    "sobrino": "Tío/a",
    "sobrina": "Tío/a",
    "tutor": "Tutelado/a",
    "tutora": "Tutelado/a",
    "tutelado": "Tutor/a",
    "tutelada": "Tutor/a",
    "esposo": "Esposa",
    "esposa": "Esposo",
    "marido": "Esposa",
    "mujer": "Esposo",
    "conyuge": "Cónyuge",
    "pareja": "Pareja",
    "hermano": "Hermano/a",
    "hermana": "Hermano/a",
    "primo": "Primo/a",
    "prima": "Primo/a",
    "suegro": "Yerno/nuera",
    "suegra": "Yerno/nuera",
    "yerno": "Suegro/a",
    "nuera": "Suegro/a",
    "cunado": "Cuñado/a",
    "cunada": "Cuñado/a",
}


class CsFamilyRelationshipMixin(models.AbstractModel):
    _name = "cs.family.relationship.mixin"
    _description = "Validación compartida de parentesco familiar"

    @api.model
    def normalize_family_relationship(self, value):
        if not value:
            return value
        return " ".join(str(value).strip().split())

    @api.model
    def _family_relationship_lookup_key(self, value):
        text = unicodedata.normalize("NFD", (value or "").lower())
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        return " ".join(text.split())

    @api.model
    def reciprocal_family_relationship(self, value):
        """Devuelve el parentesco del paciente visto desde el familiar."""
        normalized = self.normalize_family_relationship(value)
        if not normalized:
            return normalized
        reciprocal = _RECIPROCAL_FAMILY_RELATIONSHIPS.get(
            self._family_relationship_lookup_key(normalized)
        )
        return reciprocal or normalized

    @api.constrains("relationship")
    def _check_family_relationship(self):
        for rec in self:
            if "relationship" not in rec._fields:
                continue
            rel = rec.relationship
            if not rel:
                continue
            normalized = rec.normalize_family_relationship(rel)
            if len(normalized) < 2:
                raise ValidationError(_("El parentesco debe tener al menos 2 caracteres."))
            if len(normalized) > 64:
                raise ValidationError(_("El parentesco no puede superar 64 caracteres."))
