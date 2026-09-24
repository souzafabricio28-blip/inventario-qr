import os

PG_ATIVO = bool(os.environ.get("DATABASE_URL"))

if PG_ATIVO:
    from .schema_pg import criar_conexao, criar_tabelas, get_db, get_db_path, DB_PATH
    from .db_pg import (
        listar_produtos as _listar_produtos_db,
        buscar_produto as _buscar_produto_db,
        criar_produto, atualizar_produto,
        registrar_contagem, get_contagens, criar_sessao, listar_sessoes,
        excluir_produto_completo, get_dashboard_stats as _get_dashboard_stats_db,
        listar_validacoes,
        get_all_config, save_config, get_vencimentos,
        listar_recebimentos, get_recebimento, criar_recebimento_nf,
        verificar_chave_nfe, get_item_recebimento, conferir_item_recebimento,
        finalizar_recebimento, excluir_recebimento, get_etiquetas_nfe,
        listar_estoque, listar_estoque_zerados, get_estoque, set_estoque, mover_estoque,
        listar_saidas, registrar_saida,
        zerar_estoque_geral,
        fechar_sessao, fechar_sessoes_abertas, sessao_esta_aberta, registrar_validacao, get_ultima_validacao,
        qtd_contagem_sessao, vincular_codigo,
        buscar_por_vinculo_manual, listar_produtos_editados, listar_aliases,
        definir_contagem_sessao, excluir_contagem_sessao,
        aplicar_contagem_como_estoque, zerar_contagens,
        sessao_mais_ativa, loja_da_sessao,
    )
else:
    from .schema import criar_conexao, criar_tabelas, get_db, get_db_path, DB_PATH
    from .db import (
        listar_produtos as _listar_produtos_db,
        buscar_produto as _buscar_produto_db,
        criar_produto, atualizar_produto,
        registrar_contagem, get_contagens, criar_sessao, listar_sessoes,
        excluir_produto_completo, get_dashboard_stats as _get_dashboard_stats_db,
        listar_validacoes,
        get_all_config, save_config, get_vencimentos,
        listar_recebimentos, get_recebimento, criar_recebimento_nf,
        verificar_chave_nfe, get_item_recebimento, conferir_item_recebimento,
        finalizar_recebimento, excluir_recebimento, get_etiquetas_nfe,
        listar_estoque, listar_estoque_zerados, get_estoque, set_estoque, mover_estoque,
        listar_saidas, registrar_saida,
        zerar_estoque_geral,
        fechar_sessao, fechar_sessoes_abertas, sessao_esta_aberta, registrar_validacao, get_ultima_validacao,
        qtd_contagem_sessao, vincular_codigo,
        buscar_por_vinculo_manual, listar_produtos_editados, listar_aliases,
        definir_contagem_sessao, excluir_contagem_sessao,
        aplicar_contagem_como_estoque, zerar_contagens,
        sessao_mais_ativa, loja_da_sessao,
    )


def _garantir_produto_planilha(item):
    """Garante espelho no banco (para contagem/FK) a partir da planilha RT."""
    from .rt_lista import item_para_produto
    p = item_para_produto(item)
    ean = p["ean"]
    omie = p["codigo_interno"]

    existente = _buscar_produto_db(ean)
    if not existente or (existente.get("ean") or "") != ean:
        ok, msg = criar_produto(
            ean=ean,
            produto=p["produto"],
            marca=p["marca"],
            codigo_interno=omie,
        )
        if ok or "UNIQUE" in (msg or "").upper():
            if not ok:
                atualizar_produto(ean, produto=p["produto"], marca=p["marca"], codigo_interno=omie)
            existente = _buscar_produto_db(ean)
        else:
            # fallback: produto antigo com omie como PK
            for chave in (omie, item.get("codigo")):
                if chave:
                    existente = _buscar_produto_db(chave)
                    if existente:
                        break
    else:
        # Correção manual prevalece sobre a planilha: não sobrescreve o que o usuário editou
        if not (existente.get("editado_manual") if existente else False) and (
            (existente.get("produto") or "") != p["produto"]
            or (existente.get("marca") or "") != p["marca"]
            or (existente.get("codigo_interno") or "") != omie
        ):
            atualizar_produto(
                ean,
                produto=p["produto"],
                marca=p["marca"],
                codigo_interno=omie,
            )
            existente = _buscar_produto_db(ean) or existente

    if not existente:
        return None

    ean_db = existente["ean"]
    for alias in (ean, omie, item.get("codigo"), item.get("ean"), item.get("codigo_omie")):
        if alias and alias != ean_db:
            try:
                vincular_codigo(alias, ean_db, origem="rt_oficial", sobrescrever=False)
            except Exception:
                pass
    out = dict(existente)
    out["produto"] = p["produto"]
    out["marca"] = p["marca"]
    out["codigo_interno"] = omie
    out["fonte"] = "rt_oficial"
    return out


def listar_produtos(search=""):
    """Catálogo oficial = planilha RT. Fallback para o banco se a planilha falhar.

    Correções manuais (editado_manual=1) prevalecem sobre a planilha na listagem.
    """
    from .rt_lista import carregar_lista_rt, listar_como_produtos, status_lista_rt
    ok, _ = carregar_lista_rt(force=False)
    st = status_lista_rt()
    if ok and (st.get("total") or 0) > 0:
        lista = listar_como_produtos(search)
        try:
            editados = listar_produtos_editados("")
            aliases = listar_aliases()
            alias_por_produto = {}
            for a in aliases:
                alias_por_produto.setdefault(a.get("ean_produto") or "", []).append(
                    a.get("codigo") or "")
            mapa = {}
            for ep in editados:
                ean_ep = ep.get("ean")
                if not ean_ep:
                    continue
                mapa[ean_ep] = ep
                for a in alias_por_produto.get(ean_ep, []):
                    mapa[a] = ep
            if mapa:
                for p in lista:
                    o = mapa.get(p.get("ean")) or mapa.get(p.get("codigo_interno") or "")
                    if o:
                        for k, v in o.items():
                            if k == "id":
                                continue
                            p[k] = v
                        p["fonte"] = "correcao_manual"
        except Exception:
            pass
        return lista
    return _listar_produtos_db(search)


def get_dashboard_stats():
    """Dashboard: total de produtos = lista RT oficial (não o banco legado)."""
    from .rt_lista import carregar_lista_rt, status_lista_rt

    stats = _get_dashboard_stats_db()
    ok, _ = carregar_lista_rt(force=False)
    st = status_lista_rt()
    total_rt = int(st.get("total") or 0) if ok else 0
    if total_rt > 0:
        stats["total_produtos"] = total_rt
        stats["fonte_produtos"] = "rt_oficial"
    else:
        stats["fonte_produtos"] = "banco"
    return stats


def buscar_produto(ean, _force_manual_first=True):
    """Busca primeiro na planilha RT (ean / codigo_omie); espelha no banco.

    Produtos com correção manual (editado_manual=1) têm prioridade sobre a planilha.
    """
    from .rt_lista import carregar_lista_rt, resolver_na_planilha
    db_prod = _buscar_produto_db(ean)
    if db_prod and bool(db_prod.get("editado_manual")):
        return db_prod
    carregar_lista_rt(force=False)
    item = resolver_na_planilha(ean)
    if item:
        prod = _garantir_produto_planilha(item)
        if prod:
            return prod
    return db_prod
