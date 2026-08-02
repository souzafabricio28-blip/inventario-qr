import os
import json
from datetime import datetime


def formatar_data(dt_str):
    if not dt_str:
        return "-"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(dt_str)


def exportar_json(dados, filename="export.json"):
    pasta = os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
    os.makedirs(pasta, exist_ok=True)
    path = os.path.join(pasta, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, default=str)
    return path


def limpar_tela():
    os.system("cls" if os.name == "nt" else "clear")


def exibir_cabecalho(titulo):
    limpar_tela()
    print("=" * 60)
    print(f"  {titulo}")
    print("=" * 60)
