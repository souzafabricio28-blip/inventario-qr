import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.backend import criar_tabelas, DB_PATH, listar_produtos, buscar_produto, criar_produto, registrar_contagem, get_contagens, criar_sessao, fechar_sessao, listar_sessoes
from database.import_excel import importar_excel
from scanner.hid_scanner import ScannerHID
from qrcode_gen.generator import gerar_qrcode, gerar_lote_qrcode
from validation.base_validator import validar_base
from utils.helpers import exibir_cabecalho


sessao_atual = ""


def menu_principal():
    global sessao_atual
    while True:
        exibir_cabecalho("SISTEMA DE INVENTÁRIO - QR CODE & VALIDAÇÃO DE BASES")
        print(f"  Sessão atual: {sessao_atual or 'Nenhuma'}")
        print(f"  Banco: {DB_PATH}")
        print()
        print("  1. INICIAR NOVA SESSÃO DE INVENTÁRIO")
        print("  2. MODO SCANNER (leitura contínua de EAN)")
        print("  3. CADASTRAR PRODUTO")
        print("  4. LISTAR PRODUTOS")
        print("  5. IMPORTAR PRODUTOS DO EXCEL")
        print("  6. GERAR QR CODES (lote)")
        print("  7. VALIDAÇÃO DE BASE (ANTI-ERRO)")
        print("  8. RELATÓRIO DE CONTAGEM")
        print("  9. SESSÕES DE INVENTÁRIO")
        print("  0. SAIR")
        print()
        opcao = input("  Escolha: ").strip()

        if opcao == "1":
            iniciar_sessao()
        elif opcao == "2":
            modo_scanner()
        elif opcao == "3":
            cadastrar_produto()
        elif opcao == "4":
            listar_produtos_menu()
        elif opcao == "5":
            importar_excel_menu()
        elif opcao == "6":
            gerar_qrcodes_menu()
        elif opcao == "7":
            validacao_base_menu()
        elif opcao == "8":
            relatorio_contagem()
        elif opcao == "9":
            menu_sessoes()
        elif opcao == "0":
            print("\n  Encerrando...")
            sys.exit(0)


def iniciar_sessao():
    global sessao_atual
    exibir_cabecalho("NOVA SESSÃO DE INVENTÁRIO")
    nome = input("  Nome da sessão: ").strip()
    if not nome:
        print("  Nome inválido.")
        input("\n  Enter para continuar...")
        return
    criar_sessao(nome)
    sessao_atual = nome
    print(f"\n  Sessão '{nome}' iniciada com sucesso!")
    input("\n  Enter para continuar...")


def on_scan_callback(ean):
    produto = buscar_produto(ean)
    if produto:
        registrar_contagem(ean, sessao=sessao_atual)
        print(f"    -> {produto['produto']} ({produto['marca']}) - CONTAGEM REGISTRADA +1")
    else:
        print(f"    -> EAN {ean} NÃO ENCONTRADO NA BASE")
        resp = input("    Cadastrar agora? (s/N): ").strip().lower()
        if resp == "s":
            cadastrar_produto_rápido(ean)
            registrar_contagem(ean, sessao=sessao_atual)
            print(f"    -> Produto cadastrado e contagem registrada!")


def modo_scanner():
    global sessao_atual
    if not sessao_atual:
        exibir_cabecalho("MODO SCANNER")
        print("  Nenhuma sessão ativa!")
        resp = input("  Iniciar nova sessão? (s/N): ").strip().lower()
        if resp == "s":
            iniciar_sessao()
        else:
            return

    exibir_cabecalho("MODO SCANNER - LEITURA CONTÍNUA")
    print(f"  Sessão: {sessao_atual}")
    print(f"  Scanner modo HID (teclado) - Aponte e leia os códigos")
    print(f"  Comandos: '!sair' para voltar, '!status' para ver total\n")

    total = 0
    while True:
        ean = input("  EAN: ").strip()
        if ean == "!sair":
            break
        if ean == "!status":
            print(f"  Total de leituras nesta sessão: {total}")
            continue
        if not ean:
            continue

        produto = buscar_produto(ean)
        if produto:
            registrar_contagem(ean, sessao=sessao_atual)
            total += 1
            print(f"    OK: {produto['produto']} ({produto['marca']}) [+{total}]")
        else:
            print(f"    EAN {ean} não cadastrado")
            resp = input("    Cadastrar agora? (s/N): ").strip().lower()
            if resp == "s":
                cadastrar_produto_rápido(ean)
                registrar_contagem(ean, sessao=sessao_atual)
                total += 1
                print(f"    Cadastrado e contado! [+{total}]")

    print(f"\n  Fim da sessão. Total de leituras: {total}")
    input("\n  Enter para continuar...")


def cadastrar_produto():
    exibir_cabecalho("CADASTRAR PRODUTO")
    ean = input("  EAN: ").strip()
    if not ean:
        return
    cadastrar_produto_rápido(ean)


def cadastrar_produto_rápido(ean):
    print(f"\n  --- Cadastro rápido para EAN: {ean} ---")
    produto = input("  Nome do produto: ").strip()
    if not produto:
        print("  Cadastro cancelado.")
        return
    cod = input("  Código interno (ID): ").strip()
    marca = input("  Marca: ").strip()
    unidade = input("  Unidade (UN/LT/KG) [UN]: ").strip() or "UN"
    base = input("  Base específica (ex: Base A, Base B, Padrão): ").strip()
    dosagem = input("  Instrução de dosagem: ").strip()
    lote = input("  Lote: ").strip()
    data_venc = input("  Data de vencimento (AAAA-MM-DD): ").strip()

    sucesso, msg = criar_produto(
        ean=ean, produto=produto, marca=marca,
        unidade_medida=unidade, base_especifica=base,
        instrucao_dosagem=dosagem, lote=lote,
        data_vencimento=data_venc, codigo_interno=cod,
    )
    print(f"  {msg}")


def listar_produtos_menu():
    exibir_cabecalho("LISTA DE PRODUTOS")
    search = input("  Buscar (vazio para todos): ").strip()
    produtos = listar_produtos(search)
    if not produtos:
        print("\n  Nenhum produto encontrado.")
    else:
        print(f"\n  Total: {len(produtos)} produtos\n")
        print(f"  {'ID':<10} {'EAN':<15} {'PRODUTO':<22} {'MARCA':<10}")
        print("  " + "-" * 57)
        for p in produtos:
            ean_short = p["ean"][:14] if len(p["ean"]) > 14 else p["ean"]
            cod = (p.get("codigo_interno") or "")[:9] or "-"
            print(f"  {cod:<10} {ean_short:<15} {p['produto'][:21]:<22} {p['marca'][:9]:<10}")
    input("\n  Enter para continuar...")


def importar_excel_menu():
    exibir_cabecalho("IMPORTAR PRODUTOS DO EXCEL")
    caminho = input("  Caminho do arquivo Excel: ").strip()
    if not caminho:
        return
    print("  Importando...")
    sucesso, msg = importar_excel(caminho)
    print(f"\n  {'SUCESSO' if sucesso else 'ERRO'}: {msg}")
    input("\n  Enter para continuar...")


def gerar_qrcodes_menu():
    exibir_cabecalho("GERAR QR CODES")
    produtos = listar_produtos()
    if not produtos:
        print("  Nenhum produto cadastrado.")
        input("\n  Enter para continuar...")
        return

    print(f"  Total de produtos: {len(produtos)}")
    resp = input("  Gerar QR Codes para todos? (s/N): ").strip().lower()
    if resp == "s":
        arquivos = gerar_lote_qrcode(produtos)
        print(f"\n  {len(arquivos)} QR Codes gerados em: exports/qrcodes/")
    else:
        ean = input("  EAN do produto: ").strip()
        p = buscar_produto(ean)
        if p:
            arq = gerar_qrcode(
                ean=p["ean"], produto=p["produto"], marca=p["marca"],
                unidade=p["unidade_medida"], base=p["base_especifica"],
                dosagem=p["instrucao_dosagem"],
                codigo_interno=p.get("codigo_interno", ""),
            )
            print(f"  QR Code gerado: {arq}")
        else:
            print("  Produto não encontrado.")
    input("\n  Enter para continuar...")


def validacao_base_menu():
    exibir_cabecalho("VALIDAÇÃO DE BASE - ANTI-ERRO")
    print("  Função: Validar se a base coletada confere com a base oficial")
    print()

    ean = input("  EAN do produto: ").strip()
    if not ean:
        return

    produto = buscar_produto(ean)
    if not produto:
        print("  Produto não encontrado!")
        input("\n  Enter para continuar...")
        return

    print(f"\n  Produto: {produto['produto']}")
    print(f"  Marca:   {produto['marca']}")
    print(f"  Base oficial cadastrada: {produto['base_especifica'] or 'N/A'}")
    print(f"  Dosagem: {produto['instrucao_dosagem'] or 'N/A'}")
    print()

    if not produto["base_especifica"]:
        print("  ATENÇÃO: Produto sem base específica cadastrada.")
        resp = input("  Deseja cadastrar a base agora? (s/N): ").strip().lower()
        if resp == "s":
            base = input("  Base específica: ").strip()
            from database.backend import atualizar_produto
            atualizar_produto(ean, base_especifica=base)
            print("  Base atualizada!")

    base_informada = input("  Base coletada fisicamente: ").strip()
    resultado = validar_base(ean, base_informada)

    print()
    if resultado["status"] == "bloqueada":
        print(f"  {'!' * 50}")
        print(f"  BLOQUEADO! Divergência de base detectada!")
        print(f"  {resultado['mensagem']}")
        print(f"  {'!' * 50}")
    elif resultado["status"] == "aprovada":
        print(f"  {'v' * 40}")
        print(f"  APROVADO! Base confirmada com sucesso.")
        print(f"  {resultado['mensagem']}")
        print(f"  {'v' * 40}")
    else:
        print(f"  {resultado['mensagem']}")

    input("\n  Enter para continuar...")


def relatorio_contagem():
    global sessao_atual
    exibir_cabecalho("RELATÓRIO DE CONTAGEM")
    if sessao_atual:
        print(f"  Sessão atual: {sessao_atual}")
        resp = input("  Usar sessão atual? (S/n): ").strip().lower()
        if resp == "n":
            sessoes = listar_sessoes()
            if sessoes:
                print("\n  Sessões disponíveis:")
                for s in sessoes:
                    print(f"    {s['id']}. {s['nome']} - {s['status']} ({s.get('total_itens', 0)} itens)")
                sid = input("\n  ID da sessão: ").strip()
                sessao_nome = next((s["nome"] for s in sessoes if str(s["id"]) == sid), "")
            else:
                print("  Nenhuma sessão encontrada.")
                input("\n  Enter para continuar...")
                return
        else:
            sessao_nome = sessao_atual
    else:
        sessoes = listar_sessoes()
        if sessoes:
            print("  Sessões disponíveis:")
            for s in sessoes:
                print(f"    {s['id']}. {s['nome']} - {s['status']} ({s.get('total_itens', 0)} itens)")
            sid = input("\n  ID da sessão: ").strip()
            sessao_nome = next((s["nome"] for s in sessoes if str(s["id"]) == sid), "")
            if not sessao_nome:
                print("  Sessão inválida.")
                input("\n  Enter para continuar...")
                return
        else:
            print("  Nenhuma sessão encontrada.")
            input("\n  Enter para continuar...")
            return

    contagens = get_contagens(sessao_nome)
    if not contagens:
        print(f"\n  Nenhuma contagem registrada na sessão '{sessao_nome}'.")
    else:
        total_geral = sum(c["total_contado"] for c in contagens)
        print(f"\n  Sessão: {sessao_nome} | Total de itens: {len(contagens)} | Total de leituras: {total_geral}\n")
        print(f"  {'EAN':<15} {'PRODUTO':<22} {'MARCA':<10} {'BASE':<8} {'LOTE':<8} {'VENC':<11} {'QTD':<6}")
        print("  " + "-" * 80)
        for c in contagens:
            ean_short = c["ean"][:14] if len(c["ean"]) > 14 else c["ean"]
            lote = c.get("lote", "")[:7] if c.get("lote") else "-"
            ven = (c.get("data_vencimento") or "")[:10] or "-"
            print(f"  {ean_short:<15} {c['produto'][:21]:<22} {c['marca'][:9]:<10} {c['base_especifica'][:7]:<8} {lote:<8} {ven:<11} {c['total_contado']:<6}")
    input("\n  Enter para continuar...")


def menu_sessoes():
    exibir_cabecalho("SESSÕES DE INVENTÁRIO")
    sessoes = listar_sessoes()
    if not sessoes:
        print("  Nenhuma sessão registrada.")
    else:
        for s in sessoes:
            print(f"  {s['id']:>3}. {s['nome']:<20} | {s['status']:<8} | {s.get('total_itens', 0):>5} itens | {s['data_abertura'][:19]}")
    print()
    input("  Enter para continuar...")


if __name__ == "__main__":
    criar_tabelas()
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\n\n  Encerrando...")
        sys.exit(0)
