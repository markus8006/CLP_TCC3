import psycopg2
conn = psycopg2.connect(
    dbname='scada',
    user='postgres',
    password='postgres',  # se você usou outra senha, troque aqui
    host='localhost',
    port=5432
)
print("Conectado com sucesso!")
conn.close()
