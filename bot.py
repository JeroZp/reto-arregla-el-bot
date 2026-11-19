"""Bot de seguimiento de radicación.

Lee datos/cuentas.csv, consulta cada cuenta en el portal de la aseguradora y escribe:
  - salida/resultados.csv: id_cuenta, aseguradora, valor, estado, dias_hasta_radicar
  - salida/excepciones.csv: id_cuenta, motivo (cuentas que no se pudieron procesar)

Una cuenta con problemas nunca detiene a las demás: va a excepciones con un motivo
que el equipo de operación pueda entender y resolver.
"""
import csv
from datetime import date, datetime
from pathlib import Path

from portal.portal import CuentaNoEncontrada, PortalNoDisponible, consultar

ENTRADA = Path("datos/cuentas.csv")
SALIDA_RESULTADOS = Path("salida/resultados.csv")
SALIDA_EXCEPCIONES = Path("salida/excepciones.csv")

CAMPOS_RESULTADOS = ["id_cuenta", "aseguradora", "valor", "estado", "dias_hasta_radicar"]
CAMPOS_EXCEPCIONES = ["id_cuenta", "motivo"]

MAX_REINTENTOS = 2  # además del primer intento: hasta 3 consultas por cuenta

FORMATO_FECHA_CSV = "%d/%m/%Y"      # fecha_servicio en datos/cuentas.csv
FORMATO_FECHA_PORTAL = "%Y-%m-%d"   # fecha_radicacion en el portal v2.0


class CuentaInvalida(Exception):
    """La cuenta no se puede procesar. El mensaje es el motivo que verá operación."""


# --- Lectura y validación de la entrada ---------------------------------------

def leer_cuentas(ruta):
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def interpretar_valor(texto):
    """Convierte el valor de la cuenta a entero en pesos.

    Acepta separadores de miles con punto ("1.320.500"), como se escribe en Colombia.
    Rechaza valores vacíos, no numéricos o menores o iguales a cero.
    """
    limpio = (texto or "").strip().replace(".", "")
    if not limpio.isdigit():
        raise CuentaInvalida(f"El valor de la cuenta «{texto}» no es un número válido en cuentas.csv")
    valor = int(limpio)
    if valor <= 0:
        raise CuentaInvalida(
            f"La cuenta tiene valor {valor} en cuentas.csv; una cuenta radicada debe tener valor "
            "mayor a cero. Revisar el valor con facturación antes de reportarla"
        )
    return valor


def interpretar_fecha_servicio(texto):
    try:
        return datetime.strptime((texto or "").strip(), FORMATO_FECHA_CSV).date()
    except ValueError:
        raise CuentaInvalida(
            f"La fecha de servicio «{texto}» no tiene el formato dd/mm/aaaa en cuentas.csv"
        ) from None


# --- Consulta al portal ------------------------------------------------------

def consultar_con_reintentos(id_cuenta):
    """Consulta el portal reintentando si no responde (máximo MAX_REINTENTOS reintentos)."""
    intentos = 1 + MAX_REINTENTOS
    for intento in range(1, intentos + 1):
        try:
            return consultar(id_cuenta)
        except PortalNoDisponible:
            if intento == intentos:
                raise CuentaInvalida(
                    f"El portal no respondió después de {intentos} intentos "
                    f"(1 + {MAX_REINTENTOS} reintentos). Volver a consultar más tarde"
                ) from None
            print(f"  {id_cuenta}: el portal no respondió (intento {intento}/{intentos}), reintentando...")
        except CuentaNoEncontrada:
            raise CuentaInvalida(
                "El portal no tiene registro de la cuenta. Verificar que se haya radicado "
                "o que el id_cuenta esté bien escrito"
            ) from None


def interpretar_respuesta_portal(respuesta):
    """Traduce la respuesta del portal (formato v2.0) a (estado, fecha_radicacion).

    Si el portal vuelve a cambiar su formato, este es el único lugar que hay que tocar.
    fecha_radicacion puede ser None (por ejemplo, cuentas en revisión).
    """
    estado = respuesta.get("estado_radicacion")
    if not estado:
        raise CuentaInvalida(
            "La respuesta del portal no trae 'estado_radicacion'; puede que el portal haya "
            f"cambiado de formato otra vez. Campos recibidos: {sorted(respuesta)}"
        )

    fecha_texto = respuesta.get("fecha_radicacion")
    if fecha_texto is None:
        return estado, None
    try:
        fecha = datetime.strptime(fecha_texto, FORMATO_FECHA_PORTAL).date()
    except (TypeError, ValueError):
        raise CuentaInvalida(
            f"El portal devolvió una fecha de radicación «{fecha_texto}» con formato inesperado "
            "(se esperaba aaaa-mm-dd)"
        ) from None
    return estado, fecha


# --- Proceso por cuenta -------------------------------------------------------

def procesar_cuenta(cuenta):
    """Devuelve la fila de resultados de una cuenta o lanza CuentaInvalida."""
    id_cuenta = cuenta["id_cuenta"]
    valor = interpretar_valor(cuenta.get("valor"))
    fecha_servicio = interpretar_fecha_servicio(cuenta.get("fecha_servicio"))

    estado, fecha_radicacion = interpretar_respuesta_portal(consultar_con_reintentos(id_cuenta))

    dias = ""
    if fecha_radicacion is not None:
        dias = calcular_dias(fecha_servicio, fecha_radicacion)

    return {
        "id_cuenta": id_cuenta,
        "aseguradora": cuenta["aseguradora"],
        "valor": valor,
        "estado": estado,
        "dias_hasta_radicar": dias,
    }


def calcular_dias(fecha_servicio: date, fecha_radicacion: date) -> int:
    dias = (fecha_radicacion - fecha_servicio).days
    if dias < 0:
        raise CuentaInvalida(
            f"El portal reporta radicación el {fecha_radicacion:%d/%m/%Y}, antes de la fecha "
            f"de servicio ({fecha_servicio:%d/%m/%Y}). Revisar fechas"
        )
    return dias


# --- Salida -------------------------------------------------------------------

def escribir_csv(ruta, campos, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(filas)


def procesar():
    resultados, excepciones = [], []

    for cuenta in leer_cuentas(ENTRADA):
        id_cuenta = cuenta.get("id_cuenta", "").strip() or "(sin id)"
        try:
            resultados.append(procesar_cuenta(cuenta))
        except CuentaInvalida as error:
            excepciones.append({"id_cuenta": id_cuenta, "motivo": str(error)})
        except Exception as error:  # red de seguridad: un error inesperado no tumba al resto
            excepciones.append({
                "id_cuenta": id_cuenta,
                "motivo": f"Error inesperado del bot ({type(error).__name__}: {error}). Escalar a RPA",
            })

    escribir_csv(SALIDA_RESULTADOS, CAMPOS_RESULTADOS, resultados)
    escribir_csv(SALIDA_EXCEPCIONES, CAMPOS_EXCEPCIONES, excepciones)

    print(f"Listo: {len(resultados)} cuentas procesadas, {len(excepciones)} en excepciones")
    for exc in excepciones:
        print(f"  - {exc['id_cuenta']}: {exc['motivo']}")


if __name__ == "__main__":
    procesar()
