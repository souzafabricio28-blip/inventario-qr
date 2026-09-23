import re
from .schema_pg import criar_conexao, get_db
from datetime import datetime

import psycopg2
import psycopg2.extras


def _exec(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def listar_produtos(search=""):
    with get_db() as conn:
        if search:
            cur = _exec(conn,
                """SELECT * FROM produtos
                   WHERE ean ILIKE %s OR produto ILIKE %s OR marca ILIKE %s
                   ORDER BY produto""",
                (f"%{search}%", f"%{search}%", f"%{search}%"),
            )
        else:
            cur = _exec(conn, "SELECT * FROM produtos ORDER BY produto")
        return [dict(r) for r in cur.fetchall()]


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

    with get_db() as conn:
        for cod in candidatos:
            cur = _exec(conn,
                "SELECT * FROM produtos WHERE ean = %s OR codigo_interno = %s",
                (cod, cod))
            row = cur.fetchone()
            if row:
                return dict(row)

        for cod in candidatos:
            try:
                cur = _exec(conn,
                    "SELECT p.* FROM produto_codigos c "
                    "JOIN produtos p ON p.ean = c.ean_produto "
                    "WHERE c.codigo = %s",
                    (cod,))
                row = cur.fetchone()
                if row:
                    return dict(row)
            except Exception:
                conn.rollback()
                break

        limpo_u = re.sub(r"[^0-9A-Za-z]", "", ean).upper()
        if not limpo_u:
            return None
        cur = _exec(conn,
            "SELECT * FROM produtos WHERE "
            "regexp_replace(upper(ean), '[^0-9A-Z]', '', 'g') = %s "
            "OR regexp_replace(upper(COALESCE(codigo_interno,'')), '[^0-9A-Z]', '', 'g') = %s "
            "LIMIT 1",
            (limpo_u, limpo_u))
        row = cur.fetchone()
        if row:
            return dict(row)
    return None


def vincular_codigo(codigo, ean_produto, origem="bip"):
    """Associa um código de barras (GTIN) a um produto Omie (ean)."""
    codigo = (codigo or "").strip()
    ean_produto = (ean_produto or "").strip()
    if not codigo or not ean_produto:
        return False, "Código e produto são obrigatórios"
    with get_db() as conn:
        cur = _exec(conn, "SELECT ean FROM produtos WHERE ean = %s", (ean_produto,))
        if not cur.fetchone():
            return False, "Produto Omie não encontrado"
        try:
            _exec(conn,
                "INSERT INTO produto_codigos (codigo, ean_produto, origem) VALUES (%s, %s, %s) "
                "ON CONFLICT (codigo) DO UPDATE SET ean_produto = EXCLUDED.ean_produto, origem = EXCLUDED.origem",
                (codigo, ean_produto, origem))
            conn.commit()
            return True, f"Código {codigo} vinculado ao produto {ean_produto}"
        except Exception as e:
            conn.rollback()
            return False, str(e)


def qtd_contagem_sessao(ean, sessao=""):
    with get_db() as conn:
        if sessao:
            cur = _exec(conn,
                "SELECT COALESCE(SUM(quantidade_contada), 0) as qtd "
                "FROM inventario_contagem WHERE ean = %s AND sessao = %s",
                (ean, sessao))
        else:
            cur = _exec(conn,
                "SELECT COALESCE(SUM(quantidade_contada), 0) as qtd "
                "FROM inventario_contagem WHERE ean = %s",
                (ean,))
        row = cur.fetchone()
    return int(row["qtd"] if hasattr(row, "keys") else row[0])


def criar_produto(ean, produto, marca="", unidade_medida="UN",
                  base_especifica="", instrucao_dosagem="",
                  lote="", data_vencimento="", codigo_interno=""):
    with get_db() as conn:
        try:
            _exec(conn,
                """INSERT INTO produtos (ean, produto, marca, unidade_medida,
                   base_especifica, instrucao_dosagem, lote, data_vencimento, codigo_interno)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (ean, produto.strip(), marca.strip(), unidade_medida,
                 base_especifica.strip(), instrucao_dosagem.strip(),
                 lote.strip(), data_vencimento.strip(), codigo_interno.strip()),
            )
            conn.commit()
            return True, "Produto cadastrado com sucesso"
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return False, "EAN já cadastrado (UNIQUE)"
        except Exception as e:
            conn.rollback()
            return False, str(e)


def atualizar_produto(ean, **kwargs):
    campos = []
    valores = []
    for key, val in kwargs.items():
        if val is not None and key in ("produto", "marca", "unidade_medida",
                                       "base_especifica", "instrucao_dosagem",
                                       "lote", "data_vencimento", "codigo_interno"):
            campos.append(f"{key} = %s")
            valores.append(val.strip() if isinstance(val, str) else val)
    if not campos:
        return False, "Nenhum campo para atualizar"
    campos.append("updated_at = CURRENT_TIMESTAMP")
    valores.append(ean)
    with get_db() as conn:
        try:
            _exec(conn, f"UPDATE produtos SET {', '.join(campos)} WHERE ean = %s", valores)
            conn.commit()
            return True, "Produto atualizado"
        except Exception as e:
            conn.rollback()
            return False, str(e)


def registrar_contagem(ean, quantidade=1, sessao="", lote="", data_vencimento=""):
    with get_db() as conn:
        _exec(conn,
            """INSERT INTO inventario_contagem (ean, quantidade_contada, sessao, lote, data_vencimento)
               VALUES (%s, %s, %s, %s, %s)""",
            (ean, quantidade, sessao, lote, data_vencimento))
        conn.commit()


def definir_contagem_sessao(ean, quantidade, sessao, lote="", data_vencimento=""):
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

    with get_db() as conn:
        _exec(conn,
            "DELETE FROM inventario_contagem WHERE ean = %s AND sessao = %s",
            (ean, sessao))
        if quantidade > 0:
            _exec(conn,
                """INSERT INTO inventario_contagem (ean, quantidade_contada, sessao, lote, data_vencimento)
                   VALUES (%s, %s, %s, %s, %s)""",
                (ean, quantidade, sessao, lote or "", data_vencimento or ""))
        conn.commit()
    return True, quantidade


def excluir_contagem_sessao(ean, sessao):
    """Remove o item da contagem da sessão."""
    ean = (ean or "").strip()
    sessao = (sessao or "").strip()
    if not ean or not sessao:
        return False, "EAN e sessão são obrigatórios"
    with get_db() as conn:
        cur = _exec(conn,
            "DELETE FROM inventario_contagem WHERE ean = %s AND sessao = %s",
            (ean, sessao))
        removidos = cur.rowcount
        conn.commit()
    return True, removidos


def get_contagens(sessao="", cruzar=False):
    """Lista contagens. Se cruzar=True, inclui todo o cadastro (Omie) com qtd 0."""
    cols = (
        "p.ean, COALESCE(NULLIF(p.codigo_interno, ''), p.ean) as codigo_omie, "
        "p.codigo_interno, p.produto, p.marca, p.base_especifica, "
        "p.lote, p.data_vencimento, "
        "COALESCE(p.quantidade_estoque, 0) as quantidade_estoque, "
        "COALESCE(SUM(i.quantidade_contada), 0) as total_contado, "
        "MAX(i.data_hora) as ultima_leitura"
    )
    group = (
        "p.ean, p.codigo_interno, p.produto, p.marca, p.base_especifica, "
        "p.lote, p.data_vencimento, p.quantidade_estoque"
    )
    with get_db() as conn:
        if cruzar:
            if sessao:
                cur = _exec(conn,
                    f"SELECT {cols} FROM produtos p "
                    f"LEFT JOIN inventario_contagem i ON i.ean = p.ean AND i.sessao = %s "
                    f"GROUP BY {group} "
                    f"ORDER BY CASE WHEN COALESCE(SUM(i.quantidade_contada), 0) = 0 THEN 1 ELSE 0 END, p.produto",
                    (sessao,))
            else:
                cur = _exec(conn,
                    f"SELECT {cols} FROM produtos p "
                    f"LEFT JOIN inventario_contagem i ON i.ean = p.ean "
                    f"GROUP BY {group} "
                    f"ORDER BY CASE WHEN COALESCE(SUM(i.quantidade_contada), 0) = 0 THEN 1 ELSE 0 END, p.produto")
        elif sessao:
            cur = _exec(conn,
                f"SELECT {cols} FROM inventario_contagem i "
                f"JOIN produtos p ON i.ean = p.ean "
                f"WHERE i.sessao = %s "
                f"GROUP BY {group} ORDER BY COALESCE(SUM(i.quantidade_contada), 0) DESC",
                (sessao,))
        else:
            cur = _exec(conn,
                f"SELECT {cols} FROM inventario_contagem i "
                f"JOIN produtos p ON i.ean = p.ean "
                f"GROUP BY {group} ORDER BY COALESCE(SUM(i.quantidade_contada), 0) DESC")
        result = [dict(r) for r in cur.fetchall()]
    for r in result:
        r["total_contado"] = int(r.get("total_contado") or 0)
        r["status"] = "contado" if r["total_contado"] > 0 else "pendente"
    return result


def criar_sessao(nome):
    with get_db() as conn:
        cur = _exec(conn, "INSERT INTO sessoes_inventario (nome) VALUES (%s) RETURNING id", (nome,))
        conn.commit()
        return cur.fetchone()["id"]


def fechar_sessao(sessao_id):
    with get_db() as conn:
        _exec(conn,
            """UPDATE sessoes_inventario
               SET status = 'fechada', data_fechamento = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (sessao_id,))
        conn.commit()


def listar_sessoes():
    with get_db() as conn:
        cur = _exec(conn,
            """SELECT s.*,
                      (SELECT COUNT(*) FROM inventario_contagem
                       WHERE sessao = s.nome) as total_itens
               FROM sessoes_inventario s
               ORDER BY data_abertura DESC""")
        return [dict(r) for r in cur.fetchall()]


def registrar_validacao(ean, base_informada, base_oficial):
    status = "aprovada" if base_informada.upper() == base_oficial.upper() else "bloqueada"
    with get_db() as conn:
        _exec(conn,
            """INSERT INTO validacoes_base (ean, base_informada, base_oficial, status)
               VALUES (%s, %s, %s, %s)""",
            (ean, base_informada, base_oficial, status))
        conn.commit()
    return status


def get_ultima_validacao(ean):
    with get_db() as conn:
        cur = _exec(conn,
            """SELECT * FROM validacoes_base
               WHERE ean = %s
               ORDER BY data_hora DESC LIMIT 1""",
            (ean,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_dashboard_stats():
    with get_db() as conn:
        from datetime import datetime, timedelta
        hoje = datetime.now().strftime("%Y-%m-%d")
        limite30 = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        total_produtos = _exec(conn, "SELECT COUNT(*) FROM produtos").fetchone()[0]
        sessoes_abertas = _exec(conn, "SELECT COUNT(*) FROM sessoes_inventario WHERE status='aberta'").fetchone()[0]
        vencidos = _exec(conn, "SELECT COUNT(*) FROM produtos WHERE data_vencimento != '' AND data_vencimento < %s", (hoje,)).fetchone()[0]
        vencendo_30 = _exec(conn, "SELECT COUNT(*) FROM produtos WHERE data_vencimento BETWEEN %s AND %s", (hoje, limite30)).fetchone()[0]
        total_contagens = _exec(conn, "SELECT COUNT(*) FROM inventario_contagem").fetchone()[0]
        bloqueios = _exec(conn, "SELECT COUNT(*) FROM validacoes_base WHERE status='bloqueada'").fetchone()[0]

        expirados = [dict(r) for r in _exec(conn,
            """SELECT p.ean, p.produto, p.marca, p.data_vencimento
               FROM produtos p WHERE p.data_vencimento != '' AND p.data_vencimento < %s
               ORDER BY p.data_vencimento LIMIT 5""", (hoje,)).fetchall()]

        expirando = [dict(r) for r in _exec(conn,
            """SELECT p.ean, p.produto, p.marca, p.data_vencimento
               FROM produtos p WHERE p.data_vencimento BETWEEN %s AND %s
               ORDER BY p.data_vencimento LIMIT 5""", (hoje, limite30)).fetchall()]

        recentes = [dict(r) for r in _exec(conn,
            """SELECT i.data_hora, i.ean, p.produto
               FROM inventario_contagem i JOIN produtos p ON i.ean=p.ean
               ORDER BY i.data_hora DESC LIMIT 10""").fetchall()]

        validacoes_bloqueadas = [dict(r) for r in _exec(conn,
            """SELECT * FROM validacoes_base WHERE status='bloqueada'
               ORDER BY data_hora DESC LIMIT 5""").fetchall()]

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


def excluir_produto_completo(ean):
    with get_db() as conn:
        _exec(conn, "DELETE FROM inventario_contagem WHERE ean=%s", (ean,))
        _exec(conn, "DELETE FROM validacoes_base WHERE ean=%s", (ean,))
        _exec(conn, "DELETE FROM produtos WHERE ean=%s", (ean,))
        conn.commit()


def listar_validacoes(limit=200):
    with get_db() as conn:
        cur = _exec(conn, """SELECT v.*, p.produto, p.marca FROM validacoes_base v
           LEFT JOIN produtos p ON v.ean=p.ean ORDER BY v.data_hora DESC LIMIT %s""",
           (limit,))
        return [dict(r) for r in cur.fetchall()]


def get_all_config():
    with get_db() as conn:
        cur = _exec(conn, "SELECT chave, valor FROM config")
        return {r[0]: r[1] for r in cur.fetchall()}


def save_config(data):
    with get_db() as conn:
        for k, v in data.items():
            _exec(conn,
                """INSERT INTO config (chave, valor) VALUES (%s, %s)
                   ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor""",
                (k, str(v)))
        conn.commit()


def get_vencimentos():
    with get_db() as conn:
        from datetime import datetime, timedelta
        hoje = datetime.now().strftime("%Y-%m-%d")
        limite30 = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        limite90 = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

        vencidos = [dict(r) for r in _exec(conn, """SELECT * FROM produtos WHERE data_vencimento != ''
           AND data_vencimento < %s ORDER BY data_vencimento""", (hoje,)).fetchall()]

        vencendo30 = [dict(r) for r in _exec(conn, """SELECT * FROM produtos WHERE data_vencimento BETWEEN %s AND %s
           ORDER BY data_vencimento""", (hoje, limite30)).fetchall()]

        vencendo90 = [dict(r) for r in _exec(conn, """SELECT * FROM produtos WHERE data_vencimento BETWEEN %s AND %s
           ORDER BY data_vencimento""", (limite30, limite90)).fetchall()]

        ok = [dict(r) for r in _exec(conn, """SELECT * FROM produtos WHERE data_vencimento > %s
           OR data_vencimento = '' ORDER BY produto""", (limite90,)).fetchall()]

        return {"vencidos": vencidos, "vencendo_30": vencendo30,
                "vencendo_90": vencendo90, "ok": ok}


def listar_recebimentos():
    with get_db() as conn:
        cur = _exec(conn, """SELECT * FROM recebimentos_nf WHERE excluido=0
           ORDER BY data_recebimento DESC LIMIT 50""")
        return [dict(r) for r in cur.fetchall()]


def get_recebimento(rec_id):
    with get_db() as conn:
        rec = _exec(conn, "SELECT * FROM recebimentos_nf WHERE id=%s", (rec_id,)).fetchone()
        if not rec:
            return None
        rec = dict(rec)
        itens = _exec(conn, "SELECT * FROM itens_recebimento WHERE recebimento_id=%s ORDER BY id",
            (rec_id,)).fetchall()
        rec["itens"] = [dict(r) for r in itens]
        return rec


def criar_recebimento_nf(chave_acesso, numero, serie, fornecedor, cnpj_fornecedor,
                          data_emissao, itens):
    with get_db() as conn:
        cur = _exec(conn,
            """INSERT INTO recebimentos_nf (chave_acesso, numero, serie, fornecedor,
               cnpj_fornecedor, data_emissao, total_itens)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (chave_acesso, numero, serie, fornecedor, cnpj_fornecedor,
             data_emissao, len(itens)))
        rec_id = cur.fetchone()["id"]

        for item in itens:
            _exec(conn,
                """INSERT INTO itens_recebimento (recebimento_id, ean, codigo_produto,
                   descricao, ncm, unidade, quantidade_esperada, lote, data_vencimento)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (rec_id, item.get("ean", ""), item.get("codigo_produto", ""),
                 item["descricao"], item.get("ncm", ""),
                 item.get("unidade", "UN"), item["quantidade_esperada"],
                 item.get("lote", ""), item.get("data_vencimento", "")),
            )

        conn.commit()
        return rec_id


def verificar_chave_nfe(chave_acesso):
    with get_db() as conn:
        row = _exec(conn, "SELECT id, numero FROM recebimentos_nf WHERE chave_acesso=%s",
            (chave_acesso,)).fetchone()
        return dict(row) if row else None


def get_item_recebimento(rec_id, ean):
    with get_db() as conn:
        row = _exec(conn,
            """SELECT lote, data_vencimento, descricao FROM itens_recebimento
               WHERE recebimento_id=%s AND (ean=%s OR codigo_produto=%s)
               LIMIT 1""",
            (rec_id, ean, ean),
        ).fetchone()
        return dict(row) if row else None


def conferir_item_recebimento(rec_id, ean, quantidade, lote, data_venc):
    with get_db() as conn:
        item = _exec(conn,
            """SELECT * FROM itens_recebimento
               WHERE recebimento_id=%s AND (ean=%s OR codigo_produto=%s)
               AND quantidade_recebida < quantidade_esperada
               ORDER BY id LIMIT 1""",
            (rec_id, ean, ean),
        ).fetchone()

        if not item:
            return None

        item = dict(item)
        qtd_input = int(quantidade)
        nova_qtd = min(item["quantidade_recebida"] + qtd_input, item["quantidade_esperada"])
        _exec(conn,
            """UPDATE itens_recebimento SET quantidade_recebida=%s, lote=%s, data_vencimento=%s
               WHERE id=%s""",
            (nova_qtd, lote, data_venc, item["id"]),
        )

        total_itens = _exec(conn,
            "SELECT COUNT(*) FROM itens_recebimento WHERE recebimento_id=%s",
            (rec_id,)).fetchone()[0]
        total_receb = _exec(conn,
            "SELECT SUM(quantidade_recebida) FROM itens_recebimento WHERE recebimento_id=%s",
            (rec_id,)).fetchone()[0]
        total_esper = _exec(conn,
            "SELECT SUM(quantidade_esperada) FROM itens_recebimento WHERE recebimento_id=%s",
            (rec_id,)).fetchone()[0]

        _exec(conn, "UPDATE recebimentos_nf SET itens_recebidos=%s WHERE id=%s",
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
        itens = [dict(r) for r in _exec(conn,
            "SELECT * FROM itens_recebimento WHERE recebimento_id=%s", (rec_id,)).fetchall()]

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
                    _exec(conn,
                        """UPDATE produtos SET lote=%s, data_vencimento=%s,
                           quantidade_estoque = COALESCE(quantidade_estoque,0) + %s,
                           updated_at=CURRENT_TIMESTAMP
                           WHERE ean=%s""",
                        (item["lote"] or "", item["data_vencimento"] or "",
                         item["quantidade_recebida"], ean),
                    )

        _exec(conn,
            "UPDATE recebimentos_nf SET status='finalizado', finalizado_em=CURRENT_TIMESTAMP WHERE id=%s",
            (rec_id,),
        )
        conn.commit()

        return {"divergencias": divergencias, "total_divergencias": len(divergencias), "itens": itens}


def excluir_recebimento(rec_id):
    with get_db() as conn:
        _exec(conn, "UPDATE recebimentos_nf SET excluido=1 WHERE id=%s", (rec_id,))
        conn.commit()


def get_etiquetas_nfe(rec_id):
    with get_db() as conn:
        itens = [dict(r) for r in _exec(conn,
            """SELECT * FROM itens_recebimento WHERE recebimento_id=%s AND quantidade_recebida > 0""",
            (rec_id,)).fetchall()]
        return itens


def listar_estoque(search=""):
    with get_db() as conn:
        if search:
            rows = _exec(conn, """
                SELECT ean, produto, marca, quantidade_estoque, lote, data_vencimento, base_especifica
                FROM produtos
                WHERE quantidade_estoque > 0 AND (ean ILIKE %s OR produto ILIKE %s)
                ORDER BY quantidade_estoque DESC LIMIT 200
            """, (f"%{search}%", f"%{search}%")).fetchall()
        else:
            rows = _exec(conn, """
                SELECT ean, produto, marca, quantidade_estoque, lote, data_vencimento, base_especifica
                FROM produtos
                WHERE quantidade_estoque > 0
                ORDER BY quantidade_estoque DESC LIMIT 200
            """).fetchall()
        return [dict(r) for r in rows]


def listar_estoque_zerados():
    with get_db() as conn:
        rows = _exec(conn, """
            SELECT ean, produto, quantidade_estoque FROM produtos
            WHERE quantidade_estoque IS NULL OR quantidade_estoque <= 0
            ORDER BY produto LIMIT 200
        """).fetchall()
        return [dict(r) for r in rows]


def listar_saidas():
    with get_db() as conn:
        rows = _exec(conn, """SELECT s.*, p.produto as produto_nome
            FROM saidas_estoque s LEFT JOIN produtos p ON s.ean=p.ean
            ORDER BY s.data_saida DESC LIMIT 100""").fetchall()
        return [dict(r) for r in rows]


def registrar_saida(ean, produto, quantidade, lote, data_vencimento, motivo, observacao):
    with get_db() as conn:
        _exec(conn, """INSERT INTO saidas_estoque (ean, produto, quantidade, lote, data_vencimento, motivo, observacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (ean, produto, quantidade, lote, data_vencimento, motivo, observacao))
        _exec(conn, """UPDATE produtos SET quantidade_estoque = GREATEST(0, COALESCE(quantidade_estoque,0) - %s)
            WHERE ean=%s""", (quantidade, ean))
        conn.commit()


# ── Usuários ────────────────────────────────────────────────

from werkzeug.security import generate_password_hash, check_password_hash


def criar_usuario(usuario, senha, nome=""):
    with get_db() as conn:
        try:
            _exec(conn,
                "INSERT INTO usuarios (usuario, senha_hash, nome) VALUES (%s, %s, %s)",
                (usuario.strip().lower(), generate_password_hash(senha), nome.strip()),
            )
            conn.commit()
            return True, "Usuário cadastrado com sucesso"
        except psycopg2.errors.UniqueViolation:
            return False, "Usuário já existe"


def buscar_usuario(usuario):
    with get_db() as conn:
        cur = _exec(conn, "SELECT * FROM usuarios WHERE usuario = %s AND ativo = 1",
                    (usuario.strip().lower(),))
        row = cur.fetchone()
        return dict(row) if row else None


def verificar_senha(usuario, senha):
    user = buscar_usuario(usuario)
    if user and check_password_hash(user["senha_hash"], senha):
        return user
    return None


def listar_usuarios():
    with get_db() as conn:
        cur = _exec(conn, "SELECT id, usuario, nome, ativo, created_at FROM usuarios ORDER BY usuario")
        return [dict(r) for r in cur.fetchall()]


def excluir_usuario(usuario):
    with get_db() as conn:
        _exec(conn, "UPDATE usuarios SET ativo = 0 WHERE usuario = %s", (usuario.strip().lower(),))
        conn.commit()


def redefinir_senha(usuario, nova_senha):
    with get_db() as conn:
        _exec(conn, "UPDATE usuarios SET senha_hash = %s WHERE usuario = %s AND ativo = 1",
              (generate_password_hash(nova_senha), usuario.strip().lower()))
        conn.commit()
        return True, "Senha redefinida com sucesso"