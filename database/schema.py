import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "inventario.db")


def get_db_path():
    return DB_PATH


def criar_conexao():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    conn = criar_conexao()
    try:
        yield conn
    finally:
        conn.close()


def criar_tabelas():
    conn = criar_conexao()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS recebimentos_nf (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave_acesso TEXT,
            numero TEXT,
            serie TEXT,
            fornecedor TEXT DEFAULT '',
            cnpj_fornecedor TEXT DEFAULT '',
            data_emissao TEXT DEFAULT '',
            data_recebimento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'aberto',
            total_itens INTEGER DEFAULT 0,
            itens_recebidos INTEGER DEFAULT 0,
            finalizado_em TIMESTAMP,
            loja TEXT DEFAULT 'RTJ'
        );

        CREATE TABLE IF NOT EXISTS itens_recebimento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recebimento_id INTEGER NOT NULL,
            ean TEXT DEFAULT '',
            codigo_produto TEXT DEFAULT '',
            descricao TEXT NOT NULL,
            ncm TEXT DEFAULT '',
            unidade TEXT DEFAULT 'UN',
            quantidade_esperada REAL DEFAULT 1,
            quantidade_recebida REAL DEFAULT 0,
            lote TEXT DEFAULT '',
            data_vencimento TEXT DEFAULT '',
            FOREIGN KEY (recebimento_id) REFERENCES recebimentos_nf(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ean TEXT UNIQUE NOT NULL,
            produto TEXT NOT NULL,
            marca TEXT NOT NULL DEFAULT '',
            unidade_medida TEXT DEFAULT 'UN',
            base_especifica TEXT DEFAULT '',
            instrucao_dosagem TEXT DEFAULT '',
            lote TEXT DEFAULT '',
            data_vencimento TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS produto_codigos (
            codigo TEXT PRIMARY KEY,
            ean_produto TEXT NOT NULL,
            origem TEXT DEFAULT 'bip',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ean_produto) REFERENCES produtos(ean) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS inventario_contagem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ean TEXT NOT NULL,
            quantidade_contada INTEGER DEFAULT 1,
            lote TEXT DEFAULT '',
            data_vencimento TEXT DEFAULT '',
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sessao TEXT DEFAULT '',
            loja TEXT DEFAULT 'RTJ',
            FOREIGN KEY (ean) REFERENCES produtos(ean)
        );

        CREATE TABLE IF NOT EXISTS sessoes_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            loja TEXT DEFAULT 'RTJ',
            data_abertura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_fechamento TIMESTAMP,
            status TEXT DEFAULT 'aberta'
        );

        CREATE TABLE IF NOT EXISTS estoque_produto (
            ean TEXT NOT NULL,
            loja TEXT NOT NULL DEFAULT 'RTJ',
            quantidade_estoque REAL NOT NULL DEFAULT 0,
            lote TEXT DEFAULT '',
            data_vencimento TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ean, loja)
        );

        CREATE TABLE IF NOT EXISTS validacoes_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ean TEXT NOT NULL,
            base_informada TEXT NOT NULL,
            base_oficial TEXT NOT NULL,
            status TEXT DEFAULT 'pendente',
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ean) REFERENCES produtos(ean)
        );

        CREATE INDEX IF NOT EXISTS idx_inventario_ean ON inventario_contagem(ean);
        CREATE INDEX IF NOT EXISTS idx_inventario_sessao ON inventario_contagem(sessao);
        CREATE INDEX IF NOT EXISTS idx_produtos_ean ON produtos(ean);
        CREATE INDEX IF NOT EXISTS idx_validacoes_ean ON validacoes_base(ean);
    """)

    migrar_banco(conn)

    conn.commit()
    conn.close()
    return DB_PATH


def migrar_banco(conn):
    cursor = conn.cursor()
    existing = [row[1] for row in cursor.execute("PRAGMA table_info(produtos)").fetchall()]
    if "lote" not in existing:
        cursor.execute("ALTER TABLE produtos ADD COLUMN lote TEXT DEFAULT ''")
    if "data_vencimento" not in existing:
        cursor.execute("ALTER TABLE produtos ADD COLUMN data_vencimento TEXT DEFAULT ''")

    existing_cont = [row[1] for row in cursor.execute("PRAGMA table_info(inventario_contagem)").fetchall()]
    if "lote" not in existing_cont:
        cursor.execute("ALTER TABLE inventario_contagem ADD COLUMN lote TEXT DEFAULT ''")
    if "data_vencimento" not in existing_cont:
        cursor.execute("ALTER TABLE inventario_contagem ADD COLUMN data_vencimento TEXT DEFAULT ''")
    if "loja" not in existing_cont:
        cursor.execute("ALTER TABLE inventario_contagem ADD COLUMN loja TEXT DEFAULT 'RTJ'")

    existing_sess = [row[1] for row in cursor.execute("PRAGMA table_info(sessoes_inventario)").fetchall()]
    if "loja" not in existing_sess:
        cursor.execute("ALTER TABLE sessoes_inventario ADD COLUMN loja TEXT DEFAULT 'RTJ'")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inventario_loja ON inventario_contagem(loja)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessoes_loja ON sessoes_inventario(loja)")

    if "codigo_interno" not in existing:
        cursor.execute("ALTER TABLE produtos ADD COLUMN codigo_interno TEXT DEFAULT ''")

    existing_rec = [row[1] for row in cursor.execute("PRAGMA table_info(recebimentos_nf)").fetchall()]
    if "excluido" not in existing_rec:
        cursor.execute("ALTER TABLE recebimentos_nf ADD COLUMN excluido INTEGER DEFAULT 0")
    if "loja" not in existing_rec:
        cursor.execute("ALTER TABLE recebimentos_nf ADD COLUMN loja TEXT DEFAULT 'RTJ'")

    if "quantidade_estoque" not in existing:
        cursor.execute("ALTER TABLE produtos ADD COLUMN quantidade_estoque REAL DEFAULT 0")

    existing_sai = [row[1] for row in cursor.execute("PRAGMA table_info(saidas_estoque)").fetchall()]
    if not existing_sai:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saidas_estoque (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ean TEXT NOT NULL DEFAULT '',
                produto TEXT DEFAULT '',
                quantidade REAL DEFAULT 1,
                lote TEXT DEFAULT '',
                data_vencimento TEXT DEFAULT '',
                motivo TEXT DEFAULT '',
                observacao TEXT DEFAULT '',
                data_saida TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        existing_sai = [row[1] for row in cursor.execute("PRAGMA table_info(saidas_estoque)").fetchall()]
    if existing_sai and "loja" not in existing_sai:
        cursor.execute("ALTER TABLE saidas_estoque ADD COLUMN loja TEXT DEFAULT ''")

    cursor.execute("CREATE TABLE IF NOT EXISTS estoque_produto ("
                   "ean TEXT NOT NULL, loja TEXT NOT NULL DEFAULT 'RTJ',"
                   "quantidade_loja REAL NOT NULL DEFAULT 0,"
                   "quantidade_estoque REAL NOT NULL DEFAULT 0, lote TEXT DEFAULT '',"
                   "data_vencimento TEXT DEFAULT '', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                   "PRIMARY KEY (ean, loja))")
    existing_ep = [row[1] for row in cursor.execute("PRAGMA table_info(estoque_produto)").fetchall()]
    if existing_ep and "quantidade_loja" not in existing_ep:
        cursor.execute("ALTER TABLE estoque_produto ADD COLUMN quantidade_loja REAL NOT NULL DEFAULT 0")
    qtd = cursor.execute("SELECT COUNT(*) FROM estoque_produto").fetchone()[0]
    if qtd == 0:
        cursor.execute("""INSERT OR IGNORE INTO estoque_produto (ean, loja, quantidade_loja, quantidade_estoque, lote, data_vencimento)
                          SELECT ean, 'RTJ', 0, quantidade_estoque, lote, data_vencimento FROM produtos
                          WHERE COALESCE(quantidade_estoque, 0) > 0""")


