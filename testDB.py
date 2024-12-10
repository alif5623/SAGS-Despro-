import sqlite3
from sqlite3 import Error

database = "SAGS.db"
    
# Create a database connection
def create_connection(db_file):
    """Create a database connection to SQLite database"""
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        print(f"Successfully connected to SQLite version {sqlite3.version}")
        return conn
    except Error as e:
        print(f"Error connecting to database: {e}")
    return conn

conn = create_connection(database)
query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
# Execute the query
if conn:
    try:
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()  # Fetch all rows from the query result
        for row in rows:
            print(row)  # Print each row
    except sqlite3.Error as e:
        print(f"Error executing query: {e}")