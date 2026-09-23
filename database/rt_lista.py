"""Índice em memória da lista RT oficial (ean + codigo_omie) para bipagem precisa."""
import os
import re
import time
from openpyxl import load_workbook

_CACHE = {
    "ts": 0,
    "path": None,
    "by_ean": {},
    "by_omie": {},
    "by_codigo": {},
    "total": 0,
}

_TTL_SEGUNDOS = 300  # 5 min


def _norm(val):
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    if s.endswith(".0") and s[:-2].replace("-", "").replace(".", "").isdigit():
        s = s[:-2]
    return s


def _limpo(val):
    return re.sub(r"[^0-9A-Za-z]", "", _norm(val)).upper()


def caminho_lista_rt():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidatos = [
        os.path.join(raiz, "data", "lista_produtos_RToficial.xlsx"),
        os.path.join(
            os.path.expanduser("~"), "Documents",
            "produtos omie 21092026", "lista_produtos_RToficial.xlsx",
        ),
        os.path.join(raiz, "data", "lista_produtos_unica.xlsx"),
    ]
    return next((p for p in candidatos if os.path.exists(p)), None)


def carregar_lista_rt(force=False):
    """Carrega/atualiza o índice ean + codigo_omie da planilha RT."""
    path = caminho_lista_rt()
    agora = time.time()
    if (
        not force
        and _CACHE["by_ean"]
        and _CACHE["path"] == path
        and (agora - _CACHE["ts"]) < _TTL_SEGUNDOS
    ):
        return True, f"cache {_CACHE['total']} produtos"

    if not path:
        return False, "lista_produtos_RToficial.xlsx não encontrada"

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb["Lista Unica"] if "Lista Unica" in wb.sheetnames else wb.active
        linhas = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as e:
        return False, f"Erro ao ler planilha RT: {e}"

    if len(linhas) < 2:
        return False, "Planilha RT vazia"

    cab = [str(c or "").strip().lower() for c in linhas[0]]

    def idx(*nomes):
        for n in nomes:
            if n in cab:
                return cab.index(n)
        return None

    i_ean = idx("ean", "codigo_barras", "gtin")
    i_omie = idx("codigo_omie")
    i_cod = idx("codigo")
    i_desc = idx("descricao", "produto", "nome")

    by_ean, by_omie, by_codigo = {}, {}, {}

    for linha in linhas[1:]:
        if not linha:
            continue

        def cell(i):
            if i is None or i >= len(linha):
                return ""
            return _norm(linha[i])

        ean = cell(i_ean)
        omie = cell(i_omie)
        codigo = cell(i_cod)
        descricao = cell(i_desc)
        if not ean and not omie and not codigo:
            continue
        if not descricao:
            descricao = ean or omie or codigo

        item = {
            "ean": ean or omie or codigo,
            "codigo_omie": omie or codigo,
            "codigo": codigo or omie,
            "descricao": descricao,
        }

        for key, bucket in (
            (ean, by_ean),
            (omie, by_omie),
            (codigo, by_codigo),
        ):
            if key:
                bucket[key] = item
                lim = _limpo(key)
                if lim and lim not in bucket:
                    bucket[lim] = item

    _CACHE.update({
        "ts": agora,
        "path": path,
        "by_ean": by_ean,
        "by_omie": by_omie,
        "by_codigo": by_codigo,
        "total": len({id(v) for v in list(by_ean.values()) + list(by_omie.values())}),
    })
    # total único por ean preferencial
    unicos = {}
    for it in list(by_ean.values()) + list(by_omie.values()) + list(by_codigo.values()):
        unicos[it["ean"] + "|" + it["codigo_omie"]] = it
    _CACHE["total"] = len(unicos)

    return True, f"{_CACHE['total']} produtos indexados ({os.path.basename(path)})"


def status_lista_rt():
    ok, msg = carregar_lista_rt(force=False)
    return {
        "sucesso": ok,
        "msg": msg,
        "total": _CACHE["total"],
        "arquivo": _CACHE["path"],
        "ean_index": len(_CACHE["by_ean"]),
        "omie_index": len(_CACHE["by_omie"]),
    }


def resolver_na_planilha(codigo_lido):
    """
    Resolve bipagem pela planilha: tenta EAN e depois codigo_omie (e codigo).
    Retorna dict {ean, codigo_omie, codigo, descricao} ou None.
    """
    codigo = _norm(codigo_lido)
    if not codigo:
        return None
    carregar_lista_rt(force=False)

    for bucket in (_CACHE["by_ean"], _CACHE["by_omie"], _CACHE["by_codigo"]):
        if codigo in bucket:
            return bucket[codigo]
        lim = _limpo(codigo)
        if lim and lim in bucket:
            return bucket[lim]
        # sem zeros à esquerda (EAN)
        if codigo.isdigit():
            sem = codigo.lstrip("0")
            if sem and sem in bucket:
                return bucket[sem]
    return None
