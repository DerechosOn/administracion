"""
Numeracion del tarifario de CONALBOS y marca de las tarifas del despacho.

Este modulo hace DOS cosas, y solo dos:

1. Calcula el siguiente numero libre dentro de un area, para que una tarifa
   creada por el despacho no choque con el tarifario oficial.
2. Expone la constante MARCA_DERECHOS_ON, con la que se identifican las tarifas
   que no provienen de la Resolucion 02/2002 de CONALBOS.

No busca en internet, no se conecta a ningun servicio externo y no depende de
`requests`. Es logica pura y determinista: el mismo catalogo siempre da el
mismo resultado.
"""

MARCA_DERECHOS_ON = "Derechos On"


# ------------------------------------------------ numeracion del tarifario

def numeros_usados(catalogo, area_numero):
    """
    Numeros de PRIMER nivel ya ocupados en un area.
    Se cuenta el primer nivel aunque el item exista solo como padre de un
    sub-item: 18.6 esta ocupado por 18.6.1 / 18.6.3.
    Los niveles mas profundos (18.7.11) NO cuentan: el 11 de 18.7.11.1 no
    ocupa el numero 18.11.
    """
    raiz = str(area_numero or "").strip().split(".")[0]
    usados = set()
    for t in catalogo or []:
        num = str(t.get("numero") or "").strip()
        if not num.startswith(raiz + "."):
            continue
        partes = num.split(".")
        if len(partes) >= 2 and partes[1].isdigit():
            usados.add(int(partes[1]))
    return raiz, usados


def siguiente_numero(catalogo, area_numero):
    """
    Proximo numero libre, continuando DESPUES del ultimo usado.

    No rellena huecos a proposito: si CONALBOS dejo un numero sin usar
    (21.11, 14.7), ocupar ese hueco haria que un servicio creado por el usuario
    pareciera un item oficial de la Resolucion. Se continua con el ultimo + 1.
      area '1'  (1.1..1.9)                 -> '1.10'
      area '18' (18.1..18.9, 18.7.11.1)     -> '18.10'
      area '2'  (solo existe '2')          -> '2.1'
    """
    raiz, usados = numeros_usados(catalogo, area_numero)
    if not raiz.isdigit():
        raiz = "1"
    n = (max(usados) + 1) if usados else 1
    return "%s.%d" % (raiz, n)


def huecos_numericos(catalogo, area_numero):
    """Numeros que el tarifario oficial dejo sin usar dentro del area."""
    raiz, usados = numeros_usados(catalogo, area_numero)
    if not usados:
        return []
    return ["%s.%d" % (raiz, n) for n in range(1, max(usados)) if n not in usados]


def areas_numericas(catalogo):
    """
    Devuelve [(raiz, etiqueta_display, cantidad_items)] ordenado numericamente.
    Sirve para que el administrador elija el area y el sistema sugiera el numero.
    """
    acc = {}
    for t in catalogo or []:
        num = str(t.get("numero") or "").strip()
        if not num:
            continue
        raiz = num.split(".")[0]
        d = acc.setdefault(raiz, {"area": t.get("area") or "", "n": 0})
        d["n"] += 1
        if not d["area"]:
            d["area"] = t.get("area") or ""
    out = []
    for raiz in sorted(acc, key=lambda x: (len(x), x)):
        out.append((raiz, acc[raiz]["area"], acc[raiz]["n"]))
    return out


def opciones_alta(catalogo, max_areas=40, areas_propias=None):
    """
    Lista [{'numero', 'area', 'items', 'siguiente', 'huecos'}] para alimentar el
    selector de area del formulario de alta. Se calcula en el servidor para que el
    formulario sea utilizable aunque el JavaScript no se ejecute.

    `areas_propias` son las areas creadas por el despacho. Se agregan al final y
    con `propia: True` para distinguirlas en la interfaz.
    """
    out = [{"numero": raiz, "area": lbl, "items": n, "propia": False,
            "siguiente": siguiente_numero(catalogo, raiz),
            "huecos": huecos_numericos(catalogo, raiz)[:6]}
           for raiz, lbl, n in areas_numericas(catalogo)[:max_areas]]
    for raiz, nombre in areas_propias or []:
        out.append({"numero": str(raiz), "area": nombre, "items": 0, "propia": True,
                    "siguiente": siguiente_numero(catalogo, raiz), "huecos": []})
    return out


def siguiente_raiz(catalogo, areas_propias=None):
    """
    Proxima raiz numerica libre para un area NUEVA del despacho.

    Las areas oficiales ocupan las raices 1..23. Una area propia no puede
    reutilizarlas (pareceria oficial), asi que se continua despues de la mayor
    raiz en uso, sea oficial o propia.
    """
    raices = set()
    for t in catalogo or []:
        num = str(t.get("numero") or "").strip()
        if num and num.split(".")[0].isdigit():
            raices.add(int(num.split(".")[0]))
    for raiz, _n in areas_propias or []:
        if str(raiz).isdigit():
            raices.add(int(raiz))
    return str(max(raices) + 1) if raices else "1"
