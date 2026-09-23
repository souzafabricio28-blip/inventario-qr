"""Baixa o banco Neon (PostgreSQL) para SQLite local + dump JSON."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except ImportError:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

from database.schema import criar_tabelas, get_db_path

# Ordem respeitando FKs (pais antes de filhos)
ORDEM_TABELAS = [
    "usuarios",
    "produtos",
    "config",
    "sessoes_inventario",
    "recebimentos_nf",
    "itens_recebimento",
    "inventario_contagem",
    "validacoes_base",
    "saidas_estoque",
]


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, memoryview):
        return bytes(obj).hex()
    if isinstance(obj, bytes):
        return obj.hex()
    raise TypeError(type(obj).__name__)


def _cell(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=_json_default)
    if isinstance(v, memoryview):
        return bytes(v)
    return v


def main():
    url = os.environ.get("DATABASE_URL", "").replace("&channel_binding=require", "")
    if not url:
        print("ERRO: DATABASE_URL nao encontrada no .env")
        sys.exit(1)

    print("Conectando ao Neon...")
    pg = psycopg2.connect(url, cursor_factory=RealDictCursor, connect_timeout=60)
    cur = pg.cursor()

    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    )
    existentes = [r["table_name"] for r in cur.fetchall()]
    print("Tabelas no Neon:", ", ".join(existentes) or "(nenhuma)")

    tabelas = [t for t in ORDEM_TABELAS if t in existentes]
    extras = [t for t in existentes if t not in ORDEM_TABELAS]
    tabelas.extend(extras)

    dump = {}
    for t in tabelas:
        cur.execute(f'SELECT * FROM "{t}"')
        rows = cur.fetchall()
        dump[t] = [dict(r) for r in rows]
        print(f"  {t}: {len(rows)} linhas")

    pg.close()

    backups = ROOT / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = backups / f"neon_dump_{stamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=2, default=_json_default)
    print(f"JSON salvo: {json_path}")

    db_path = Path(get_db_path())
    if db_path.exists():
        bak = backups / f"inventario_antes_neon_{stamp}.db"
        shutil.copy2(db_path, bak)
        print(f"Backup local anterior: {bak}")
        db_path.unlink()

    # Sem DATABASE_URL o schema SQLite e usado
    os.environ.pop("DATABASE_URL", None)
    criar_tabelas()

    sq = sqlite3.connect(str(db_path))
    sq.execute("PRAGMA foreign_keys=OFF")
    sq_cur = sq.cursor()

    total = 0
    for t in tabelas:
        rows = dump[t]
        if not rows:
            continue
        cols_pg = list(rows[0].keys())
        info = sq_cur.execute(f"PRAGMA table_info({t})").fetchall()
        if not info:
            print(f"  AVISO: tabela {t} nao existe no SQLite local — pulando")
            continue
        cols_sq = {r[1] for r in info}
        cols = [c for c in cols_pg if c in cols_sq]
        if not cols:
            print(f"  AVISO: sem colunas em comum em {t} — pulando")
            continue
        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join(cols)
        sql = f"INSERT INTO {t} ({col_list}) VALUES ({placeholders})"
        data = [tuple(_cell(row[c]) for c in cols) for row in rows]
        sq_cur.executemany(sql, data)
        total += len(data)
        print(f"  SQLite {t}: {len(data)} inseridas")

    sq.commit()
    sq.execute("PRAGMA foreign_keys=ON")
    sq.close()

    print(f"\nOK: {total} registros gravados em {db_path}")
    print("Pronto para usar localmente (sem DATABASE_URL no ambiente).")


if __name__ == "__main__":
    main()
