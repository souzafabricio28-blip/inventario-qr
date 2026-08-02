import os
import re
from openpyxl import load_workbook
from .backend import criar_produto


COLUNAS_MApeamento = {
    "ean": ["ean", "código de barras", "codigo", "código", "gtin", "barras"],
    "produto": ["produto", "descricao", "descrição", "descrição",
                "nome", "item", "descrição do produto", "descricao produto"],
    "marca": ["marca", "fabricante", "marca do produto"],
    "unidade_medida": ["unidade", "un", "unidade medida", "umed",
                       "unidade de medida", "und"],
    "base_especifica": ["base", "base específica", "base especifica",
                        "tipo base", "base técnica", "base tecnica"],
    "instrucao_dosagem": ["instrucao", "dosagem", "instrução",
                          "instrução dosagem", "regra", "proporção",
                          "instrucao dosagem"],
    "lote": ["lote", "batch", "lote fabricação", "lote fabricacao", "nro lote", "número lote"],
    "data_vencimento": ["data venci", "vencimento", "data venc", "validade", "dt venc",
                        "data de validade", "val", "venc"],
    "codigo_interno": ["codigo interno", "código interno", "id",
                        "cod_interno", "código", "referencia", "referência",
                        "sku", "código próprio", "codigo proprio"],
    "deposito": ["deposito", "depósito", "localização", "localizacao", "local", "armazém", "armazem"],
    "preco": ["preco", "preço", "valor", "preco venda", "preço venda",
              "preco custo", "preço custo", "valor unitário"],
}


def _normalizar_nome_coluna(nome):
    return re.sub(r"[_\-\s]", "", nome.strip().lower())


def _mapear_colunas(cabecalhos):
    mapping = {}
    cab_normalizados = {}
    for col in cabecalhos:
        cab_normalizados[col] = _normalizar_nome_coluna(col)

    for campo_alvo, possibilidades in COLUNAS_MApeamento.items():
        poss_norm = [_normalizar_nome_coluna(p) for p in possibilidades]
        for col_original, col_norm in cab_normalizados.items():
            if col_norm in poss_norm:
                mapping[campo_alvo] = col_original
                break

    return mapping


def importar_excel(caminho_arquivo):
    if not os.path.exists(caminho_arquivo):
        return False, f"Arquivo não encontrado: {caminho_arquivo}"

    try:
        wb = load_workbook(caminho_arquivo, read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return False, "Planilha vazia"

        linhas = list(ws.iter_rows(values_only=True))
        if len(linhas) < 2:
            return False, "Planilha sem dados (apenas cabeçalho ou vazia)"

        cabecalhos = [str(c or "").strip() for c in linhas[0]]
        mapping = _mapear_colunas(cabecalhos)

        campos_obrigatorios = ["ean", "produto"]
        for campo in campos_obrigatorios:
            if campo not in mapping:
                return False, f"Coluna obrigatória '{campo}' não encontrada no Excel. Colunas encontradas: {', '.join(cabecalhos)}"

        importados = 0
        erros = []
        for idx, linha in enumerate(linhas[1:], start=2):
            if all(v is None or str(v).strip() == "" for v in linha):
                continue

            dados = {}
            for campo_alvo, col_orig in mapping.items():
                pos = cabecalhos.index(col_orig)
                val = linha[pos] if pos < len(linha) else None
                dados[campo_alvo] = str(val).strip() if val is not None else ""

            ean = dados.get("ean", "").replace(".0", "")
            if not ean or ean == "":
                continue

            produto_raw = dados.get("produto", "")
            marca = dados.get("marca", "")

            if not marca:
                partes = produto_raw.split(" ", 1)
                if len(partes) > 1 and len(partes[0]) <= 20:
                    marca = partes[0]
                    produto_raw = partes[1] if len(partes) > 1 else produto_raw

            unidade = dados.get("unidade_medida", "UN")
            base = dados.get("base_especifica", "")
            dosagem = dados.get("instrucao_dosagem", "")
            lote = dados.get("lote", "")
            data_venc = dados.get("data_vencimento", "")
            if data_venc and len(data_venc) >= 10:
                data_venc = data_venc[:10]
            codigo_interno = dados.get("codigo_interno", "")

            sucesso, msg = criar_produto(
                ean=ean,
                produto=produto_raw,
                marca=marca,
                unidade_medida=unidade,
                base_especifica=base,
                instrucao_dosagem=dosagem,
                lote=lote,
                data_vencimento=data_venc,
                codigo_interno=codigo_interno,
            )
            if sucesso:
                importados += 1
            else:
                if "UNIQUE" not in msg:
                    erros.append(f"Linha {idx} (EAN {ean}): {msg}")

        wb.close()
        resumo = f"{importados} produtos importados"
        if erros:
            resumo += f", {len(erros)} erros ignorados"

        return True, resumo

    except Exception as e:
        return False, f"Erro ao importar: {str(e)}"
