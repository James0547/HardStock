import bcrypt
import sqlite3
import secrets
from typing import Optional
from database import DB_NAME

def debug_auth_state():
    """Debug function to check auth state"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'owner'")
    owner_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM shop_details")
    shop_count = cursor.fetchone()[0]
    conn.close()
    print(f"DEBUG: owner_exists={owner_count > 0}, shop_exists={shop_count > 0}")
    return owner_count > 0, shop_count > 0

def verify_receipt_deletion_password(password: str) -> bool:
    """Verify password for receipt deletion (same as owner password)"""
    return verify_owner_password(password)

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def check_first_time_setup() -> bool:
    """Check if this is first time running the app"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Check if there's a REAL owner (not placeholder)
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'owner'")
    count = cursor.fetchone()[0]
    conn.close()
    return count == 0

def verify_developer_password(password: str) -> bool:
    """Verify the developer setup password"""
    return password == "HardStock@2024"

def create_owner_password(password: str):
    """Create shop owner's password after setup"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    hashed = hash_password(password)
    
    # Delete placeholder if exists
    cursor.execute("DELETE FROM users WHERE username = 'placeholder'")
    
    # Check if owner already exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'owner'")
    if cursor.fetchone()[0] > 0:
        cursor.execute("UPDATE users SET password_hash = ?, is_setup_complete = 1 WHERE username = 'owner'", (hashed,))
    else:
        cursor.execute(
            "INSERT INTO users (username, password_hash, is_setup_complete) VALUES (?, ?, ?)",
            ("owner", hashed, 1)
        )
    
    conn.commit()
    conn.close()

def verify_owner_password(password: str) -> bool:
    """Verify shop owner's password"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = 'owner'")
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0] and result[0] != "placeholder":
        try:
            return verify_password(password, result[0])
        except:
            return False
    return False

def check_shop_setup() -> bool:
    """Check if shop details have been registered"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM shop_details")
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

def get_shop_details():
    """Get shop details"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT shop_name, location, phone FROM shop_details ORDER BY id DESC LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "shop_name": result[0],
            "location": result[1],
            "phone": result[2]
        }
    return None

def create_money_vault_password(password: str):
    """Create password for money vault"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    hashed = hash_password(password)
    
    # Check if vault password exists
    cursor.execute("SELECT COUNT(*) FROM money_vault")
    count = cursor.fetchone()[0]
    
    if count == 0:
        cursor.execute("INSERT INTO money_vault (id, vault_password_hash) VALUES (1, ?)", (hashed,))
    else:
        cursor.execute("UPDATE money_vault SET vault_password_hash = ?, last_updated = CURRENT_TIMESTAMP WHERE id = 1", (hashed,))
    
    conn.commit()
    conn.close()

def verify_vault_password(password: str) -> bool:
    """Verify money vault password"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT vault_password_hash FROM money_vault WHERE id = 1")
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        try:
            return verify_password(password, result[0])
        except:
            return False
    return False

def update_vault_password(old_password: str, new_password: str) -> bool:
    """Update vault password with recovery"""
    if verify_vault_password(old_password):
        create_money_vault_password(new_password)
        return True
    return False

# Password recovery secret
RECOVERY_SECRET = "HardStockMasterKey2024"

def recover_vault_password(recovery_code: str) -> Optional[str]:
    """Recover vault password using master recovery code"""
    if recovery_code == RECOVERY_SECRET:
        # Generate temporary password
        temp_password = secrets.token_urlsafe(8)
        create_money_vault_password(temp_password)
        return temp_password
    return None