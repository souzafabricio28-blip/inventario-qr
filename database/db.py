from .schema import criar_conexao, get_db
from datetime import datetime
import re


def listar_produtos(search=""):
    conn = criar_conexao()
    cursor = conn.cursor()
    if search:
        cursor.execute(
            """SELECT * FROM produtos
               WHERE ean LIKE ? OR produto LIKE ? OR marca LIKE ?
               ORDER BY produto""",
            (f"%{search}%", f"%{search}%", f"%{search}%"),
        )
    else:
        cursor.execute("SELECT * FROM produtos ORDER BY produto")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_produto(ean):
    """Busca por EAN, código Omie, alias de barras ou código sem pontuação."""
    ean = (ean or "").strip()
    if not ean:
        return None
    candidatos = [ean]
    if ean.endswith(".0"):
        candidatos.append(ean[:-2])
    sem_zeros = ean.lstrip("0")
    if sem_zeros and sem_zeros != ean:
        candidatos.append(sem_zeros)
    limpo = re.sub(r"[^0-9A-Za-z]", "", ean)
    if limpo and limpo not in candidatos:
        candidatos.append(limpo)

    conn = criar_conexao()
    cursor = conn.cursor()
    for cod in candidatos:
        cursor.execute(
            "SELECT * FROM produtos WHERE ean = ? OR codigo_interno = ?",
            (cod, cod),
        )
        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    for cod in candidatos:
        try:
            cursor.execute(
                "SELECT p.* FROM produto_codigos c "
                "JOIN produtos p ON p.ean = c.ean_produto WHERE c.codigo = ?",
                (cod,),
            )
            row = cursor.fetchone()
            if row:
                conn.close()
                return dict(row)
        except Exception:
            break

    limpo_u = re.sub(r"[^0-9A-Za-z]", "", ean).upper()
    if limpo_u:
        cursor.execute("SELECT * FROM produtos")
        for r in cursor.fetchall():
            d = dict(r)
            for campo in (d.get("ean") or "", d.get("codigo_interno") or ""):
                if re.sub(r"[^0-9A-Za-z]", "", str(campo)).upper() == limpo_u:
                    conn.close()
                    return d
    conn.close()
    return None


def vincular_codigo(codigo, ean_produto, origem="bip", sobrescrever=True):
    codigo = (codigo or "").strip()
    ean_produto = (ean_produto or "").strip()
    if not codigo or not ean_produto:
        return False, "Código e produto são obrigatórios"
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute("SELECT ean FROM produtos WHERE ean = ?", (ean_produto,))
    if not cursor.fetchone():
        conn.close()
        return False, "Produto Omie não encontrado"
    try:
        if not sobrescrever:
            # Não deixa a planilha RT apagar uma correção manual já feita
            cursor.execute(
                "SELECT origem FROM produto_codigos WHERE codigo = ?",
                (codigo,),
            )
            existe = cursor.fetchone()
            origens_rt = ("rt_planilha", "rt_oficial")
            if existe:
                if origem in origens_rt and existe["origem"] in origens_rt:
                    cursor.execute(
                        "UPDATE produto_codigos SET ean_produto = ?, origem = ? WHERE codigo = ?",
                        (ean_produto, origem, codigo),
                    )
                    conn.commit()
                    conn.close()
                    return True, f"Código {codigo} vinculado ao produto {ean_produto}"
                conn.close()
                return False, f"Código {codigo} já associado manualmente ao produto (mantido)"
        cursor.execute(
            "INSERT INTO produto_codigos (codigo, ean_produto, origem) VALUES (?, ?, ?) "
            "ON CONFLICT(codigo) DO UPDATE SET ean_produto=excluded.ean_produto, origem=excluded.origem",
            (codigo, ean_produto, origem),
        )
        conn.commit()
        conn.close()
        return True, f"Código {codigo} vinculado ao produto {ean_produto}"
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e)


def buscar_por_vinculo_manual(codigo):
    """Retorna o produto se o código lido tiver uma correção manual (origem bip/edicao).

    Correções manuais têm prioridade sobre a planilha RT: se o usuário vinculou o
    código a um produto, a planilha não pode devolver outro produto para o mesmo código.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    candidatos = [codigo]
    if codigo.endswith(".0"):
        candidatos.append(codigo[:-2])
    sem_zeros = codigo.lstrip("0")
    if sem_zeros and sem_zeros != codigo:
        candidatos.append(sem_zeros)
    conn = criar_conexao()
    try:
        cursor = conn.cursor()
        for c in candidatos:
            cursor.execute(
                "SELECT p.* FROM produto_codigos v "
                "JOIN produtos p ON p.ean = v.ean_produto "
                "WHERE v.codigo = ? AND v.origem NOT IN ('rt_planilha', 'rt_oficial')",
                (c,),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
    finally:
        conn.close()
    return None


def listar_produtos_editados(search=""):
    """Produtos que receberam correção manual (editado_manual=1)."""
    conn = criar_conexao()
    cursor = conn.cursor()
    if search:
        cursor.execute(
            """SELECT * FROM produtos
               WHERE editado_manual = 1
                 AND (ean LIKE ? OR produto LIKE ? OR marca LIKE ?)
               ORDER BY produto""",
            (f"%{search}%", f"%{search}%", f"%{search}%"),
        )
    else:
        cursor.execute(
            "SELECT * FROM produtos WHERE editado_manual = 1 ORDER BY produto"
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def listar_aliases():
    """Todos os vínculos codigo->produto (produto_codigos)."""
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute("SELECT codigo, ean_produto, origem FROM produto_codigos")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def qtd_contagem_sessao(ean, sessao=""):
    conn = criar_conexao()
    cursor = conn.cursor()
    if sessao:
        cursor.execute(
            "SELECT COALESCE(SUM(quantidade_contada), 0) as qtd "
            "FROM inventario_contagem WHERE ean = ? AND sessao = ?",
            (ean, sessao),
        )
    else:
        cursor.execute(
            "SELECT COALESCE(SUM(quantidade_contada), 0) as qtd "
            "FROM inventario_contagem WHERE ean = ?",
            (ean,),
        )
    row = cursor.fetchone()
    conn.close()
    return int(row["qtd"] if hasattr(row, "keys") else row[0])


def loja_da_sessao(nome):
    """Retorna a loja da sessão (ou '' se a sessão não existir)."""
    nome = (nome or "").strip()
    if not nome:
        return ""
    conn = criar_conexao()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT loja FROM sessoes_inventario WHERE nome = ? LIMIT 1",
            (nome,),
        )
        row = cursor.fetchone()
        return row["loja"] if row else ""
    finally:
        conn.close()


def criar_produto(ean, produto, marca="", unidade_medida="UN",
                  base_especifica="", instrucao_dosagem="",
                  lote="", data_vencimento="", codigo_interno="", editado_manual=True):
    conn = criar_conexao()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO produtos (ean, produto, marca, unidade_medida,
               base_especifica, instrucao_dosagem, lote, data_vencimento, codigo_interno, editado_manual)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ean, produto.strip(), marca.strip(), unidade_medida,
             base_especifica.strip(), instrucao_dosagem.strip(),
             lote.strip(), data_vencimento.strip(), codigo_interno.strip(),
             1 if editado_manual else 0),
        )
        conn.commit()
        return True, "Produto cadastrado com sucesso"
    except Exception as e:
        conn.rollback()
        if "UNIQUE" in str(e):
            return False, "EAN já cadastrado"
        return False, str(e)
    finally:
        conn.close()


def atualizar_produto(ean, ean_novo=None, editado_manual=None, **kwargs):
    ean = (ean or "").strip()
    novo_ean = (ean_novo or "").strip() or ean
    campos = []
    valores = []
    for key, val in kwargs.items():
        if val is not None and key in ("produto", "marca", "unidade_medida",
                                       "base_especifica", "instrucao_dosagem",
                                       "lote", "data_vencimento", "codigo_interno"):
            campos.append(f"{key} = ?")
            valores.append(val.strip() if isinstance(val, str) else val)
    if editado_manual is not None:
        campos.append("editado_manual = ?")
        valores.append(1 if editado_manual else 0)
    if not ean or not novo_ean:
        return False, "EAN inválido"

    conn = criar_conexao()
    cursor = conn.cursor()
    try:
        if ean != novo_ean:
            cursor.execute("SELECT ean FROM produtos WHERE ean = ?", (novo_ean,))
            if cursor.fetchone():
                return False, f"Já existe outro produto com o EAN {novo_ean}"
            cursor.execute(
                """INSERT INTO produtos (ean, produto, marca, unidade_medida,
                   base_especifica, instrucao_dosagem, lote, data_vencimento,
                   codigo_interno, quantidade_estoque, editado_manual, created_at, updated_at)
                   SELECT ?, produto, marca, unidade_medida,
                   base_especifica, instrucao_dosagem, lote, data_vencimento,
                   codigo_interno, quantidade_estoque, editado_manual, created_at, CURRENT_TIMESTAMP
                   FROM produtos WHERE ean = ?""",
                (novo_ean, ean),
            )
            if campos:
                campos.append("updated_at = CURRENT_TIMESTAMP")
                cursor.execute(
                    f"UPDATE produtos SET {', '.join(campos)} WHERE ean = ?",
                    valores + [novo_ean],
                )
            for tabela in ("inventario_contagem", "validacoes_base",
                           "saidas_estoque", "itens_recebimento"):
                cursor.execute(
                    f"UPDATE {tabela} SET ean = ? WHERE ean = ?",
                    (novo_ean, ean),
                )
            cursor.execute(
                "UPDATE produto_codigos SET ean_produto = ? WHERE ean_produto = ?",
                (novo_ean, ean),
            )
            cursor.execute("DELETE FROM produtos WHERE ean = ?", (ean,))
            conn.commit()
            msg = f"Produto atualizado (EAN: {ean} → {novo_ean})"
        else:
            if not campos:
                return False, "Nenhum campo para atualizar"
            campos.append("updated_at = CURRENT_TIMESTAMP")
            valores.append(ean)
            cursor.execute(
                f"UPDATE produtos SET {', '.join(campos)} WHERE ean = ?",
                valores,
            )
            conn.commit()
            msg = "Produto atualizado"

        # EAN antigo continua apontando para o produto (etiquetas antigas/planilha RT)
        if ean != novo_ean:
            try:
                vincular_codigo(ean, novo_ean, origem="edicao", sobrescrever=True)
            except Exception:
                pass
        return True, msg
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def registrar_contagem(ean, quantidade=1, sessao="", lote="", data_vencimento="", loja=""):
    if not loja and sessao:
        loja = loja_da_sessao(sessao)
    if not loja:
        loja = "RTJ"
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO inventario_contagem (ean, quantidade_contada, sessao, lote, data_vencimento, loja)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ean, quantidade, sessao, lote, data_vencimento, loja),
    )
    conn.commit()
    conn.close()


def definir_contagem_sessao(ean, quantidade, sessao, lote="", data_vencimento="", loja=""):
    """Define a quantidade total do item na sessão (substitui leituras anteriores)."""
    ean = (ean or "").strip()
    sessao = (sessao or "").strip()
    try:
        quantidade = int(quantidade)
    except (TypeError, ValueError):
        return False, "Quantidade inválida"
    if not ean or not sessao:
        return False, "EAN e sessão são obrigatórios"
    if quantidade < 0:
        return False, "Quantidade não pode ser negativa"

    if not loja:
        loja = loja_da_sessao(sessao) or "RTJ"

    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM inventario_contagem WHERE ean = ? AND sessao = ?",
        (ean, sessao),
    )
    if quantidade > 0:
        cursor.execute(
            """INSERT INTO inventario_contagem (ean, quantidade_contada, sessao, lote, data_vencimento, loja)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ean, quantidade, sessao, lote or "", data_vencimento or "", loja),
        )
    conn.commit()
    conn.close()
    return True, quantidade


def excluir_contagem_sessao(ean, sessao):
    """Remove o item da contagem da sessão."""
    ean = (ean or "").strip()
    sessao = (sessao or "").strip()
    if not ean or not sessao:
        return False, "EAN e sessão são obrigatórios"
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM inventario_contagem WHERE ean = ? AND sessao = ?",
        (ean, sessao),
    )
    removidos = cursor.rowcount
    conn.commit()
    conn.close()
    return True, removidos


def zerar_contagens(sessao="", apagar_sessao=False):
    """
    Zera leituras de inventário.
    sessao vazia = todas as sessões.
    apagar_sessao=True remove também o registro em sessoes_inventario.
    """
    sessao = (sessao or "").strip()
    conn = criar_conexao()
    cursor = conn.cursor()
    if sessao:
        cursor.execute("DELETE FROM inventario_contagem WHERE sessao = ?", (sessao,))
        removidos = cursor.rowcount or 0
        if apagar_sessao:
            cursor.execute("DELETE FROM sessoes_inventario WHERE nome = ?", (sessao,))
    else:
        cursor.execute("DELETE FROM inventario_contagem")
        removidos = cursor.rowcount or 0
        if apagar_sessao:
            cursor.execute("DELETE FROM sessoes_inventario")
    conn.commit()
    conn.close()
    return True, removidos


def aplicar_contagem_como_estoque(sessao, zerar_nao_contados=False, loja=""):
    """
    Grava a contagem da sessão como LOJA FÍSICA da loja (quantidade_loja) em
    estoque_produto. Entradas futuras (NF-e) somam no depósito (quantidade_estoque).
    """
    sessao = (sessao or "").strip()
    if not sessao:
        return False, "Informe a sessão de inventário"

    loja = (loja or "").strip() or loja_da_sessao(sessao) or "RTJ"

    contagens = get_contagens(sessao, cruzar=False)
    itens = [c for c in contagens if int(c.get("total_contado") or 0) > 0]
    if not itens:
        return False, "Nenhum item contado nesta sessão"

    conn = criar_conexao()
    cursor = conn.cursor()
    atualizados = 0
    eans_ok = set()
    for c in itens:
        ean = (c.get("ean") or "").strip()
        qtd = int(c.get("total_contado") or 0)
        if not ean or qtd <= 0:
            continue
        lote = c.get("lote") or ""
        venc = c.get("data_vencimento") or ""
        cursor.execute(
            """INSERT INTO estoque_produto (ean, loja, quantidade_loja, lote, data_vencimento, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(ean, loja) DO UPDATE SET
                   quantidade_loja = excluded.quantidade_loja,
                   lote = CASE WHEN excluded.lote != '' THEN excluded.lote ELSE estoque_produto.lote END,
                   data_vencimento = CASE WHEN excluded.data_vencimento != '' THEN excluded.data_vencimento ELSE estoque_produto.data_vencimento END,
                   updated_at = CURRENT_TIMESTAMP""",
            (ean, loja, qtd, lote, venc),
        )
        atualizados += 1
        eans_ok.add(ean)

    zerados = 0
    if zerar_nao_contados and eans_ok:
        placeholders = ",".join("?" * len(eans_ok))
        cursor.execute(
            f"""UPDATE estoque_produto SET quantidade_loja = 0, quantidade_estoque = 0, updated_at = CURRENT_TIMESTAMP
               WHERE loja = ? AND ean NOT IN ({placeholders})
                 AND (COALESCE(quantidade_loja, 0) > 0 OR COALESCE(quantidade_estoque, 0) > 0)""",
            (loja, *tuple(eans_ok)),
        )
        zerados = cursor.rowcount

    conn.commit()
    conn.close()
    msg = f"Estoque da loja {loja} atualizado: {atualizados} produto(s) com a contagem da sessão '{sessao}'"
    if zerados:
        msg += f"; {zerados} não contados zerados"
    return True, msg

def get_contagens(sessao="", cruzar=False, loja=""):
    """Lista contagens. Se cruzar=True, inclui todo o cadastro (Omie) com qtd 0."""
    loja = (loja or "").strip()
    cols = (
        "p.ean, COALESCE(NULLIF(p.codigo_interno, ''), p.ean) as codigo_omie, "
        "p.codigo_interno, p.produto, p.marca, p.base_especifica, "
        "p.lote, p.data_vencimento, "
        "COALESCE(p.quantidade_estoque, 0) as quantidade_estoque, "
        "COALESCE(SUM(i.quantidade_contada), 0) as total_contado, "
        "MAX(i.data_hora) as ultima_leitura, "
        "MAX(i.loja) as loja"
    )
    group = (
        "p.ean, p.codigo_interno, p.produto, p.marca, p.base_especifica, "
        "p.lote, p.data_vencimento, p.quantidade_estoque"
    )
    conn = criar_conexao()
    cursor = conn.cursor()
    if cruzar:
        if sessao:
            cursor.execute(
                f"SELECT {cols} FROM produtos p "
                f"LEFT JOIN inventario_contagem i ON i.ean = p.ean AND i.sessao = ? "
                f"GROUP BY {group} "
                f"ORDER BY CASE WHEN COALESCE(SUM(i.quantidade_contada), 0) = 0 THEN 1 ELSE 0 END, p.produto",
                (sessao,),
            )
        else:
            if loja:
                cursor.execute(
                    f"SELECT {cols} FROM produtos p "
                    f"LEFT JOIN inventario_contagem i ON i.ean = p.ean AND (i.loja = ? OR i.id IS NULL) "
                    f"GROUP BY {group} "
                    f"ORDER BY CASE WHEN COALESCE(SUM(i.quantidade_contada), 0) = 0 THEN 1 ELSE 0 END, p.produto",
                    (loja,),
                )
            else:
                cursor.execute(
                    f"SELECT {cols} FROM produtos p "
                    f"LEFT JOIN inventario_contagem i ON i.ean = p.ean "
                    f"GROUP BY {group} "
                    f"ORDER BY CASE WHEN COALESCE(SUM(i.quantidade_contada), 0) = 0 THEN 1 ELSE 0 END, p.produto"
                )
    elif sessao:
        cursor.execute(
            f"SELECT {cols} FROM inventario_contagem i "
            f"JOIN produtos p ON i.ean = p.ean "
            f"WHERE i.sessao = ? "
            f"GROUP BY {group} ORDER BY total_contado DESC",
            (sessao,),
        )
    else:
        filter_sql = ""
        params = ()
        if loja:
            filter_sql = " WHERE i.loja = ?"
            params = (loja,)
        cursor.execute(
            f"SELECT {cols} FROM inventario_contagem i "
            f"JOIN produtos p ON i.ean = p.ean "
            f"{filter_sql} "
            f"GROUP BY {group} ORDER BY total_contado DESC",
            params,
        )
    rows = cursor.fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    fallback_loja = loja or (loja_da_sessao(sessao) if sessao else "") or "RTJ"
    if sessao and not cruzar:
        loja_sessao = loja_da_sessao(sessao)
        for r in result:
            r["loja"] = loja_sessao
    for r in result:
        r["total_contado"] = int(r.get("total_contado") or 0)
        r["loja"] = r.get("loja") or fallback_loja
        r["status"] = "contado" if r["total_contado"] > 0 else "pendente"

    # Estoque por loja: cada linha usa o estoque da sua loja (sessão ou filtro)
    pares = list({(r["ean"], r["loja"] or "RTJ") for r in result})
    estoques = {}
    if pares:
        conn = criar_conexao()
        try:
            where = " OR ".join("(ean = ? AND loja = ?)" for _ in pares)
            params = [x for p in pares for x in p]
            rows_ep = conn.execute(
                f"SELECT ean, loja, quantidade_loja, quantidade_estoque FROM estoque_produto WHERE {where}",
                params,
            ).fetchall()
            for r in rows_ep:
                estoques[(r["ean"], r["loja"])] = (r["quantidade_loja"] or 0) + (r["quantidade_estoque"] or 0)
        finally:
            conn.close()
    for r in result:
        r["quantidade_estoque"] = int(float(estoques.get((r["ean"], r["loja"] or "RTJ"), 0) or 0))
    return result


def criar_sessao(nome, loja="RTJ"):
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessoes_inventario (nome, loja) VALUES (?, ?)", (nome, loja or "RTJ"),
    )
    conn.commit()
    sessao_id = cursor.lastrowid
    conn.close()
    return sessao_id


def fechar_sessao(sessao_id=None, nome=None):
    """Encerra sessão por id ou por nome. Retorna True se alguma linha foi atualizada."""
    conn = criar_conexao()
    cursor = conn.cursor()
    if nome:
        cursor.execute(
            """UPDATE sessoes_inventario
               SET status = 'fechada', data_fechamento = CURRENT_TIMESTAMP
               WHERE nome = ? AND status = 'aberta'""",
            (nome,),
        )
    elif sessao_id is not None:
        cursor.execute(
            """UPDATE sessoes_inventario
               SET status = 'fechada', data_fechamento = CURRENT_TIMESTAMP
               WHERE id = ? AND status = 'aberta'""",
            (sessao_id,),
        )
    else:
        conn.close()
        return False
    alteradas = cursor.rowcount or 0
    conn.commit()
    conn.close()
    return alteradas > 0


def fechar_sessoes_abertas():
    """Encerra todas as sessões com status aberta. Retorna quantidade encerrada."""
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE sessoes_inventario
           SET status = 'fechada', data_fechamento = CURRENT_TIMESTAMP
           WHERE status = 'aberta'"""
    )
    alteradas = cursor.rowcount or 0
    conn.commit()
    conn.close()
    return alteradas


def sessao_esta_aberta(nome):
    """True se a sessão existe e está aberta. Sessão vazia = livre (sem bloqueio)."""
    if not (nome or "").strip():
        return True
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM sessoes_inventario WHERE nome = ? LIMIT 1",
        (nome.strip(),),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return True
    return row["status"] == "aberta"


def sessao_mais_ativa(loja=""):
    """Sessão com leitura mais recente (aberta ou ainda sem registro formal)."""
    loja = (loja or "").strip()
    conn = criar_conexao()
    cursor = conn.cursor()
    where_loja = "AND i.loja = ?" if loja else ""
    params = (loja,) if loja else ()
    cursor.execute(
        f"""SELECT i.sessao AS nome, MAX(i.loja) AS loja
           FROM inventario_contagem i
           LEFT JOIN sessoes_inventario s ON s.nome = i.sessao
           WHERE COALESCE(i.sessao, '') != ''
             {where_loja}
             AND (s.status = 'aberta' OR s.id IS NULL)
           GROUP BY i.sessao
           ORDER BY MAX(i.data_hora) DESC
           LIMIT 1""",
        params,
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return ""
    return row["nome"] or ""


def listar_sessoes(loja=""):
    loja = (loja or "").strip()
    conn = criar_conexao()
    cursor = conn.cursor()
    if loja:
        cursor.execute(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM inventario_contagem
                       WHERE sessao = s.nome) as total_itens
               FROM sessoes_inventario s
               WHERE s.loja = ?
               ORDER BY data_abertura DESC""",
            (loja,),
        )
    else:
        cursor.execute(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM inventario_contagem
                       WHERE sessao = s.nome) as total_itens
               FROM sessoes_inventario s
               ORDER BY data_abertura DESC"""
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def registrar_validacao(ean, base_informada, base_oficial):
    conn = criar_conexao()
    cursor = conn.cursor()
    status = "aprovada" if base_informada.upper() == base_oficial.upper() else "bloqueada"
    cursor.execute(
        """INSERT INTO validacoes_base (ean, base_informada, base_oficial, status)
           VALUES (?, ?, ?, ?)""",
        (ean, base_informada, base_oficial, status),
    )
    conn.commit()
    conn.close()
    return status


def get_ultima_validacao(ean):
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM validacoes_base
           WHERE ean = ?
           ORDER BY data_hora DESC LIMIT 1""",
        (ean,),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# ── Dashboard ─────────────────────────────────────────────

def get_dashboard_stats():
    with get_db() as conn:
        cursor = conn.cursor()
        from datetime import datetime, timedelta
        hoje = datetime.now().strftime("%Y-%m-%d")
        limite30 = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        cursor.execute("SELECT COUNT(*) FROM produtos")
        total_produtos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM sessoes_inventario WHERE status='aberta'")
        sessoes_abertas = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM produtos WHERE data_vencimento != '' AND data_vencimento < ?", (hoje,))
        vencidos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM produtos WHERE data_vencimento BETWEEN ? AND ?", (hoje, limite30))
        vencendo_30 = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM inventario_contagem")
        total_contagens = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM validacoes_base WHERE status='bloqueada'")
        bloqueios = cursor.fetchone()[0]

        cursor.execute("""SELECT p.ean, p.produto, p.marca, p.data_vencimento
           FROM produtos p WHERE p.data_vencimento != '' AND p.data_vencimento < ?
           ORDER BY p.data_vencimento LIMIT 5""", (hoje,))
        expirados = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""SELECT p.ean, p.produto, p.marca, p.data_vencimento
           FROM produtos p WHERE p.data_vencimento BETWEEN ? AND ?
           ORDER BY p.data_vencimento LIMIT 5""", (hoje, limite30))
        expirando = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""SELECT i.data_hora, i.ean, p.produto
           FROM inventario_contagem i JOIN produtos p ON i.ean=p.ean
           ORDER BY i.data_hora DESC LIMIT 10""")
        recentes = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""SELECT * FROM validacoes_base WHERE status='bloqueada'
           ORDER BY data_hora DESC LIMIT 5""")
        validacoes_bloqueadas = [dict(r) for r in cursor.fetchall()]

        return {
            "total_produtos": total_produtos,
            "sessoes_abertas": sessoes_abertas,
            "vencidos": vencidos,
            "vencendo_30": vencendo_30,
            "total_contagens": total_contagens,
            "bloqueios": bloqueios,
            "expirados": expirados,
            "expirando": expirando,
            "recentes": recentes,
            "validacoes_bloqueadas": validacoes_bloqueadas,
        }


# ── Produtos ───────────────────────────────────────────────

def excluir_produto_completo(ean):
    with get_db() as conn:
        conn.execute("DELETE FROM inventario_contagem WHERE ean=?", (ean,))
        conn.execute("DELETE FROM validacoes_base WHERE ean=?", (ean,))
        conn.execute("DELETE FROM estoque_produto WHERE ean=?", (ean,))
        conn.execute("DELETE FROM produtos WHERE ean=?", (ean,))
        conn.commit()


# ── Validações ─────────────────────────────────────────────

def listar_validacoes(limit=200):
    with get_db() as conn:
        rows = conn.execute("""SELECT v.*, p.produto, p.marca FROM validacoes_base v
           LEFT JOIN produtos p ON v.ean=p.ean ORDER BY v.data_hora DESC LIMIT ?""",
           (limit,)).fetchall()
        return [dict(r) for r in rows]


# ── Config ─────────────────────────────────────────────────

def get_all_config():
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY, valor TEXT DEFAULT '')""")
        conn.commit()
        rows = conn.execute("SELECT chave, valor FROM config").fetchall()
        return {r[0]: r[1] for r in rows}


def save_config(data):
    with get_db() as conn:
        for k, v in data.items():
            conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", (k, str(v)))
        conn.commit()


# ── Vencimentos ────────────────────────────────────────────

def get_vencimentos():
    with get_db() as conn:
        from datetime import datetime, timedelta
        hoje = datetime.now().strftime("%Y-%m-%d")
        limite30 = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        limite90 = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

        vencidos = [dict(r) for r in conn.execute("""SELECT * FROM produtos WHERE data_vencimento != ''
           AND data_vencimento < ? ORDER BY data_vencimento""", (hoje,)).fetchall()]

        vencendo30 = [dict(r) for r in conn.execute("""SELECT * FROM produtos WHERE data_vencimento BETWEEN ? AND ?
           ORDER BY data_vencimento""", (hoje, limite30)).fetchall()]

        vencendo90 = [dict(r) for r in conn.execute("""SELECT * FROM produtos WHERE data_vencimento BETWEEN ? AND ?
           ORDER BY data_vencimento""", (limite30, limite90)).fetchall()]

        ok = [dict(r) for r in conn.execute("""SELECT * FROM produtos WHERE data_vencimento > ?
           OR data_vencimento = '' ORDER BY produto""", (limite90,)).fetchall()]

        return {"vencidos": vencidos, "vencendo_30": vencendo30,
                "vencendo_90": vencendo90, "ok": ok}


# ── NF-e / Recebimento ────────────────────────────────────

def listar_recebimentos():
    with get_db() as conn:
        rows = conn.execute("""SELECT * FROM recebimentos_nf WHERE excluido=0
           ORDER BY data_recebimento DESC LIMIT 50""").fetchall()
        return [dict(r) for r in rows]


def get_recebimento(rec_id):
    with get_db() as conn:
        rec = conn.execute("SELECT * FROM recebimentos_nf WHERE id=?", (rec_id,)).fetchone()
        if not rec:
            return None
        rec = dict(rec)
        itens = conn.execute("SELECT * FROM itens_recebimento WHERE recebimento_id=? ORDER BY id",
            (rec_id,)).fetchall()
        rec["itens"] = [dict(r) for r in itens]
        return rec


def criar_recebimento_nf(chave_acesso, numero, serie, fornecedor, cnpj_fornecedor,
                          data_emissao, itens, loja="RTJ"):
    loja = _normalizar_loja(loja)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO recebimentos_nf (chave_acesso, numero, serie, fornecedor,
               cnpj_fornecedor, data_emissao, total_itens, loja)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (chave_acesso, numero, serie, fornecedor, cnpj_fornecedor,
             data_emissao, len(itens), loja),
        )
        rec_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for item in itens:
            conn.execute(
                """INSERT INTO itens_recebimento (recebimento_id, ean, codigo_produto,
                   descricao, ncm, unidade, quantidade_esperada, lote, data_vencimento)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec_id, item.get("ean", ""), item.get("codigo_produto", ""),
                 item["descricao"], item.get("ncm", ""),
                 item.get("unidade", "UN"), item["quantidade_esperada"],
                 item.get("lote", ""), item.get("data_vencimento", "")),
            )

        conn.commit()
        return rec_id


def verificar_chave_nfe(chave_acesso):
    with get_db() as conn:
        row = conn.execute("SELECT id, numero FROM recebimentos_nf WHERE chave_acesso=?",
            (chave_acesso,)).fetchone()
        return dict(row) if row else None


def get_item_recebimento(rec_id, ean):
    with get_db() as conn:
        row = conn.execute(
            """SELECT lote, data_vencimento, descricao FROM itens_recebimento
               WHERE recebimento_id=? AND (ean=? OR codigo_produto=?)
               LIMIT 1""",
            (rec_id, ean, ean),
        ).fetchone()
        return dict(row) if row else None


def conferir_item_recebimento(rec_id, ean, quantidade, lote, data_venc):
    with get_db() as conn:
        item = conn.execute(
            """SELECT * FROM itens_recebimento
               WHERE recebimento_id=? AND (ean=? OR codigo_produto=?)
               AND quantidade_recebida < quantidade_esperada
               ORDER BY id LIMIT 1""",
            (rec_id, ean, ean),
        ).fetchone()

        if not item:
            return None

        item = dict(item)
        qtd_input = int(quantidade)
        nova_qtd = min(item["quantidade_recebida"] + qtd_input, item["quantidade_esperada"])
        conn.execute(
            """UPDATE itens_recebimento SET quantidade_recebida=?, lote=?, data_vencimento=?
               WHERE id=?""",
            (nova_qtd, lote, data_venc, item["id"]),
        )

        total_itens = conn.execute(
            "SELECT COUNT(*) FROM itens_recebimento WHERE recebimento_id=?",
            (rec_id,)).fetchone()[0]
        total_receb = conn.execute(
            "SELECT SUM(quantidade_recebida) FROM itens_recebimento WHERE recebimento_id=?",
            (rec_id,)).fetchone()[0]
        total_esper = conn.execute(
            "SELECT SUM(quantidade_esperada) FROM itens_recebimento WHERE recebimento_id=?",
            (rec_id,)).fetchone()[0]

        conn.execute("UPDATE recebimentos_nf SET itens_recebidos=? WHERE id=?",
            (int(total_receb or 0), rec_id))
        conn.commit()

        completo = total_receb >= total_esper if total_esper else False
        return {
            "item": item,
            "recebido_ate_agora": nova_qtd,
            "total_esperado": item["quantidade_esperada"],
            "progresso": f"{int(total_receb or 0)}/{int(total_esper or 0)}",
            "completo": completo,
        }


def finalizar_recebimento(rec_id, loja=None):
    with get_db() as conn:
        row = conn.execute("SELECT loja FROM recebimentos_nf WHERE id=?", (rec_id,)).fetchone()
        loja = _normalizar_loja(loja or (row["loja"] if row else "") or "RTJ")
        itens = [dict(r) for r in conn.execute(
            "SELECT * FROM itens_recebimento WHERE recebimento_id=?", (rec_id,)).fetchall()]

        divergencias = []
        for item in itens:
            if item["quantidade_recebida"] < item["quantidade_esperada"]:
                divergencias.append({
                    "descricao": item["descricao"],
                    "esperado": item["quantidade_esperada"],
                    "recebido": item["quantidade_recebida"],
                    "faltando": item["quantidade_esperada"] - item["quantidade_recebida"],
                })

        for item in itens:
            if item["quantidade_recebida"] > 0:
                ean = item.get("ean", "") or item.get("codigo_produto", "")
                if ean:
                    conn.execute(
                        """INSERT INTO estoque_produto (ean, loja, quantidade_estoque, lote, data_vencimento, updated_at)
                           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                           ON CONFLICT(ean, loja) DO UPDATE SET
                               quantidade_estoque = estoque_produto.quantidade_estoque + excluded.quantidade_estoque,
                               lote = CASE WHEN excluded.lote != '' THEN excluded.lote ELSE estoque_produto.lote END,
                               data_vencimento = CASE WHEN excluded.data_vencimento != '' THEN excluded.data_vencimento ELSE estoque_produto.data_vencimento END,
                               updated_at = CURRENT_TIMESTAMP""",
                        (ean, loja, item["quantidade_recebida"],
                         item["lote"] or "", item["data_vencimento"] or ""),
                    )

        conn.execute(
            "UPDATE recebimentos_nf SET status='finalizado', finalizado_em=CURRENT_TIMESTAMP WHERE id=?",
            (rec_id,),
        )
        conn.commit()

        return {"divergencias": divergencias, "total_divergencias": len(divergencias), "itens": itens}


def excluir_recebimento(rec_id):
    with get_db() as conn:
        conn.execute("UPDATE recebimentos_nf SET excluido=1 WHERE id=?", (rec_id,))
        conn.commit()


def get_etiquetas_nfe(rec_id):
    with get_db() as conn:
        itens = [dict(r) for r in conn.execute(
            """SELECT * FROM itens_recebimento WHERE recebimento_id=? AND quantidade_recebida > 0""",
            (rec_id,)).fetchall()]
        return itens


# ── Estoque ────────────────────────────────────────────────

def _normalizar_loja(loja=""):
    return (loja or "").strip() or "RTJ"


def get_estoque(ean, loja=""):
    """Retorna o saldo/lote/validade do produto na loja (ou None). Inclui 'total'. """
    loja = _normalizar_loja(loja)
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM estoque_produto WHERE ean=? AND loja=? LIMIT 1",
            (ean, loja),
        ).fetchone()
        if row is None:
            return None
        res = dict(row)
        res["total"] = float(res.get("quantidade_loja") or 0) + float(res.get("quantidade_estoque") or 0)
        return res


def set_estoque(ean, quantidade, loja="", lote="", data_vencimento=""):
    """Define (substitui) o saldo do DEPÓSITO do produto na loja. Upsert em estoque_produto."""
    loja = _normalizar_loja(loja)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO estoque_produto (ean, loja, quantidade_estoque, lote, data_vencimento, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(ean, loja) DO UPDATE SET
                   quantidade_estoque = excluded.quantidade_estoque,
                   lote = CASE WHEN excluded.lote != '' THEN excluded.lote ELSE estoque_produto.lote END,
                   data_vencimento = CASE WHEN excluded.data_vencimento != '' THEN excluded.data_vencimento ELSE estoque_produto.data_vencimento END,
                   updated_at = CURRENT_TIMESTAMP""",
            (ean, loja, quantidade, lote, data_vencimento),
        )
        conn.commit()


def mover_estoque(ean, loja="", quantidade=0):
    """Move unidades entre depósito e loja física.
    quantidade > 0: depósito -> loja física; quantidade < 0: loja física -> depósito.
    Retorna (ok, mensagem)."""
    loja = _normalizar_loja(loja)
    try:
        quantidade = float(quantidade or 0)
    except (TypeError, ValueError):
        return False, "Quantidade inválida"
    if quantidade == 0:
        return False, "Informe uma quantidade para mover"
    with get_db() as conn:
        row = conn.execute(
            "SELECT quantidade_loja, quantidade_estoque FROM estoque_produto WHERE ean=? AND loja=?",
            (ean, loja),
        ).fetchone()
        if row is None:
            return False, "Produto sem registro de estoque nesta loja"
        ql = float(row["quantidade_loja"] or 0)
        qe = float(row["quantidade_estoque"] or 0)
        if quantidade > 0:
            if qe < quantidade:
                return False, f"Depósito insuficiente (tem {qe:.0f} un.)"
            ql += quantidade
            qe -= quantidade
            msg = f"Movido {quantidade:.0f} un. do depósito para a loja física"
        else:
            q = -quantidade
            if ql < q:
                return False, f"Loja física insuficiente (tem {ql:.0f} un.)"
            ql -= q
            qe += q
            msg = f"Movido {q:.0f} un. da loja física para o depósito"
        conn.execute(
            "UPDATE estoque_produto SET quantidade_loja=?, quantidade_estoque=?, updated_at=CURRENT_TIMESTAMP WHERE ean=? AND loja=?",
            (ql, qe, ean, loja),
        )
        conn.commit()
    return True, msg


def listar_estoque(search="", loja=""):
    with get_db() as conn:
        loja = _normalizar_loja(loja)
        cols = "p.ean, COALESCE(p.produto, ep.ean) as produto, p.marca," \
               " COALESCE(ep.quantidade_loja, 0) as quantidade_loja," \
               " ep.quantidade_estoque," \
               " (COALESCE(ep.quantidade_loja, 0) + COALESCE(ep.quantidade_estoque, 0)) as total," \
               " ep.lote, ep.data_vencimento, p.base_especifica"
        if search:
            rows = conn.execute(f"""
                SELECT {cols}
                FROM estoque_produto ep LEFT JOIN produtos p ON p.ean = ep.ean
                WHERE ep.loja = ?
                  AND (COALESCE(ep.quantidade_loja, 0) + COALESCE(ep.quantidade_estoque, 0)) > 0
                  AND (ep.ean LIKE ? OR COALESCE(p.produto, '') LIKE ?)
                ORDER BY total DESC LIMIT 200
            """, (loja, f"%{search}%", f"%{search}%")).fetchall()
        else:
            rows = conn.execute(f"""
                SELECT {cols}
                FROM estoque_produto ep LEFT JOIN produtos p ON p.ean = ep.ean
                WHERE ep.loja = ?
                  AND (COALESCE(ep.quantidade_loja, 0) + COALESCE(ep.quantidade_estoque, 0)) > 0
                ORDER BY total DESC LIMIT 200
            """, (loja,)).fetchall()
        return [dict(r) for r in rows]


def listar_estoque_zerados(search="", loja=""):
    with get_db() as conn:
        loja = _normalizar_loja(loja)
        cols = "p.ean, COALESCE(p.produto, p.ean) as produto," \
               " COALESCE(ep.quantidade_loja, 0) as quantidade_loja," \
               " COALESCE(ep.quantidade_estoque, 0) as quantidade_estoque," \
               " (COALESCE(ep.quantidade_loja, 0) + COALESCE(ep.quantidade_estoque, 0)) as total"
        if search:
            rows = conn.execute(f"""
                SELECT {cols}
                FROM produtos p LEFT JOIN estoque_produto ep ON ep.ean = p.ean AND ep.loja = ?
                WHERE (COALESCE(ep.quantidade_loja, 0) + COALESCE(ep.quantidade_estoque, 0)) <= 0
                  AND (p.ean LIKE ? OR p.produto LIKE ?)
                ORDER BY produto LIMIT 200
            """, (loja, f"%{search}%", f"%{search}%")).fetchall()
        else:
            rows = conn.execute(f"""
                SELECT {cols}
                FROM produtos p LEFT JOIN estoque_produto ep ON ep.ean = p.ean AND ep.loja = ?
                WHERE (COALESCE(ep.quantidade_loja, 0) + COALESCE(ep.quantidade_estoque, 0)) <= 0
                ORDER BY produto LIMIT 200
            """, (loja,)).fetchall()
        return [dict(r) for r in rows]


def zerar_estoque_geral(limpar_lote=False, loja=""):
    """Zera o estoque da loja. Retorna (ok, qtd_afetados)."""
    loja = _normalizar_loja(loja)
    conn = criar_conexao()
    cursor = conn.cursor()
    if limpar_lote:
        cursor.execute("""
            UPDATE estoque_produto SET
               quantidade_loja = 0,
               quantidade_estoque = 0,
               lote = '',
               data_vencimento = '',
               updated_at = CURRENT_TIMESTAMP
            WHERE loja = ?
               AND (COALESCE(quantidade_loja, 0) <> 0
                    OR COALESCE(quantidade_estoque, 0) <> 0
                    OR COALESCE(lote, '') <> ''
                    OR COALESCE(data_vencimento, '') <> '')""",
            (loja,))
    else:
        cursor.execute("""
            UPDATE estoque_produto SET quantidade_loja = 0, quantidade_estoque = 0, updated_at = CURRENT_TIMESTAMP
            WHERE loja = ?
               AND (COALESCE(quantidade_loja, 0) <> 0 OR COALESCE(quantidade_estoque, 0) <> 0)""",
            (loja,))
    afetados = cursor.rowcount or 0
    conn.commit()
    conn.close()
    return True, afetados


# ── Saídas ─────────────────────────────────────────────────

def listar_saidas():
    with get_db() as conn:
        rows = conn.execute("""SELECT s.*, p.produto as produto_nome
            FROM saidas_estoque s LEFT JOIN produtos p ON s.ean=p.ean
            ORDER BY s.data_saida DESC LIMIT 100""").fetchall()
        return [dict(r) for r in rows]


def registrar_saida(ean, produto, quantidade, lote, data_vencimento, motivo, observacao, loja=""):
    loja = _normalizar_loja(loja)
    with get_db() as conn:
        conn.execute("""INSERT INTO saidas_estoque (ean, produto, quantidade, lote, data_vencimento, motivo, observacao, loja)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ean, produto, quantidade, lote, data_vencimento, motivo, observacao, loja))
        row = conn.execute(
            "SELECT quantidade_loja, quantidade_estoque FROM estoque_produto WHERE ean=? AND loja=?",
            (ean, loja),
        ).fetchone()
        if row is not None:
            ql = float(row["quantidade_loja"] or 0)
            qe = float(row["quantidade_estoque"] or 0)
            ded = float(quantidade or 0)
            if ql >= ded:
                conn.execute(
                    "UPDATE estoque_produto SET quantidade_loja = quantidade_loja - ?, updated_at = CURRENT_TIMESTAMP WHERE ean=? AND loja=?",
                    (ded, ean, loja),
                )
            else:
                conn.execute(
                    "UPDATE estoque_produto SET quantidade_loja = 0, updated_at = CURRENT_TIMESTAMP WHERE ean=? AND loja=?",
                    (ean, loja),
                )
                restante = ded - ql
                conn.execute(
                    "UPDATE estoque_produto SET quantidade_estoque = MAX(0, quantidade_estoque - ?), updated_at = CURRENT_TIMESTAMP WHERE ean=? AND loja=?",
                    (restante, ean, loja),
                )
        else:
            conn.execute(
                """INSERT OR IGNORE INTO estoque_produto (ean, loja, quantidade_loja, quantidade_estoque)
                   VALUES (?, ?, 0, 0)""",
                (ean, loja),
            )
        conn.commit()
