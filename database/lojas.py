"""Lojas físicas atendidas pelo inventário (sessões de contagem separadas por loja)."""

LOJAS = [
    {"codigo": "RTJ", "nome": "RTJ", "cnpj": "06.241.162/0001-06"},
    {"codigo": "RTB", "nome": "RTB", "cnpj": "11.948.022/0001-02"},
]

LOJA_PADRAO = "RTJ"


def lista_lojas():
    return [dict(l) for l in LOJAS]


def validar_loja(codigo):
    codigo = (codigo or "").strip().upper()
    for l in LOJAS:
        if l["codigo"] == codigo:
            return codigo
    return LOJA_PADRAO


def loja_por_codigo(codigo):
    codigo = (codigo or "").strip().upper()
    for l in LOJAS:
        if l["codigo"] == codigo:
            return dict(l)
    return None