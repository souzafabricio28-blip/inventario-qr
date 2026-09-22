import os

PG_ATIVO = bool(os.environ.get("DATABASE_URL"))

if PG_ATIVO:
    from .schema_pg import criar_conexao, criar_tabelas, get_db, get_db_path, DB_PATH
    from .db_pg import (
        listar_produtos, buscar_produto, criar_produto, atualizar_produto,
        registrar_contagem, get_contagens, criar_sessao, listar_sessoes,
        excluir_produto_completo, get_dashboard_stats, listar_validacoes,
        get_all_config, save_config, get_vencimentos,
        listar_recebimentos, get_recebimento, criar_recebimento_nf,
        verificar_chave_nfe, get_item_recebimento, conferir_item_recebimento,
        finalizar_recebimento, excluir_recebimento, get_etiquetas_nfe,
        listar_estoque, listar_estoque_zerados, listar_saidas, registrar_saida,
        fechar_sessao, registrar_validacao, get_ultima_validacao,
        qtd_contagem_sessao,
    )
else:
    from .schema import criar_conexao, criar_tabelas, get_db, get_db_path, DB_PATH
    from .db import (
        listar_produtos, buscar_produto, criar_produto, atualizar_produto,
        registrar_contagem, get_contagens, criar_sessao, listar_sessoes,
        excluir_produto_completo, get_dashboard_stats, listar_validacoes,
        get_all_config, save_config, get_vencimentos,
        listar_recebimentos, get_recebimento, criar_recebimento_nf,
        verificar_chave_nfe, get_item_recebimento, conferir_item_recebimento,
        finalizar_recebimento, excluir_recebimento, get_etiquetas_nfe,
        listar_estoque, listar_estoque_zerados, listar_saidas, registrar_saida,
        fechar_sessao, registrar_validacao, get_ultima_validacao,
        qtd_contagem_sessao,
    )