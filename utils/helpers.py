import os
import json
import re
from datetime import datetime


def formatar_data(dt_str):
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(dt_str)


def parse_codigo_lido(raw):
    """
    Interpreta leitura de barcode/QR.
    Aceita EAN puro ou QR multi-linha (EAN:, Lote:, Validade:, ID:).
    """
    texto = (raw or "").strip()
    resultado = {
        "ean": "", "lote": "", "data_vencimento": "",
        "codigo_interno": "", "bruto": texto,
    }
    if not texto:
        return resultado

    upper = texto.upper()
    multilinha = "\n" in texto or "EAN:" in upper or "ID:" in upper

    if multilinha:
        for linha in texto.replace("\r", "").split("\n"):
            linha = linha.strip()
            if ":" not in linha:
                continue
            chave, _, val = linha.partition(":")
            chave_n = re.sub(r"\s+", "", chave.strip().lower())
            val = val.strip()
            if chave_n == "ean":
                resultado["ean"] = val
            elif chave_n == "lote":
                resultado["lote"] = val
            elif chave_n in ("validade", "vencimento", "datavencimento"):
                resultado["data_vencimento"] = val[:10] if val else ""
            elif chave_n in ("id", "codigo", "codigointerno", "sku"):
                resultado["codigo_interno"] = val
        if not resultado["ean"]:
            resultado["ean"] = resultado["codigo_interno"]
        return resultado

    resultado["ean"] = texto
    return resultado


def exportar_json(dados, filename="export.json"):
    pasta = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
    os.makedirs(pasta, exist_ok=True)
    path = os.path.join(pasta, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, default=str)
    return path


def limpar_tela():
    os.system("cls" if os.name == "nt" else "clear")


def exibir_cabecalho(titulo):
    limpar_tela()
    print("=" * 60)
    print(f"  {titulo}")
    print("=" * 60)
