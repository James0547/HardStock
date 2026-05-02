import sqlite3
import os
import sys
from contextlib import contextmanager

def get_db_path():
    """Get database path - saves in the same folder as the EXE"""
    if getattr(sys, 'frozen', False):
        # Running as compiled EXE
        application_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        application_path = os.path.dirname(os.path.abspath(__file__))
    
    # Create the database in the application folder
    db_path = os.path.join(application_path, 'hardstock.db')
    print(f"Database path: {db_path}")  # For debugging
    return db_path

DB_NAME = get_db_path()

def init_database():
    """Initialize all database tables"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_setup_complete INTEGER DEFAULT 0
        )
    ''')
    
    # Shop details table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shop_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,
            location TEXT NOT NULL,
            phone TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            price REAL NOT NULL,
            quantity INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    ''')
    
    # Sales table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            customer_name TEXT,
            customer_company TEXT,
            total_amount REAL,
            developer_fee REAL,
            net_amount REAL
        )
    ''')
    
    # Sale items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER,
            product_id INTEGER,
            product_name TEXT,
            category_name TEXT,
            quantity INTEGER,
            unit_price REAL,
            total_price REAL,
            FOREIGN KEY (sale_id) REFERENCES sales(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')
    
    # Money vault table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS money_vault (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            vault_password_hash TEXT NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Vault transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vault_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sale_id INTEGER,
            amount REAL,
            category_name TEXT,
            description TEXT,
            FOREIGN KEY (sale_id) REFERENCES sales(id)
        )
    ''')
    
    # Developer fees table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS developer_fees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER,
            fee_amount REAL,
            collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sale_id) REFERENCES sales(id)
        )
    ''')
    
    # Insert default category if none exists
    cursor.execute("SELECT COUNT(*) FROM categories")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO categories (name) VALUES (?)", ("General",))
    
    conn.commit()
    conn.close()
    print(f"Database initialized at: {DB_NAME}")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()