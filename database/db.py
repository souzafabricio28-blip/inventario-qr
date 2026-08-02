from .schema import criar_conexao, get_db
from datetime import datetime


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
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM produtos WHERE ean = ?", (ean,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def criar_produto(ean, produto, marca="", unidade_medida="UN",
                  base_especifica="", instrucao_dosagem="",
                  lote="", data_vencimento="", codigo_interno=""):
    conn = criar_conexao()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO produtos (ean, produto, marca, unidade_medida,
               base_especifica, instrucao_dosagem, lote, data_vencimento, codigo_interno)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ean, produto.strip(), marca.strip(), unidade_medida,
             base_especifica.strip(), instrucao_dosagem.strip(),
             lote.strip(), data_vencimento.strip(), codigo_interno.strip()),
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


def atualizar_produto(ean, **kwargs):
    conn = criar_conexao()
    cursor = conn.cursor()
    campos = []
    valores = []
    for key, val in kwargs.items():
        if val is not None and key in ("produto", "marca", "unidade_medida",
                                       "base_especifica", "instrucao_dosagem",
                                       "lote", "data_vencimento", "codigo_interno"):
            campos.append(f"{key} = ?")
            valores.append(val.strip() if isinstance(val, str) else val)
    if not campos:
        conn.close()
        return False, "Nenhum campo para atualizar"
    campos.append("updated_at = CURRENT_TIMESTAMP")
    valores.append(ean)
    try:
        cursor.execute(
            f"UPDATE produtos SET {', '.join(campos)} WHERE ean = ?",
            valores,
        )
        conn.commit()
        conn.close()
        return True, "Produto atualizado"
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e)


def registrar_contagem(ean, quantidade=1, sessao="", lote="", data_vencimento=""):
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO inventario_contagem (ean, quantidade_contada, sessao, lote, data_vencimento)
           VALUES (?, ?, ?, ?, ?)""",
        (ean, quantidade, sessao, lote, data_vencimento),
    )
    conn.commit()
    conn.close()


def get_contagens(sessao=""):
    conn = criar_conexao()
    cursor = conn.cursor()
    if sessao:
        cursor.execute(
            """SELECT p.ean, p.produto, p.marca, p.base_especifica,
                      p.lote, p.data_vencimento,
                      COUNT(i.id) as total_contado,
                      MAX(i.data_hora) as ultima_leitura
               FROM inventario_contagem i
               JOIN produtos p ON i.ean = p.ean
               WHERE i.sessao = ?
               GROUP BY i.ean
               ORDER BY total_contado DESC""",
            (sessao,),
        )
    else:
        cursor.execute(
            """SELECT p.ean, p.produto, p.marca, p.base_especifica,
                      p.lote, p.data_vencimento,
                      COUNT(i.id) as total_contado,
                      MAX(i.data_hora) as ultima_leitura
               FROM inventario_contagem i
               JOIN produtos p ON i.ean = p.ean
               GROUP BY i.ean
               ORDER BY total_contado DESC"""
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def criar_sessao(nome):
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessoes_inventario (nome) VALUES (?)", (nome,)
    )
    conn.commit()
    sessao_id = cursor.lastrowid
    conn.close()
    return sessao_id


def fechar_sessao(sessao_id):
    conn = criar_conexao()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE sessoes_inventario
           SET status = 'fechada', data_fechamento = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (sessao_id,),
    )
    conn.commit()
    conn.close()


def listar_sessoes():
    conn = criar_conexao()
    cursor = conn.cursor()
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
                          data_emissao, itens):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO recebimentos_nf (chave_acesso, numero, serie, fornecedor,
               cnpj_fornecedor, data_emissao, total_itens)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (chave_acesso, numero, serie, fornecedor, cnpj_fornecedor,
             data_emissao, len(itens)),
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


def finalizar_recebimento(rec_id):
    with get_db() as conn:
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
                        """UPDATE produtos SET lote=?, data_vencimento=?,
                           quantidade_estoque = COALESCE(quantidade_estoque,0) + ?,
                           updated_at=CURRENT_TIMESTAMP
                           WHERE ean=?""",
                        (item["lote"] or "", item["data_vencimento"] or "",
                         item["quantidade_recebida"], ean),
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

def listar_estoque(search=""):
    with get_db() as conn:
        if search:
            rows = conn.execute("""
                SELECT ean, produto, marca, quantidade_estoque, lote, data_vencimento, base_especifica
                FROM produtos
                WHERE quantidade_estoque > 0 AND (ean LIKE ? OR produto LIKE ?)
                ORDER BY quantidade_estoque DESC LIMIT 200
            """, (f"%{search}%", f"%{search}%")).fetchall()
        else:
            rows = conn.execute("""
                SELECT ean, produto, marca, quantidade_estoque, lote, data_vencimento, base_especifica
                FROM produtos
                WHERE quantidade_estoque > 0
                ORDER BY quantidade_estoque DESC LIMIT 200
            """).fetchall()
        return [dict(r) for r in rows]


def listar_estoque_zerados():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT ean, produto, quantidade_estoque FROM produtos
            WHERE quantidade_estoque IS NULL OR quantidade_estoque <= 0
            ORDER BY produto LIMIT 200
        """).fetchall()
        return [dict(r) for r in rows]


# ── Saídas ─────────────────────────────────────────────────

def listar_saidas():
    with get_db() as conn:
        rows = conn.execute("""SELECT s.*, p.produto as produto_nome
            FROM saidas_estoque s LEFT JOIN produtos p ON s.ean=p.ean
            ORDER BY s.data_saida DESC LIMIT 100""").fetchall()
        return [dict(r) for r in rows]


def registrar_saida(ean, produto, quantidade, lote, data_vencimento, motivo, observacao):
    with get_db() as conn:
        conn.execute("""INSERT INTO saidas_estoque (ean, produto, quantidade, lote, data_vencimento, motivo, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ean, produto, quantidade, lote, data_vencimento, motivo, observacao))
        conn.execute("""UPDATE produtos SET quantidade_estoque = MAX(0, COALESCE(quantidade_estoque,0) - ?)
            WHERE ean=?""", (quantidade, ean))
        conn.commit()
