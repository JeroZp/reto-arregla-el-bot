# CAMBIOS

## 1. Qué cambió en el portal y cómo me di cuenta

El bot se caía en la primera cuenta con un `KeyError: 'estado'`. Ese error dice que el portal ya no devuelve ese campo, así que fui a mirar qué devuelve ahora (`portal/respuestas.json`, que ya se identifica como `"version_portal": "2.0"`) y lo comparé con lo que el bot esperaba:

| Antes (lo que esperaba el bot) | Ahora (portal 2.0) |
|---|---|
| `estado` | `estado_radicacion` |
| `fecha` en formato `dd/mm/aaaa` | `fecha_radicacion` en formato `aaaa-mm-dd` |
| Siempre traía fecha | La fecha puede venir en `null` (cuentas `en_revision`, que todavía no tienen fecha de radicación) |

Al revisar el resto del flujo también encontré problemas que no venían del portal, sino de los datos de entrada y del propio bot:

- **C-1003** trae el valor como `"1.320.500"`, con puntos de miles. Con `int()` el bot se caía.
- **C-1005** no existe en el portal (`CuentaNoEncontrada`).
- **C-1006** tiene `valor = 0`.
- **C-1007** a veces no responde a la primera (`PortalNoDisponible`), pero responde si se reintenta.
- Si había un error en cualquier cuenta, el bot se caía completo y no escribía nada.

## 2. Qué arreglé

- **Adapté el bot al portal 2.0.** Toda la lectura de la respuesta del portal quedó en una sola función, `interpretar_respuesta_portal`. Si el portal vuelve a cambiar, se arregla ahí. Si llega una respuesta sin `estado_radicacion`, la cuenta va a excepciones con un motivo que dice que el portal pudo haber cambiado de formato y qué campos llegaron. Así el próximo cambio se diagnostica leyendo `excepciones.csv`, sin tener que depurar.
- **Fecha nula:** si la cuenta no tiene fecha de radicación, `dias_hasta_radicar` queda vacío y la cuenta sí sale en resultados con su estado (`en_revision`).
- **Cada cuenta se procesa por separado.** Un error en una cuenta la manda a `salida/excepciones.csv` con `id_cuenta` y `motivo`, y el bot sigue con las demás. Los dos archivos se escriben siempre, aunque queden vacíos.
- **Reintentos:** si el portal no responde, el bot reintenta hasta 2 veces (3 consultas en total). Si después de eso sigue sin responder, la cuenta va a excepciones con el motivo "volver a consultar más tarde". En consola se ve cada reintento.
- **Motivos pensados para quien opera, no para quien programó.** Cada motivo dice qué pasó y qué hacer. Por ejemplo: *"El portal no tiene registro de la cuenta. Verificar que se haya radicado o que el id_cuenta esté bien escrito"*.
- **Red de seguridad:** cualquier error que no esperaba también manda la cuenta a excepciones, con el detalle técnico y la indicación "Escalar a RPA", en vez de tumbar toda la corrida.

## 3. Decisiones que tomé y por qué

**La cuenta C-1006, con valor 0, va a excepciones aunque el portal la muestre como radicada.**
Una cuenta de cobro por $0 no tiene sentido: lo más probable es un error de digitación o una cuenta que no se debía radicar. Si la reporto como "radicada, 5 días", el informe parece correcto y nadie la revisa. En excepciones, alguien de facturación la mira. Elegí que el bot no "arregle" datos que no entiende y que los muestre. La misma regla aplica a cualquier valor negativo o que no sea numérico.

**`"1.320.500"` se interpreta como 1.320.500 pesos y no como un error.**
Ya que el punto es el separador de miles, y los valores de las cuentas son en pesos enteros. Por eso el bot quita los puntos y la cuenta se procesa. No acepto comas ni decimales. Si algún día aparecen, prefiero que la cuenta caiga en excepciones a adivinar el valor.

**"Máximo 2 reintentos" significa 1 intento + 2 reintentos.**
El enunciado habla de *re*-intentos, así que los cuento aparte del primer intento. El número está en una constante (`MAX_REINTENTOS`) por si operación quiere cambiarlo. No agregué una espera entre reintentos porque el portal es simulado y respondería igual. Con un portal real pondría una pausa corta y creciente, para no insistirle a un servidor que está caído.

**Una cuenta en revisión sale en resultados, no en excepciones.**
Que no tenga fecha de radicación no es un error: es un estado válido del proceso. Por eso sale en resultados con `dias_hasta_radicar` vacío. No escribí 0 ni "N/A", porque 0 se confunde con "se radicó el mismo día".

**Validación extra: radicación anterior al servicio.**
Si el portal reporta una fecha de radicación anterior a la fecha de servicio, los días saldrían negativos. Eso sería un dato imposible, así que la cuenta va a excepciones para que alguien revise las fechas. Ninguna cuenta actual cae aquí, pero es la clase de dato raro que no quiero que pase en silencio a un informe.

## Nota para correr la verificación en Windows

En una consola de Windows con la codificación por defecto, `verificar.py` se cae al imprimir el símbolo `✓`. El bot no tiene nada que ver y tampoco modifiqué `verificar.py` porque las reglas lo prohíben.