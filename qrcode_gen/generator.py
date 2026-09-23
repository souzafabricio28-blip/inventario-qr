import os
import qrcode
from io import BytesIO
import base64

EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports", "qrcodes")


def _garantir_pasta():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    return EXPORT_DIR


def gerar_qrcode(ean, produto="", marca="", unidade="", base="", dosagem="",
                 lote="", data_vencimento="", codigo_interno=""):
    dados = (
        f"EAN: {ean}\n"
        f"Marca: {marca}\n"
        f"Produto: {produto}\n"
        f"Unidade: {unidade}\n"
        f"Base: {base}\n"
        f"Dosagem: {dosagem}\n"
        f"Lote: {lote}\n"
        f"Validade: {data_vencimento}\n"
        f"ID: {codigo_interno}"
    )

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(dados)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    pasta = _garantir_pasta()
    arquivo = os.path.join(pasta, f"{ean}.png")
    img.save(arquivo)
    return arquivo


def gerar_qrcode_base64(ean, produto="", marca="", unidade="",
                        base="", dosagem="", lote="", data_vencimento="",
                        codigo_interno=""):
    dados = (
        f"EAN: {ean}\n"
        f"Marca: {marca}\n"
        f"Produto: {produto}\n"
        f"Unidade: {unidade}\n"
        f"Base: {base}\n"
        f"Dosagem: {dosagem}\n"
        f"Lote: {lote}\n"
        f"Validade: {data_vencimento}\n"
        f"ID: {codigo_interno}"
    )

    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(dados)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def gerar_lote_qrcode(produtos):
    arquivos = []
    for p in produtos:
        arq = gerar_qrcode(
            ean=p["ean"],
            produto=p.get("produto", ""),
            marca=p.get("marca", ""),
            unidade=p.get("unidade_medida", ""),
            base=p.get("base_especifica", ""),
            dosagem=p.get("instrucao_dosagem", ""),
            lote=p.get("lote", ""),
            data_vencimento=p.get("data_vencimento", ""),
            codigo_interno=p.get("codigo_interno", ""),
        )
        arquivos.append(arq)
    return arquivos
