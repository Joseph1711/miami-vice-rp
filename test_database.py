"""Prueba la conexión directa a Supabase PostgreSQL del bot.

Ejecutar con: python test_database.py
"""
from bot.db import DATABASE_URL, check_connection, execute, connection_label


def main():
    print("=" * 60)
    print("  MIAMI VICE — PRUEBA DE CONEXIÓN A SUPABASE POSTGRESQL")
    print("=" * 60)
    print(f"\n[INFO] Backend: {connection_label()}")

    result = check_connection()
    if not result["ok"]:
        print(f"\n[ERROR] No se pudo conectar a Supabase: {result['error']}")
        raise SystemExit(1)

    print("[OK] Conexión SSL/TLS a Supabase PostgreSQL establecida correctamente")
    print(f"[OK] SELECT 1 → {execute('SELECT 1 AS resultado', fetch='one')}")
    tables = execute(
        "SELECT COUNT(*) AS total FROM information_schema.tables WHERE table_schema = 'public'",
        fetch="one",
    )
    total_tables = tables["total"] if tables else 0
    print(f"[INFO] Tablas públicas en Supabase: {total_tables}")
    print("\n" + "=" * 60)
    print("  RESULTADO: SUPABASE POSTGRESQL OPERATIVO Y CONECTADO ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
