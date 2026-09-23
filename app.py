import sys, os, json, io, shutil
from datetime import datetime, timedelta
from functools import wraps
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from flask import (Flask, render_template, request, jsonify, session,
                   send_file, Response, redirect)
from database.backend import PG_ATIVO
from database.backend import (
    criar_tabelas, get_db, criar_conexao, DB_PATH,
    listar_produtos, buscar_produto, criar_produto, atualizar_produto,
    registrar_contagem, get_contagens, criar_sessao, listar_sessoes,
    excluir_produto_completo, get_dashboard_stats, listar_validacoes,
    get_all_config, save_config, get_vencimentos,
    listar_recebimentos, get_recebimento, criar_recebimento_nf,
    verificar_chave_nfe, get_item_recebimento, conferir_item_recebimento,
    finalizar_recebimento, excluir_recebimento, get_etiquetas_nfe,
    listar_estoque, listar_estoque_zerados, listar_saidas, registrar_saida,
    qtd_contagem_sessao, vincular_codigo,
)
from database.import_excel import importar_excel, sincronizar_omie, sincronizar_rt_oficial, caminho_lista_rt_oficial
from qrcode_gen.generator import gerar_qrcode_base64, gerar_qrcode
from validation.base_validator import validar_base
from nfe_parser.parser import parse_nfe_xml
from utils.helpers import parse_codigo_lido
from database.db_pg import verificar_senha, criar_usuario, listar_usuarios, excluir_usuario, redefinir_senha

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "inventario-qr-secret-key")

_upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
try:
    os.makedirs(_upload_dir, exist_ok=True)
    probe = os.path.join(_upload_dir, ".write_test")
    open(probe, "w").close()
    os.remove(probe)
    app.config["UPLOAD_FOLDER"] = _upload_dir
except OSError:
    import tempfile
    app.config["UPLOAD_FOLDER"] = os.path.join(tempfile.gettempdir(), "inventario_uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"sucesso": False, "msg": "Não autenticado"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


def api_handler(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            app.logger.error(f"Erro em {request.path}: {str(e)}")
            return jsonify({"sucesso": False, "msg": str(e)}), 500
    return wrapper


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"sucesso": False, "msg": "Recurso não encontrado"}), 404
    return e


# ── Autenticação ────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def pagina_login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        user = verificar_senha(usuario, senha)
        if user:
            session["usuario"] = user["usuario"]
            session["nome"] = user["nome"]
            session.permanent = True
            return redirect("/")
        return render_template("login.html", erro="Usuário ou senha inválidos")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ── Dashboard ──────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("dashboard.html")


@app.route("/api/dashboard")
@login_required
@api_handler
def api_dashboard():
    return jsonify(get_dashboard_stats())


# ── Produtos ───────────────────────────────────────────────

@app.route("/api/produtos/vincular-codigo", methods=["POST"])
@login_required
@api_handler
def api_vincular_codigo():
    data = request.json or {}
    codigo = (data.get("codigo") or "").strip()
    ean_produto = (data.get("ean_produto") or data.get("ean") or "").strip()
    ok, msg = vincular_codigo(codigo, ean_produto, origem="bip")
    if not ok:
        return jsonify({"sucesso": False, "msg": msg}), 400
    # já conta +1 na sessão atual
    sessao = data.get("sessao") or session.get("sessao_atual", "")
    produto = buscar_produto(codigo)
    if produto and sessao:
        registrar_contagem(produto["ean"], quantidade=1, sessao=sessao)
        qtd = qtd_contagem_sessao(produto["ean"], sessao)
        return jsonify({
            "sucesso": True, "msg": msg, "encontrado": True,
            "produto": produto,
            "codigo_omie": produto.get("codigo_interno") or produto["ean"],
            "qtd_sessao": qtd, "incremento": 1,
        })
    return jsonify({"sucesso": True, "msg": msg})


@app.route("/api/produtos")
@login_required
@api_handler
def api_listar_produtos():
    return jsonify(listar_produtos(request.args.get("search", "")))


@app.route("/api/produtos/<ean>")
@login_required
@api_handler
def api_buscar_produto(ean):
    produto = buscar_produto(ean)
    if not produto:
        return jsonify({"erro": "Produto não encontrado"}), 404
    produto["qrcode"] = gerar_qrcode_base64(
            ean=produto["ean"], produto=produto.get("produto", ""),
            marca=produto.get("marca", ""),
            unidade=produto.get("unidade_medida", ""),
            base=produto.get("base_especifica", ""),
            dosagem=produto.get("instrucao_dosagem", ""),
            lote=produto.get("lote", ""),
            data_vencimento=produto.get("data_vencimento", ""),
            codigo_interno=produto.get("codigo_interno", ""),
        )
    return jsonify(produto)


@app.route("/api/produtos", methods=["POST"])
@login_required
@api_handler
def api_criar_produto():
    data = request.json
    ean = data.get("ean", "").strip()
    if not ean:
        return jsonify({"sucesso": False, "msg": "EAN é obrigatório"}), 400
    sucesso, msg = criar_produto(
        ean=ean, produto=data.get("produto", ""),
        marca=data.get("marca", ""),
        unidade_medida=data.get("unidade_medida", "UN"),
        base_especifica=data.get("base_especifica", ""),
        instrucao_dosagem=data.get("instrucao_dosagem", ""),
        lote=data.get("lote", ""),
        data_vencimento=data.get("data_vencimento", ""),
        codigo_interno=data.get("codigo_interno", ""),
    )
    return jsonify({"sucesso": sucesso, "msg": msg})


@app.route("/api/produtos/<ean>", methods=["PUT"])
@login_required
@api_handler
def api_atualizar_produto(ean):
    data = request.json
    sucesso, msg = atualizar_produto(ean, **{
        k: v for k, v in data.items()
        if k in ("produto", "marca", "unidade_medida", "base_especifica",
                 "instrucao_dosagem", "lote", "data_vencimento", "codigo_interno")
    })
    return jsonify({"sucesso": sucesso, "msg": msg})


@app.route("/api/produtos/<ean>", methods=["DELETE"])
@login_required
@api_handler
def api_excluir_produto(ean):
    excluir_produto_completo(ean)
    return jsonify({"sucesso": True, "msg": "Produto excluído"})


@app.route("/produtos")
@login_required
def pagina_produtos():
    return render_template("produtos.html")

# ── Scanner ────────────────────────────────────────────────

def _garantir_produto_rt(item_rt):
    """Garante produto no banco a partir da linha da planilha RT (ean + codigo_omie)."""
    ean = (item_rt.get("ean") or "").strip()
    omie = (item_rt.get("codigo_omie") or item_rt.get("codigo") or "").strip()
    desc = (item_rt.get("descricao") or ean or omie).strip()
    if not ean and not omie:
        return None

    # Preferir achar por ean da planilha, depois omie
    produto = None
    for chave in (ean, omie, item_rt.get("codigo")):
        if chave:
            produto = buscar_produto(chave)
            if produto:
                break

    marca = ""
    nome = desc
    partes = desc.split(" ", 1)
    if len(partes) > 1 and len(partes[0]) <= 20:
        marca, nome = partes[0], partes[1]

    codigo_interno = omie or ean
    if produto:
        ean_db = produto["ean"]
        # atualiza nome/omie se mudou
        if (produto.get("codigo_interno") or "") != codigo_interno or (produto.get("produto") or "") != nome:
            atualizar_produto(ean_db, produto=nome, marca=marca, codigo_interno=codigo_interno)
            produto = buscar_produto(ean_db) or produto
    else:
        # cadastra com EAN de barras quando existir; senao usa omie
        ean_novo = ean or omie
        ok, _ = criar_produto(
            ean=ean_novo, produto=nome, marca=marca, codigo_interno=codigo_interno,
        )
        if not ok:
            # pode já existir — tenta buscar de novo
            produto = buscar_produto(ean_novo) or buscar_produto(omie)
        else:
            produto = buscar_produto(ean_novo)

    if not produto:
        return None

    ean_db = produto["ean"]
    # Vincula ean e codigo_omie como chaves de bipagem
    for alias in (ean, omie, item_rt.get("codigo")):
        if alias and alias != ean_db:
            try:
                vincular_codigo(alias, ean_db, origem="rt_planilha")
            except Exception:
                pass
    return produto


def _processar_bip(codigo_bruto, sessao):
    """Cruza código lido com planilha RT (ean + codigo_omie) e soma na sessão."""
    from database.rt_lista import resolver_na_planilha, carregar_lista_rt

    parsed = parse_codigo_lido(codigo_bruto)
    codigo = parsed["ean"] or (codigo_bruto or "").strip()

    # 1) Busca precisa na planilha: colunas ean e codigo_omie
    carregar_lista_rt(force=False)
    item_rt = resolver_na_planilha(codigo)
    produto = None
    if item_rt:
        produto = _garantir_produto_rt(item_rt)

    # 2) Fallback cadastro já existente no banco
    if not produto:
        produto = buscar_produto(codigo)
    if not produto and parsed.get("codigo_interno"):
        produto = buscar_produto(parsed["codigo_interno"])

    if not produto:
        return {
            "encontrado": False,
            "ean": codigo,
            "msg": f"EAN/código não cadastrado na planilha RT (ean/codigo_omie): {codigo}",
        }

    ean_real = produto["ean"]
    lote = parsed.get("lote") or produto.get("lote") or ""
    venc = parsed.get("data_vencimento") or produto.get("data_vencimento") or ""
    registrar_contagem(ean_real, quantidade=1, sessao=sessao, lote=lote, data_vencimento=venc)
    qtd = qtd_contagem_sessao(ean_real, sessao)
    vencido = bool(venc and str(venc)[:10] < datetime.now().strftime("%Y-%m-%d"))
    codigo_omie = (
        (item_rt or {}).get("codigo_omie")
        or produto.get("codigo_interno")
        or ean_real
    )
    return {
        "encontrado": True,
        "produto": produto,
        "codigo_omie": codigo_omie,
        "ean_planilha": (item_rt or {}).get("ean") or produto.get("ean"),
        "fonte": "planilha_rt" if item_rt else "banco",
        "qtd_sessao": qtd,
        "incremento": 1,
        "lote": lote,
        "data_vencimento": venc,
        "vencido": vencido,
        "msg": f"{produto['produto']} — total {qtd}",
    }


@app.route("/api/scanner/bip", methods=["POST"])
@login_required
@api_handler
def api_scanner_bip():
    data = request.json or {}
    sessao = data.get("sessao") or session.get("sessao_atual", "")
    codigo = data.get("codigo") or data.get("ean") or ""
    if not str(codigo).strip():
        return jsonify({"encontrado": False, "msg": "Código vazio"}), 400
    return jsonify(_processar_bip(codigo, sessao))


@app.route("/api/scanner/<path:ean>")
@login_required
@api_handler
def api_scanner_ean(ean):
    sessao = request.args.get("sessao", session.get("sessao_atual", ""))
    return jsonify(_processar_bip(ean, sessao))


@app.route("/api/scanner/batch", methods=["POST"])
@login_required
@api_handler
def api_scanner_batch():
    data = request.json
    eans = data.get("eans", [])
    sessao = data.get("sessao", session.get("sessao_atual", ""))
    if not sessao:
        sessao = f"leitura_{len(eans)}_{os.urandom(2).hex()}"
        criar_sessao(sessao)
    resultados = []
    for raw in eans:
        if not str(raw).strip():
            continue
        res = _processar_bip(str(raw), sessao)
        if res.get("encontrado"):
            resultados.append({
                "ean": res["produto"]["ean"], "status": "ok",
                "produto": res["produto"]["produto"],
                "qtd_sessao": res["qtd_sessao"],
            })
        else:
            resultados.append({"ean": res.get("ean", ""), "status": "nao_encontrado"})
    return jsonify({"sessao": sessao, "resultados": resultados, "total": len(resultados)})


@app.route("/scanner")
@login_required
def pagina_scanner():
    return render_template("scanner.html")

# ── Contagem ───────────────────────────────────────────────

@app.route("/api/contagem")
@login_required
@api_handler
def api_contagem():
    sessao = request.args.get("sessao", "")
    cruzar = request.args.get("cruzar", "1") in ("1", "true", "True", "yes")
    return jsonify(get_contagens(sessao, cruzar=cruzar))


@app.route("/api/omie/sincronizar", methods=["POST"])
@login_required
@api_handler
def api_omie_sincronizar():
    ok, msg = sincronizar_omie()
    return jsonify({"sucesso": ok, "msg": msg}), (200 if ok else 400)


@app.route("/api/rt/status")
@login_required
@api_handler
def api_rt_status():
    """Status rápido da lista RT (índice ean + codigo_omie da planilha)."""
    from database.rt_lista import status_lista_rt, carregar_lista_rt
    carregar_lista_rt(force=False)
    st = status_lista_rt()
    total_db = len(listar_produtos())
    return jsonify({
        "sucesso": st.get("sucesso", False),
        "total_produtos": st.get("total") or total_db,
        "total_banco": total_db,
        "arquivo": st.get("arquivo"),
        "ean_index": st.get("ean_index", 0),
        "omie_index": st.get("omie_index", 0),
        "pronto": (st.get("total") or 0) > 0 or total_db > 0,
        "msg": st.get("msg") or f"{total_db} produtos no cadastro",
    })


_RT_SYNC_CACHE = {"ts": 0, "msg": "", "ok": False}


@app.route("/api/rt/sincronizar", methods=["POST", "GET"])
@login_required
@api_handler
def api_rt_sincronizar():
    """Sincroniza cadastro com lista_produtos_RToficial.xlsx (Documents ou data/)."""
    import time
    force = False
    caminho = None
    if request.method == "POST" and request.is_json:
        body = request.json or {}
        caminho = body.get("caminho") or None
        force = bool(body.get("force"))
    force = force or request.args.get("force") in ("1", "true", "True")

    # Evita reimportar a cada abertura do Scanner (sync Neon é lento)
    agora = time.time()
    if not force and _RT_SYNC_CACHE["ok"] and (agora - _RT_SYNC_CACHE["ts"]) < 3600:
        total = len(listar_produtos())
        return jsonify({
            "sucesso": True,
            "msg": _RT_SYNC_CACHE["msg"] or "Lista RT já sincronizada",
            "total_produtos": total,
            "arquivo": next((p for p in caminho_lista_rt_oficial() if os.path.exists(p)), None),
            "cache": True,
        })

    ok, msg = sincronizar_rt_oficial(caminho)
    total = len(listar_produtos())
    arquivo = next((p for p in caminho_lista_rt_oficial() if os.path.exists(p)), None)
    if ok:
        _RT_SYNC_CACHE.update({"ts": agora, "msg": msg, "ok": True})
    return jsonify({
        "sucesso": ok,
        "msg": msg,
        "total_produtos": total,
        "arquivo": arquivo,
        "cache": False,
    }), (200 if ok else 400)


@app.route("/api/rede")
@login_required
@api_handler
def api_rede():
    """IP da rede local para acessar de outros PCs."""
    from utils.network import obter_ip_rede
    ip = obter_ip_rede()
    porta = int(os.environ.get("PORT", 5000))
    return jsonify({
        "ip": ip,
        "porta": porta,
        "url_local": f"http://{ip}:{porta}",
        "url_vercel": "https://inventario-qr-beta.vercel.app",
    })


@app.route("/contagem")
@login_required
def pagina_contagem():
    return render_template("contagem.html")


@app.route("/api/exportar/contagem")
@login_required
@api_handler
def api_exportar_contagem():
    import openpyxl
    sessao = request.args.get("sessao", "")
    cruzar = request.args.get("cruzar", "1") in ("1", "true", "True", "yes")
    contagens = get_contagens(sessao, cruzar=cruzar)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contagem"
    ws.append(["Codigo Omie", "EAN", "Produto", "Marca", "Base", "Lote", "Vencimento",
               "Estoque", "Total Contado", "Status", "Ultima Leitura"])
    for c in contagens:
        ws.append([
            c.get("codigo_omie") or c.get("codigo_interno") or c["ean"],
            c["ean"], c["produto"], c.get("marca", ""), c.get("base_especifica", ""),
            c.get("lote", ""), c.get("data_vencimento", ""),
            c.get("quantidade_estoque", 0), c["total_contado"],
            c.get("status", ""), c.get("ultima_leitura", ""),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nome = f"contagem_{sessao or 'geral'}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(buf, as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── Validação ──────────────────────────────────────────────

@app.route("/api/validar", methods=["POST"])
@login_required
@api_handler
def api_validar():
    data = request.json
    return jsonify(validar_base(data.get("ean", ""), data.get("base_informada", "")))


@app.route("/validacao")
@login_required
def pagina_validacao():
    return render_template("validacao.html")

# ── Sessões ────────────────────────────────────────────────

@app.route("/api/sessoes")
@login_required
@api_handler
def api_sessoes():
    return jsonify(listar_sessoes())


@app.route("/api/sessao", methods=["POST"])
@login_required
@api_handler
def api_criar_sessao():
    data = request.json
    nome = data.get("nome", "").strip()
    if not nome:
        return jsonify({"sucesso": False, "msg": "Nome obrigatório"}), 400
    criar_sessao(nome)
    session["sessao_atual"] = nome
    return jsonify({"sucesso": True, "sessao": nome})

# ── Importar Excel ─────────────────────────────────────────

@app.route("/importar")
@login_required
def pagina_importar():
    return render_template("importar.html")


@app.route("/api/importar", methods=["POST"])
@login_required
@api_handler
def api_importar():
    if "file" not in request.files:
        return jsonify({"sucesso": False, "msg": "Nenhum arquivo enviado"}), 400
    file = request.files["file"]
    path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(path)
    sucesso, msg = importar_excel(path)
    return jsonify({"sucesso": sucesso, "msg": msg})

# ── Histórico de Validações ─────────────────────────────────

@app.route("/api/validacoes")
@login_required
@api_handler
def api_validacoes():
    return jsonify(listar_validacoes())


@app.route("/validacoes")
@login_required
def pagina_validacoes():
    return render_template("validacoes.html")

# ── Relatório ──────────────────────────────────────────────

@app.route("/api/relatorio")
@login_required
@api_handler
def api_relatorio():
    sessao = request.args.get("sessao", "")
    cruzar = request.args.get("cruzar", "1") in ("1", "true", "True", "yes")
    contagens = get_contagens(sessao, cruzar=cruzar)
    total = sum(c["total_contado"] for c in contagens)
    contados = sum(1 for c in contagens if c.get("total_contado", 0) > 0)
    pendentes = sum(1 for c in contagens if c.get("total_contado", 0) == 0)
    return render_template("relatorio.html",
        sessao=sessao or "Todas",
        contagens=contagens,
        total=total,
        contados=contados,
        pendentes=pendentes,
        cruzar=cruzar,
        emitido_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )

# ── Configurações ──────────────────────────────────────────

@app.route("/api/config", methods=["GET", "POST"])
@login_required
@api_handler
def api_config():
    if request.method == "POST":
        save_config(request.json)
        return jsonify({"sucesso": True, "msg": "Configurações salvas"})
    return jsonify(get_all_config())


@app.route("/configuracoes")
@login_required
def pagina_config():
    return render_template("configuracoes.html")

# ── Vencimentos ────────────────────────────────────────────

@app.route("/api/vencimentos")
@login_required
@api_handler
def api_vencimentos():
    return jsonify(get_vencimentos())


@app.route("/vencimentos")
@login_required
def pagina_vencimentos():
    return render_template("vencimentos.html")

# ── Etiquetas QR ───────────────────────────────────────────

@app.route("/api/etiquetas/<ean>")
@login_required
@api_handler
def api_etiqueta(ean):
    produto = buscar_produto(ean)
    if not produto:
        return jsonify({"erro": "Produto não encontrado"}), 404
    qr_b64 = gerar_qrcode_base64(
        ean=produto["ean"], produto=produto.get("produto", ""),
        marca=produto.get("marca", ""),
        unidade=produto.get("unidade_medida", ""),
        base=produto.get("base_especifica", ""),
        dosagem=produto.get("instrucao_dosagem", ""),
        lote=produto.get("lote", ""),
        data_vencimento=produto.get("data_vencimento", ""),
        codigo_interno=produto.get("codigo_interno", ""),
    )
    return jsonify({"produto": produto, "qrcode": qr_b64})


@app.route("/api/etiquetas", methods=["POST"])
@login_required
@api_handler
def api_etiquetas_lote():
    data = request.json
    eans = data.get("eans", [])
    etiquetas = []
    for ean in eans:
        p = buscar_produto(ean.strip())
        if p:
            qr = gerar_qrcode_base64(
                ean=p["ean"], produto=p.get("produto", ""),
                marca=p.get("marca", ""),
                unidade=p.get("unidade_medida", ""),
                base=p.get("base_especifica", ""),
                dosagem=p.get("instrucao_dosagem", ""),
                lote=p.get("lote", ""),
                data_vencimento=p.get("data_vencimento", ""),
                codigo_interno=p.get("codigo_interno", ""),
            )
            etiquetas.append({"produto": p, "qrcode": qr})
    return jsonify(etiquetas)


@app.route("/api/nfe/<int:rec_id>/etiquetas")
@login_required
@api_handler
def api_nfe_etiquetas(rec_id):
    itens = get_etiquetas_nfe(rec_id)
    etiquetas = []
    for item in itens:
        p = buscar_produto(item.get("ean", "") or item.get("codigo_produto", ""))
        if not p:
            continue
        qr = gerar_qrcode_base64(
            ean=p["ean"], produto=p.get("produto", item.get("descricao", "")),
            marca=p.get("marca", ""),
            unidade=p.get("unidade_medida", item.get("unidade", "")),
            base=p.get("base_especifica", ""),
            dosagem=p.get("instrucao_dosagem", ""),
            lote=item.get("lote", "") or p.get("lote", ""),
            data_vencimento=item.get("data_vencimento", "") or p.get("data_vencimento", ""),
            codigo_interno=p.get("codigo_interno", ""),
        )
        etiquetas.append({"produto": p, "qrcode": qr, "lote_nf": item.get("lote", ""), "venc_nf": item.get("data_vencimento", "")})
    return jsonify(etiquetas)


@app.route("/etiquetas")
@login_required
def pagina_etiquetas():
    return render_template("etiquetas.html")

# ── NF-e / Recebimento ─────────────────────────────────────

@app.route("/recebimento")
@login_required
def pagina_recebimento():
    return render_template("recebimento.html")


@app.route("/api/nfe/upload", methods=["POST"])
@login_required
@api_handler
def api_nfe_upload():
    if "file" not in request.files:
        return jsonify({"sucesso": False, "msg": "Nenhum arquivo"}), 400
    file = request.files["file"]
    path = os.path.join(app.config["UPLOAD_FOLDER"], "nfe_" + file.filename)
    file.save(path)
    nfe = parse_nfe_xml(path)

    if nfe.get("chave_acesso"):
        existing = verificar_chave_nfe(nfe["chave_acesso"])
        if existing:
            return jsonify({"sucesso": False, "msg": f"NF-e já recebida anteriormente (NF {existing['numero']})"}), 400

    rec_id = criar_recebimento_nf(
        nfe.get("chave_acesso", ""), nfe["numero"], nfe.get("serie", ""),
        nfe.get("fornecedor", ""), nfe.get("cnpj_fornecedor", ""),
        nfe.get("data_emissao", ""), nfe.get("itens", []),
    )
    return jsonify({"sucesso": True, "recebimento_id": rec_id, "nfe": nfe})


@app.route("/api/nfe/listar")
@login_required
@api_handler
def api_nfe_listar():
    return jsonify(listar_recebimentos())


@app.route("/api/nfe/<int:rec_id>/excluir", methods=["POST"])
@login_required
@api_handler
def api_nfe_excluir(rec_id):
    excluir_recebimento(rec_id)
    return jsonify({"sucesso": True})


@app.route("/api/nfe/<int:rec_id>")
@login_required
@api_handler
def api_nfe_detalhe(rec_id):
    rec = get_recebimento(rec_id)
    if not rec:
        return jsonify({"erro": "Recebimento não encontrado"}), 404
    return jsonify(rec)


@app.route("/api/nfe/<int:rec_id>/buscar-item/<ean>")
@login_required
@api_handler
def api_nfe_buscar_item(rec_id, ean):
    row = get_item_recebimento(rec_id, ean)
    if row:
        return jsonify({"encontrado": True, **row})
    return jsonify({"encontrado": False})


@app.route("/api/nfe/<int:rec_id>/conferir", methods=["POST"])
@login_required
@api_handler
def api_nfe_conferir(rec_id):
    data = request.json
    resultado = conferir_item_recebimento(
        rec_id, data.get("ean", "").strip(),
        data.get("quantidade", 1),
        data.get("lote", ""),
        data.get("data_vencimento", ""),
    )
    if not resultado:
        return jsonify({"encontrado": False, "msg": "Produto não encontrado nesta NF ou já totalmente recebido"})
    return jsonify({"encontrado": True, **resultado})


@app.route("/api/nfe/<int:rec_id>/finalizar", methods=["POST"])
@login_required
@api_handler
def api_nfe_finalizar(rec_id):
    resultado = finalizar_recebimento(rec_id)
    return jsonify({"sucesso": True, **resultado})


# ── Backup ─────────────────────────────────────────────────

@app.route("/backup")
@login_required
def pagina_backup():
    return render_template("backup.html")


@app.route("/api/backup")
@login_required
@api_handler
def api_backup():
    if PG_ATIVO:
        return jsonify({"sucesso": False, "msg": "Backup por arquivo não se aplica ao Neon. Use o dashboard do Neon ou /api/exportar/contagem."}), 400
    return send_file(DB_PATH, as_attachment=True,
                     download_name=f"inventario_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db")


@app.route("/api/restore", methods=["POST"])
@login_required
@api_handler
def api_restore():
    if PG_ATIVO:
        return jsonify({"sucesso": False, "msg": "Restauração por arquivo não se aplica ao Neon."}), 400
    if "file" not in request.files:
        return jsonify({"sucesso": False, "msg": "Nenhum arquivo"}), 400
    file = request.files["file"]
    tmp = os.path.join(app.config["UPLOAD_FOLDER"], "_restore_temp.db")
    file.save(tmp)
    try:
        conn = criar_conexao()
        conn.execute("PRAGMA integrity_check")
        conn.close()
        shutil.copy2(tmp, DB_PATH)
        os.remove(tmp)
        return jsonify({"sucesso": True, "msg": "Banco restaurado com sucesso!"})
    except Exception as e:
        if os.path.exists(tmp): os.remove(tmp)
        return jsonify({"sucesso": False, "msg": f"Arquivo inválido: {str(e)}"}), 400

# ── QR Conexão iPhone / Celular ──────────────────────────────────────

from utils.network import obter_ip_rede


def _obter_ip_rede():
    return obter_ip_rede()


@app.route("/api/qr-conexao")
@login_required
@api_handler
def api_qr_conexao():
    vercel_url = os.environ.get("VERCEL_URL", "")
    if vercel_url:
        url = f"https://{vercel_url}"
    else:
        ipconfig = _obter_ip_rede()
        url = f"http://{ipconfig}:5000/"
    import qrcode, base64
    qr = qrcode.make(url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return jsonify({"url": url, "qrcode": f"data:image/png;base64,{b64}"})

# ── Test Barcodes ──────────────────────────────────────────

@app.route("/teste-barcodes")
@login_required
def teste_barcodes():
    produtos_teste = [
        {"ean": "01405000132", "nome": "FITA CREPE VERDE 48MMX50M", "qtd": 12},
        {"ean": "5323543", "nome": "LIXA LIQUIDA 500 ML", "qtd": 4},
        {"ean": "29912", "nome": "APLICADOR P/MASSA PLASTICA", "qtd": 6},
        {"ean": "023634-28", "nome": "THINNER ECOEF 2750 5L", "qtd": 2},
        {"ean": "1405000066", "nome": "FITA CREPE VERDE 24MMX50M", "qtd": 24},
        {"ean": "5323557", "nome": "REPARA PAREDES 2X8 GR", "qtd": 10},
        {"ean": "1700", "nome": "EXTENSOR 3M PROLONGADOR ACO", "qtd": 5},
        {"ean": "023636-28", "nome": "THINNER ECOEF 5000 5L", "qtd": 3},
    ]
    return render_template("teste_barcodes.html", produtos=produtos_teste)

# ── Estoque Atual ───────────────────────────────────────

@app.route("/estoque")
@login_required
def pagina_estoque():
    return render_template("estoque.html")


@app.route("/api/estoque")
@login_required
@api_handler
def api_estoque():
    return jsonify(listar_estoque(request.args.get("search", "")))


@app.route("/api/estoque/zerados")
@login_required
@api_handler
def api_estoque_zerados():
    return jsonify(listar_estoque_zerados())

# ── Saída de Estoque ─────────────────────────────────────

@app.route("/saida")
@login_required
def pagina_saida():
    return render_template("saida.html")


@app.route("/api/saidas", methods=["GET"])
@login_required
@api_handler
def api_listar_saidas():
    return jsonify(listar_saidas())


@app.route("/api/saidas", methods=["POST"])
@login_required
@api_handler
def api_registrar_saida():
    data = request.get_json()
    if not data or not data.get("ean"):
        return jsonify({"sucesso": False, "msg": "EAN obrigatório"}), 400
    registrar_saida(
        data["ean"], data.get("produto", ""), data.get("quantidade", 1),
        data.get("lote", ""), data.get("data_vencimento", ""),
        data.get("motivo", ""), data.get("observacao", ""),
    )
    return jsonify({"sucesso": True})

# ── Gerenciamento de Usuários ────────────────────────────────

@app.route("/usuarios")
@login_required
def pagina_usuarios():
    return render_template("usuarios.html")


@app.route("/api/usuarios", methods=["GET"])
@login_required
@api_handler
def api_listar_usuarios():
    return jsonify(listar_usuarios())


@app.route("/api/usuarios", methods=["POST"])
@login_required
@api_handler
def api_criar_usuario():
    data = request.json
    usuario = data.get("usuario", "").strip()
    senha = data.get("senha", "")
    nome = data.get("nome", "")
    if not usuario or not senha:
        return jsonify({"sucesso": False, "msg": "Usuário e senha obrigatórios"}), 400
    sucesso, msg = criar_usuario(usuario, senha, nome)
    return jsonify({"sucesso": sucesso, "msg": msg})


@app.route("/api/usuarios/<usuario>/excluir", methods=["POST"])
@login_required
@api_handler
def api_excluir_usuario(usuario):
    if usuario == session.get("usuario"):
        return jsonify({"sucesso": False, "msg": "Não é possível excluir seu próprio usuário"}), 400
    excluir_usuario(usuario)
    return jsonify({"sucesso": True})


@app.route("/api/usuarios/<usuario>/redefinir-senha", methods=["POST"])
@login_required
@api_handler
def api_redefinir_senha(usuario):
    data = request.json
    nova_senha = data.get("nova_senha", "")
    if not nova_senha:
        return jsonify({"sucesso": False, "msg": "Nova senha obrigatória"}), 400
    redefinir_senha(usuario, nova_senha)
    return jsonify({"sucesso": True, "msg": "Senha redefinida com sucesso"})

# ── Nav ────────────────────────────────────────────────────

NAV_SECTIONS = [
    ("INVENTÁRIO", [
        ("/", "Início", "fa-home"),
        ("/scanner", "Scanner", "fa-qrcode"),
        ("/produtos", "Produtos", "fa-boxes"),
        ("/validacao", "Validação", "fa-check-double"),
        ("/contagem", "Contagem", "fa-chart-bar"),
        ("/etiquetas", "Etiquetas", "fa-tag"),
        ("/vencimentos", "Vencimentos", "fa-calendar-alt"),
        ("/estoque", "Estoque", "fa-warehouse"),
        ("/saida", "Saída", "fa-arrow-right"),
    ]),
    ("RECEBIMENTO", [
        ("/recebimento", "NF-e", "fa-file-invoice"),
    ]),
    ("GERAL", [
        ("/validacoes", "Histórico", "fa-history"),
        ("/importar", "Importar", "fa-file-excel"),
        ("/backup", "Backup", "fa-database"),
        ("/usuarios", "Usuários", "fa-users"),
        ("/configuracoes", "Config", "fa-cog"),
    ]),
]


@app.context_processor
def inject_nav():
    tema = get_all_config().get("tema", "escuro")
    return {"nav_sections": NAV_SECTIONS, "tema_config": tema}


if not os.environ.get("SKIP_DB_INIT"):
    try:
        criar_tabelas()
    except Exception as e:
        import logging as _lg
        _lg.getLogger("app").warning(f"Falha ao inicializar banco: {e}")


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
