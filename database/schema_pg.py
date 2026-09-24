import os
import socket
import threading
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import DictCursor

DB_PATH = None

_lock = threading.Lock()
_pool = None


def get_db_path():
    return None


def construir_dsn():
    url = os.environ["DATABASE_URL"].replace("&channel_binding=require", "")
    if "hostaddr=" in url or "hostaddr%3D" in url:
        return url
    try:
        host = url.split("@")[-1].split("/")[0]
        port = 5432
        hostname = host
        if ":" in host and not host.startswith("["):
            hostname, port_s = host.rsplit(":", 1)
            try:
                port = int(port_s)
            except ValueError:
                pass
        ips = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        base, _, rest = url.partition("@")
        hostpart, _, dbq = rest.partition("/")
        dbname, _, query = dbq.partition("?")
        return f"{base}@hostaddr={ips},{hostpart}/{dbname}" + (f"?{query}" if query else "")
    except Exception:
        return url


def _criar_conexao_fisica():
    return psycopg2.connect(construir_dsn(), cursor_factory=DictCursor,
                            connect_timeout=30, keepalives=1)


def _conn_ok(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        return True
    except Exception:
        return False


def criar_conexao():
    """Retorna uma conexão do pool (reutilizável entre requests)."""
    global _pool
    with _lock:
        if _pool is None:
            try:
                from psycopg2.pool import ThreadedConnectionPool
                _pool = ThreadedConnectionPool(minconn=0, maxconn=3,
                                               dsn=construir_dsn(),
                                               cursor_factory=DictCursor,
                                               connect_timeout=30, keepalives=1)
            except Exception:
                return _criar_conexao_fisica()
    try:
        conn = _pool.getconn()
        if not _conn_ok(conn):
            _pool.putconn(conn)
            spawn = _criar_conexao_fisica()
            return spawn
        return conn
    except Exception:
        return _criar_conexao_fisica()


def devolver_conexao(conn):
    global _pool
    if conn is None:
        return
    if _pool is not None:
        try:
            _pool.putconn(conn)
            return
        except Exception:
            pass
    try:
        conn.close()
    except Exception:
        pass


@contextmanager
def get_db():
    conn = criar_conexao()
    try:
        yield conn
    finally:
        devolver_conexao(conn)


def criar_tabelas():
    conn = criar_conexao()
    try:
        cursor = conn.cursor()
        with open(os.path.join(os.path.dirname(__file__), "schema_pg.sql"), encoding="utf-8") as f:
            cursor.execute(f.read())

        # Semeia estoque_produto a partir do estoque geral que já existia (apenas 1x)
        cursor.execute("SELECT COUNT(*) FROM estoque_produto")
        count = cursor.fetchone()
        qtd = int(count[0]) if count else 0
        if qtd == 0:
            cursor.execute(
                """INSERT INTO estoque_produto (ean, loja, quantidade_estoque, lote, data_vencimento)
                   SELECT ean, 'RTJ', quantidade_estoque, lote, data_vencimento
                   FROM produtos WHERE COALESCE(quantidade_estoque, 0) > 0""")
        conn.commit()
    finally:
        devolver_conexao(conn)
    return True