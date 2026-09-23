from database.backend import buscar_produto, registrar_validacao


def validar_base(ean, base_informada):
    produto = buscar_produto(ean)
    if not produto:
        return {
            "status": "erro",
            "mensagem": "Produto não encontrado",
            "produto": None,
        }

    base_oficial = produto.get("base_especifica", "")
    if not base_oficial:
        return {
            "status": "aviso",
            "mensagem": "Produto sem base específica cadastrada. Liberação manual necessária.",
            "produto": produto,
            "base_oficial": "",
        }

    status_db = registrar_validacao(ean, base_informada, base_oficial)

    if status_db == "bloqueada":
        return {
            "status": "bloqueada",
            "mensagem": (
                f"BLOQUEADO! Base informada '{base_informada}' não confere "
                f"com a base oficial '{base_oficial}'."
            ),
            "produto": produto,
            "base_oficial": base_oficial,
            "base_informada": base_informada,
        }
    else:
        return {
            "status": "aprovada",
            "mensagem": (
                f"APROVADO! Base '{base_oficial}' confirmada. "
                f"Liberação autorizada."
            ),
            "produto": produto,
            "base_oficial": base_oficial,
        }


def validar_dosagem(ean, quantidade_informada):
    produto = buscar_produto(ean)
    if not produto:
        return {"status": "erro", "mensagem": "Produto não encontrado"}

    instrucao = produto.get("instrucao_dosagem", "")
    if not instrucao:
        return {
            "status": "aviso",
            "mensagem": "Sem instrução de dosagem cadastrada.",
            "produto": produto,
        }

    return {
        "status": "info",
        "mensagem": f"Dosagem padrão: {instrucao}",
        "produto": produto,
        "instrucao": instrucao,
        "quantidade_informada": quantidade_informada,
    }
