<p align="center">
  <img src="static/description/icon.png" alt="CS Patient Wallet" width="180" />
</p>

# CS Patient Wallet (`cs_purse_pocket`)

Módulo de Odoo 19 para gestionar fondos de terceros en pacientes (residencias/centros sanitarios) con trazabilidad completa: recargas, consumos, saldo, liquidaciones y vínculos familiares.

## Qué resuelve

Este módulo separa el dinero custodiado para pacientes del flujo de ventas/facturación del centro.

- Mantiene un monedero por paciente.
- Registra movimientos inmutables de entrada/salida.
- Permite recargas por paciente o familiar vinculado.
- Permite imputar gastos individuales o repartidos.
- Permite liquidar y cerrar cuenta con ajuste final a saldo cero.

## Funcionalidad principal

- **Cuentas de monedero**
  - Un monedero por paciente y compañía.
  - Política configurable de saldo negativo y límite.
- **Recargas**
  - Estados: borrador, confirmada, cancelada.
  - Al cancelar, se revierte el movimiento y no computa en `Total recargas`.
- **Imputaciones de gasto**
  - Reparto automático y edición manual.
  - Rebalanceo automático del remanente al editar importes.
- **Movimientos**
  - Libro mayor con hash y reversión controlada por rol.
- **Liquidaciones**
  - Generación por paciente.
  - Botón `Liquidar`: deja saldo en cero y cierra monedero.
- **Vínculos familiares**
  - Gestión desde menú dedicado y desde ficha de contacto.
  - Soporte de parentesco y estado activo.

## Requisitos

- Odoo 19
- Módulos base: `mail`, `contacts`, `account`, `web`

## Instalación

1. Copia el módulo en tu ruta de addons custom (ej. `custom-addons/cs_purse_pocket`).
2. Asegúrate de tener esa ruta en `addons_path`.
3. Reinicia Odoo.
4. Actualiza lista de apps e instala **CS Patient Wallet**.

## Flujo recomendado de uso

1. **Contactos**
   - Etiqueta contactos como `Paciente` o `Familia`.
   - Configura vínculos en la pestaña **Vínculos monedero**.
2. **Cuentas**
   - Crea monedero por paciente.
3. **Recargas**
   - Registra ingreso y confirma.
4. **Imputaciones**
   - Registra consumo total y reparto por paciente.
5. **Liquidaciones**
   - Genera liquidación y usa `Liquidar` para cierre final.

## Seguridad y roles

- `Wallet Admin`: administración completa, cancelaciones y reversiones.
- `Wallet Operator`: operación diaria.
- `Wallet Readonly`: consulta.

## Estructura técnica (resumen)

- `models/`: lógica de negocio y validaciones ORM.
- `views/`: formularios, listas, menús y herencias de contactos.
- `security/`: grupos, reglas y accesos por modelo.
- `wizards/`: asistentes de imputación/liquidación.
- `data/sequence.xml`: seriación de referencias.

## Notas

- El módulo está orientado a operación en español.
- Las etiquetas de contacto usadas en filtros son:
  - `Paciente` (o texto que contenga `paciente`)
  - `Familia` (o texto que contenga `famil`)
