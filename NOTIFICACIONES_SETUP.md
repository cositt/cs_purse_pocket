# Guía de configuración — Notificaciones de monedero

Cubre la configuración completa de alertas de saldo bajo y extractos semanales
por **email** y/o **WhatsApp** para los familiares de los residentes.

---

## 1. Email — configuración mínima

El email funciona desde el primer Upgrade sin pasos adicionales, siempre que
Odoo tenga configurado un servidor de correo saliente.

**Verificar servidor de correo:**
Ajustes → Técnico → Servidores de correo saliente → debe haber al menos uno activo.

**Plantillas disponibles** (Ajustes → Técnico → Email → Plantillas de correo electrónico):
- `Monedero: Alerta saldo bajo`
- `Monedero: Extracto semanal`

Puedes editarlas libremente desde la UI sin tocar código.

---

## 2. WhatsApp — configuración paso a paso

### 2.1 Requisitos previos (fuera de Odoo)

Necesitas una cuenta **Meta WhatsApp Business** con:
- Número de teléfono verificado (puede ser el del centro)
- Token de acceso permanente de la Meta API
- Las plantillas de mensaje **aprobadas** por Meta (ver sección 2.4)

> En desarrollo puedes trabajar sin cuenta Meta: los mensajes quedarán en
> estado *En cola* y no saldrán, pero la lógica funciona correctamente.

### 2.2 Instalar el módulo WhatsApp en Odoo

1. Ajustes → Aplicaciones → buscar `WhatsApp`
2. Instalar **WhatsApp** (módulo Enterprise)

### 2.3 Conectar la cuenta Meta

1. Ajustes → WhatsApp → **Cuentas de WhatsApp** → Nueva
2. Rellenar:
   - **Nombre**: p. ej. `Equilibrium WhatsApp`
   - **Número de teléfono**: el número verificado en Meta (con prefijo +34...)
   - **Token de acceso**: el token permanente de Meta Business
   - **ID del número de teléfono**: visible en el panel de Meta → Configuración del número
   - **ID de cuenta de empresa**: visible en Meta Business Suite → Configuración

### 2.4 Aprobar las plantillas en Meta

Las plantillas creadas automáticamente por el módulo están en estado **Borrador**.
Para enviar mensajes business-initiated, Meta exige que estén aprobadas.

**Pasos:**
1. Ir a **WhatsApp → Plantillas de mensajes**
2. Abrir `Alerta Saldo Bajo Monedero`
3. Asignarle la cuenta creada en 2.3 (campo **Cuenta**)
4. Revisar el cuerpo del mensaje (puedes modificarlo):
   ```
   Hola {{1}}, el saldo del monedero de {{2}} ha bajado a {{3}} €.
   Por favor, realice una recarga para garantizar la continuidad de los servicios.
   ```
   - `{{1}}` → nombre del familiar
   - `{{2}}` → nombre del residente
   - `{{3}}` → saldo actual en €
5. Clic en **Enviar para aprobación** → Meta tarda entre minutos y 24 h
6. Repetir para `Extracto Semanal Monedero`:
   ```
   Hola {{1}}, extracto semanal de {{2}} ({{3}} al {{4}}): saldo actual {{5}} €.
   Puede consultar el detalle en el portal del centro.
   ```
   - `{{1}}` nombre familiar, `{{2}}` residente, `{{3}}` fecha inicio,
     `{{4}}` fecha fin, `{{5}}` saldo final

> Una vez aprobadas, el estado cambia a **Aprobado** y los mensajes empiezan
> a enviarse automáticamente.

---

## 3. Configurar el canal por familiar

Cada vínculo familiar tiene ahora el campo **Canal de notificación**:

| Valor | Comportamiento |
|-------|---------------|
| Solo email | Solo se envía email (requiere que `payer_id.email` esté relleno) |
| Solo WhatsApp | Solo se envía WA (requiere que `payer_id.mobile` esté relleno) |
| Email y WhatsApp | Se envían ambos |

**Dónde configurarlo:**
Monedero → Vínculos familiares → abrir el vínculo → campo **Canal de notificación**

> Si el familiar no tiene `mobile` y el canal es WhatsApp, el mensaje se
> omite silenciosamente (no hay error).

---

## 4. Configurar umbrales por monedero

En cada **Monedero** (Monedero → Monederos → abrir registro) → pestaña
**Alertas y notificaciones**:

| Campo | Descripción | Valor por defecto |
|-------|-------------|-------------------|
| Activar alerta saldo bajo | Habilita/deshabilita la alerta para este monedero | Sí |
| Umbral alerta saldo bajo | Importe en € por debajo del cual se dispara la alerta | 50,00 € |
| Última alerta saldo bajo | Fecha del último envío (solo lectura, para diagnóstico) | — |
| Extracto semanal automático | Habilita el extracto semanal para este monedero | Sí |

---

## 5. Tareas programadas (crons)

Los crons se crean automáticamente al instalar/actualizar el módulo.

**Verificar y ajustar horario:**
Ajustes → Técnico → Automatización → Acciones planificadas

| Nombre | Frecuencia | Acción |
|--------|-----------|--------|
| `Monedero: Alerta de saldo bajo` | Diaria | Envía alerta si saldo < umbral y no se ha enviado en los últimos 7 días |
| `Monedero: Extracto semanal automático` | Semanal | Genera `patient.wallet.statement` de la semana y lo envía a familias |

**Lanzar manualmente para probar:**
Abrir la acción planificada → botón **Ejecutar manualmente**

---

## 6. Flujo completo de la alerta de saldo bajo

```
Cron diario
  ↓
Busca monederos: estado=abierto + alerta activada + saldo < umbral
                 + (sin alerta previa O última alerta hace > 7 días)
  ↓
Para cada monedero → obtiene vínculos familiares activos
  ↓
Por cada familiar:
  · canal email/ambos  → mail.template → envío inmediato al email del familiar
  · canal WA/ambos    → whatsapp.message (outgoing) → cola de envío Meta API
  ↓
Actualiza last_low_balance_alert = hoy
```

---

## 7. Diagnóstico y resolución de problemas

| Síntoma | Causa probable | Solución |
|---------|---------------|----------|
| Email no llega | Sin servidor correo saliente | Ajustes → Servidores correo saliente |
| WA en estado *Error - Cuenta* | Sin cuenta Meta configurada | Ver sección 2.3 |
| WA en estado *Error - Plantilla* | Plantilla no aprobada por Meta | Ver sección 2.4 |
| WA en estado *En cola* | Sin cuenta configurada (normal en dev) | Configura cuenta Meta en producción |
| No se generan alertas | Cron inactivo | Activar el cron en Acciones planificadas |
| Alerta no se repite | Cooldown de 7 días activo | Normal; resetea `last_low_balance_alert` manualmente si necesitas re-probar |

---

## 8. Historial de mensajes WhatsApp

Cada mensaje enviado queda registrado en:
- **WhatsApp → Mensajes** (lista global)
- El chatter del contacto familiar (nota interna con la fecha/hora del envío)

Los mensajes se purgan automáticamente después de 15 días (GC nativo de Odoo).
