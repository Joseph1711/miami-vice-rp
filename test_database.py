"""Prueba la base SQLite local del bot.

Ejecutar con: python test_database.py
"""
from bot.db import DB_PATH, check_connection, execute


def main():
    print("=" * 55)
    print("  MIAMI VICE — PRUEBA DE BASE DE DATOS LOCAL")
    print("=" * 55)
    print(f"\n[INFO] Archivo SQLite: {DB_PATH}")

    from scripts.init_db import init_db
    init_db()
    result = check_connection()
    if not result["ok"]:
        print(f"\n[ERROR] No se pudo abrir SQLite: {result['error']}")
        raise SystemExit(1)

    print("[OK] Conexión SQLite establecida correctamente")
    print(f"[OK] SELECT 1 → {execute('SELECT 1 AS resultado', fetch='one')}")
    tables = execute(
        "SELECT COUNT(*) AS total FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%'",
        fetch="one",
    )
    print(f"[INFO] Tablas del bot: {tables['total']}")
    print("\n" + "=" * 55)
    print("  RESULTADO: BASE LOCAL OPERATIVA ✓")
    print("=" * 55)


if __name__ == "__main__":
    main()