"""Catálogo oficial = lista_produtos_RToficial.xlsx (fonte única de produtos)."""
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
    "itens": [],  # lista única
    "total": 0,
}

_TTL_SEGUNDOS = 60


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
    existentes = [p for p in candidatos if os.path.exists(p)]
    if not existentes:
        return None
    # Preferir a mais recente entre data/ e Documents
    return max(existentes, key=lambda p: os.path.getmtime(p))


def carregar_lista_rt(force=False):
    """Carrega/atualiza o índice ean + codigo_omie da planilha RT."""
    path = caminho_lista_rt()
    agora = time.time()
    if (
        not force
        and _CACHE["itens"]
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
    unicos = {}

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
            "codigo_omie": omie or codigo or ean,
            "codigo": codigo or omie or ean,
            "descricao": descricao,
        }
        chave = item["ean"] + "|" + item["codigo_omie"]
        unicos[chave] = item

        for key, bucket in (
            (ean, by_ean),
            (omie, by_omie),
            (codigo, by_codigo),
            (item["ean"], by_ean),
            (item["codigo_omie"], by_omie),
        ):
            if key:
                bucket[key] = item
                lim = _limpo(key)
                if lim and lim not in bucket:
                    bucket[lim] = item

    itens = sorted(unicos.values(), key=lambda x: (x["descricao"] or "").upper())
    _CACHE.update({
        "ts": agora,
        "path": path,
        "by_ean": by_ean,
        "by_omie": by_omie,
        "by_codigo": by_codigo,
        "itens": itens,
        "total": len(itens),
    })
    return True, f"{len(itens)} produtos indexados ({os.path.basename(path)})"


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
    """Resolve por ean, codigo_omie ou codigo na planilha RT."""
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
        if codigo.isdigit():
            sem = codigo.lstrip("0")
            if sem and sem in bucket:
                return bucket[sem]
    return None


def item_para_produto(item):
    """Converte linha da planilha para o formato da tabela produtos."""
    desc = item.get("descricao") or ""
    marca = ""
    nome = desc
    partes = desc.split(" ", 1)
    if len(partes) > 1 and len(partes[0]) <= 20:
        marca, nome = partes[0], partes[1]
    ean = item.get("ean") or item.get("codigo_omie") or item.get("codigo")
    return {
        "ean": ean,
        "produto": nome or desc or ean,
        "marca": marca,
        "unidade_medida": "UN",
        "base_especifica": "",
        "instrucao_dosagem": "",
        "lote": "",
        "data_vencimento": "",
        "codigo_interno": item.get("codigo_omie") or item.get("codigo") or ean,
        "quantidade_estoque": 0,
        "fonte": "rt_oficial",
    }


def listar_como_produtos(search=""):
    """Lista o catálogo oficial (planilha) no formato de produtos do sistema."""
    carregar_lista_rt(force=False)
    itens = _CACHE.get("itens") or []
    q = (search or "").strip().upper()
    out = []
    for item in itens:
        p = item_para_produto(item)
        if q:
            blob = " ".join([
                p.get("ean") or "",
                p.get("codigo_interno") or "",
                p.get("produto") or "",
                p.get("marca") or "",
                item.get("codigo") or "",
            ]).upper()
            if q not in blob:
                continue
        out.append(p)
    return out


def chaves_oficiais():
    """Conjuntos de ean e codigo_omie presentes na planilha."""
    carregar_lista_rt(force=False)
    eans, omies = set(), set()
    for item in _CACHE.get("itens") or []:
        if item.get("ean"):
            eans.add(item["ean"])
        if item.get("codigo_omie"):
            omies.add(item["codigo_omie"])
        if item.get("codigo"):
            omies.add(item["codigo"])
    return eans, omies


def adicionar_na_planilha(ean, produto="", marca="", codigo_omie=None, origem="manual"):
    """Adiciona (ou garante) um produto na planilha oficial — aba 'Lista Unica'.

    Grava em todas as cópias existentes (data/ e Documents) quando possível;
    considera sucesso se ao menos uma cópia foi atualizada.
    Retorna (ok, msg).
    """
    ean = _norm(ean)
    if not ean:
        return False, "EAN/código vazio"

    # Não duplica produto que já consta na planilha
    carregar_lista_rt(force=True)
    if resolver_na_planilha(ean):
        return True, "Produto já consta na planilha oficial"

    codigo_omie = _norm(codigo_omie) if codigo_omie else None
    codigo_omie = codigo_omie or ean
    tem_ean = "SIM" if ean.isdigit() else "NAO"
    ean_origem = "codigo_barras" if tem_ean == "SIM" else "codigo_produto"
    motivo = (None if tem_ean == "SIM"
              else "EAN preenchido com o codigo da coluna A (sem codigo de barras)")

    desc_parts = []
    if marca and str(marca).strip():
        desc_parts.append(str(marca).strip().upper())
    if produto and str(produto).strip():
        desc_parts.append(str(produto).strip().upper())
    descricao = " ".join(desc_parts) or ean

    def valor(v):
        s = str(v)
        return int(s) if s.isdigit() else s

    linha = [
        valor(ean),       # codigo
        descricao,        # descricao
        valor(codigo_omie),  # codigo_omie
        valor(ean),       # ean
        tem_ean,          # tem_ean
        ean_origem,       # ean_origem
        "SIM",            # encontrado
        "codigo",         # cruzado_por
        None,             # fonte_ean
        motivo,           # motivo_sem_ean
        origem,           # origem
    ]

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p_data = os.path.join(raiz, "data", "lista_produtos_RToficial.xlsx")
    destinos = []
    for p in (p_data, caminho_lista_rt()):
        if p and os.path.exists(p) and p not in destinos:
            destinos.append(p)

    escritos, erros = [], []
    for dest in destinos:
        try:
            wb = load_workbook(dest)
            ws = wb["Lista Unica"] if "Lista Unica" in wb.sheetnames else wb.active
            # verificação defensiva de duplicidade por ean no arquivo real
            i_ean = None
            for i, c in enumerate(ws[1], start=0):
                if str(c.value or "").strip().lower() == "ean":
                    i_ean = i
                    break
            dup = False
            if i_ean is not None:
                for r in ws.iter_rows(min_row=2, values_only=True):
                    if i_ean < len(r) and _norm(r[i_ean]) == ean:
                        dup = True
                        break
            if not dup:
                ws.append(linha)
                wb.save(dest)
            escritos.append(dest)
        except PermissionError:
            erros.append(f"{os.path.basename(dest)} (sem permissão)")
        except Exception as e:
            erros.append(f"{os.path.basename(dest)} ({e})")

    carregar_lista_rt(force=True)
    if escritos:
        msg = "adicionado à planilha oficial (" + ", ".join(
            os.path.basename(p) for p in escritos) + ")"
        if erros:
            msg += "; falha em " + "; ".join(erros)
        return True, msg
    return False, "não foi possível gravar na planilha oficial: " + "; ".join(erros)
