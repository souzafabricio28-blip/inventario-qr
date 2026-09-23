#!/usr/bin/env python3
import os
from dotenv import load_dotenv
load_dotenv()

from database.db_pg import get_db

with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT id, usuario, ativo FROM usuarios ORDER BY id")
    for r in cur.fetchall():
        print(f"ID: {r[0]} | Usuario: {r[1]} | Ativo: {r[2]}")
