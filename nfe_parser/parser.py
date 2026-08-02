import xml.etree.ElementTree as ET
import re

NAMESPACES = {
    "nfe": "http://www.portalfiscal.inf.br/nfe",
}


def _strip_ns(tag):
    return re.sub(r"\{.*?\}", "", tag)


def parse_nfe_xml(caminho):
    tree = ET.parse(caminho)
    root = tree.getroot()

    # Try with namespace first
    ns = {"ns": "http://www.portalfiscal.inf.br/nfe"}
    nfe = root.find(".//ns:infNFe", ns)
    if nfe is None:
        nfe = root.find(".//infNFe")

    if nfe is None:
        raise ValueError("XML inválido: tag infNFe não encontrada")

    ide = nfe.find("ns:ide", ns) if nfe.find("ns:ide", ns) is not None else nfe.find("ide")
    emit = nfe.find("ns:emit", ns) if nfe.find("ns:emit", ns) is not None else nfe.find("emit")

    numero = ide.findtext("ns:nNF", "", ns) if ide is not None else ""
    serie = ide.findtext("ns:serie", "", ns) if ide is not None else ""
    data_emissao = ide.findtext("ns:dhEmi", "", ns) if ide is not None else ""
    if not data_emissao:
        data_emissao = ide.findtext("ns:dEmi", "", ns) if ide is not None else ""

    fornecedor = emit.findtext("ns:xNome", "", ns) if emit is not None else ""
    cnpj = emit.findtext("ns:CNPJ", "", ns) if emit is not None else ""

    chave = ""
    prot = root.find(".//ns:protNFe", ns)
    if prot is not None:
        infProt = prot.find("ns:infProt", ns)
        if infProt is not None:
            chave = infProt.findtext("ns:chNFe", "", ns)

    if not chave:
        nfe_tag = root.find(".//ns:NFe", ns) if root.find(".//ns:NFe", ns) is not None else root.find(".//NFe")
        if nfe_tag is not None:
            inf_nfe = nfe_tag.find("ns:infNFe", ns) if nfe_tag.find("ns:infNFe", ns) is not None else nfe_tag.find("infNFe")
            if inf_nfe is not None:
                chave = (inf_nfe.get("Id") or "").replace("NFe", "", 1)
        if not chave:
            chave = (nfe.get("Id") or "").replace("NFe", "", 1)

    itens = []
    det_list = nfe.findall("ns:det", ns)
    if not det_list:
        det_list = nfe.findall("det")

    for det in det_list:
        prod = det.find("ns:prod", ns) if det.find("ns:prod", ns) is not None else det.find("prod")
        if prod is None:
            continue

        cEAN = prod.findtext("ns:cEAN", "", ns) if prod.find("ns:cEAN", ns) is not None else prod.findtext("cEAN", "")
        cProd = prod.findtext("ns:cProd", "", ns) if prod.find("ns:cProd", ns) is not None else prod.findtext("cProd", "")
        xProd = prod.findtext("ns:xProd", "", ns) if prod.find("ns:xProd", ns) is not None else prod.findtext("xProd", "")
        ncm = prod.findtext("ns:NCM", "", ns) if prod.find("ns:NCM", ns) is not None else prod.findtext("NCM", "")
        uCom = prod.findtext("ns:uCom", "", ns) if prod.find("ns:uCom", ns) is not None else prod.findtext("uCom", "")
        qCom = prod.findtext("ns:qCom", "", ns) if prod.find("ns:qCom", ns) is not None else prod.findtext("qCom", "")

        ean = cEAN.strip() if cEAN and cEAN.strip() else ""
        quantidade = float(qCom.replace(",", ".")) if qCom else 1

        rastro = prod.find("ns:rastro", ns) if prod.find("ns:rastro", ns) is not None else prod.find("rastro")
        lote = ""
        data_venc = ""
        if rastro is not None:
            lote = rastro.findtext("ns:lote", "", ns) if rastro.find("ns:lote", ns) is not None else rastro.findtext("lote", "")
            dVal = rastro.findtext("ns:dVal", "", ns) if rastro.find("ns:dVal", ns) is not None else rastro.findtext("dVal", "")
            if dVal:
                data_venc = dVal[:10]

        itens.append({
            "ean": ean,
            "codigo_produto": cProd.strip(),
            "descricao": xProd.strip() if xProd else "",
            "ncm": ncm.strip(),
            "unidade": uCom.strip() if uCom else "UN",
            "quantidade_esperada": quantidade,
            "lote": lote,
            "data_vencimento": data_venc,
        })

    return {
        "chave_acesso": chave,
        "numero": numero,
        "serie": serie,
        "fornecedor": fornecedor,
        "cnpj_fornecedor": cnpj,
        "data_emissao": data_emissao[:10] if data_emissao else "",
        "itens": itens,
    }
