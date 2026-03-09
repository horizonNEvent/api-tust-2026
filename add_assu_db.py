import sqlite3

conn = sqlite3.connect('sql_app.db')
cursor = conn.cursor()

try:
    cursor.execute("""
        INSERT INTO robot_configs (label, robot_type, base, agents_json, username, password) 
        VALUES ('ASSU_AE_LIBRA', 'assu', 'AE', '{"8011": "LIBRA"}', '', '')
    """)
    conn.commit()
    print("Robô ASSU inserido no banco de dados!")
except Exception as e:
    print(f"Aviso: {e} - Talvez já exista.")
finally:
    conn.close()
