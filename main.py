from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import secrets
import json
import os
import sys

from database import init_database, get_db
from auth import *

# Initialize database
init_database()

# Create FastAPI app FIRST
app = FastAPI(title="HardStock")

# Set up paths for bundled app
def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Setup templates and static files AFTER app is created
if getattr(sys, 'frozen', False):
    templates_dir = get_resource_path('templates')
    static_dir = get_resource_path('static')
    templates = Jinja2Templates(directory=templates_dir)
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    templates = Jinja2Templates(directory="templates")
    if os.path.exists("static"):
        app.mount("/static", StaticFiles(directory="static"), name="static")

# Session middleware
app.add_middleware(SessionMiddleware, secret_key=secrets.token_urlsafe(32))

def render_template(template_name: str, request: Request, **kwargs):
    return templates.TemplateResponse(template_name, {
        "request": request,
        **kwargs
    })

def is_logged_in(request: Request):
    return request.session.get("logged_in", False)

print("=== DATABASE STATE ON STARTUP ===")
print(f"First time setup: {check_first_time_setup()}")
print(f"Shop setup: {check_shop_setup()}")
print("=================================")

# ========== ROOT ==========
@app.get("/")
async def root(request: Request):
    if check_first_time_setup():
        return RedirectResponse(url="/setup", status_code=302)
    if not check_shop_setup():
        return RedirectResponse(url="/register-shop", status_code=302)
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/dashboard", status_code=302)

# ========== SETUP ==========
@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    if not check_first_time_setup():
        if not check_shop_setup():
            return RedirectResponse(url="/register-shop", status_code=302)
        return RedirectResponse(url="/login", status_code=302)
    return render_template("setup.html", request)

@app.post("/verify-setup")
async def verify_setup(request: Request, password: str = Form(...)):
    if verify_developer_password(password):
        request.session["dev_verified"] = True
        return RedirectResponse(url="/register-shop", status_code=302)
    return render_template("setup.html", request, error="Invalid developer password")

# ========== REGISTER SHOP ==========
@app.get("/register-shop", response_class=HTMLResponse)
async def register_shop_page(request: Request):
    if check_shop_setup():
        return RedirectResponse(url="/login", status_code=302)
    if not request.session.get("dev_verified"):
        return RedirectResponse(url="/setup", status_code=302)
    return render_template("register_shop.html", request)

@app.post("/register-shop")
async def register_shop(
    request: Request,
    shop_name: str = Form(...),
    location: str = Form(...),
    phone: str = Form(...),
    owner_password: str = Form(...),
    confirm_password: str = Form(...)
):
    if owner_password != confirm_password:
        return render_template("register_shop.html", request, error="Passwords do not match",
                              shop_name=shop_name, location=location, phone=phone)
    if len(owner_password) < 4:
        return render_template("register_shop.html", request, error="Password too short (min 4 chars)",
                              shop_name=shop_name, location=location, phone=phone)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO shop_details (shop_name, location, phone) VALUES (?, ?, ?)",
                       (shop_name, location, phone))
    
    create_owner_password(owner_password)
    create_money_vault_password(owner_password)
    
    request.session["logged_in"] = True
    request.session["dev_verified"] = False
    
    return RedirectResponse(url="/dashboard", status_code=302)

# ========== LOGIN ==========
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_logged_in(request):
        return RedirectResponse(url="/dashboard", status_code=302)
    if check_first_time_setup():
        return RedirectResponse(url="/setup", status_code=302)
    if not check_shop_setup():
        return RedirectResponse(url="/register-shop", status_code=302)
    return render_template("login.html", request)

@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if verify_owner_password(password):
        request.session["logged_in"] = True
        return RedirectResponse(url="/dashboard", status_code=302)
    return render_template("login.html", request, error="Invalid password")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)

# ========== DASHBOARD ==========
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    shop = get_shop_details()
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COALESCE(SUM(quantity), 0) as total FROM products")
        total_products = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(price * quantity), 0) as total_value FROM products")
        total_stock_value = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) as count FROM categories")
        total_categories = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE DATE(sale_date) = DATE('now')")
        today_sales = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT p.id, p.name, p.quantity, c.name as category_name
            FROM products p JOIN categories c ON p.category_id = c.id
            WHERE p.quantity < 10 ORDER BY p.quantity ASC LIMIT 10
        """)
        low_stock = cursor.fetchall()
        
        cursor.execute("SELECT id, sale_date, customer_name, total_amount FROM sales ORDER BY sale_date DESC LIMIT 5")
        recent_sales = cursor.fetchall()
    
    return render_template("dashboard.html", request, shop=shop, total_products=total_products,
                          total_categories=total_categories, today_sales=today_sales,
                          low_stock=low_stock, recent_sales=recent_sales,
                          total_stock_value=total_stock_value)

# ========== CATEGORIES ==========
@app.get("/categories", response_class=HTMLResponse)
async def categories_page(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories ORDER BY name")
        categories = cursor.fetchall()
    return render_template("categories.html", request, categories=categories)

@app.post("/add-category")
async def add_category(request: Request, category_name: str = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO categories (name) VALUES (?)", (category_name.strip(),))
            return RedirectResponse(url="/categories?success=added", status_code=302)
        except:
            return RedirectResponse(url="/categories?error=exists", status_code=302)

@app.post("/delete-category/{category_id}")
async def delete_category(request: Request, category_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return RedirectResponse(url="/categories?success=deleted", status_code=302)

# ========== PRODUCTS ==========
@app.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, c.name as category_name FROM products p
            JOIN categories c ON p.category_id = c.id ORDER BY p.name
        """)
        products = cursor.fetchall()
        cursor.execute("SELECT * FROM categories ORDER BY name")
        categories = cursor.fetchall()
        
        cursor.execute("SELECT COALESCE(SUM(quantity), 0) as total_quantity FROM products")
        total_quantity = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(price * quantity), 0) as total_value FROM products")
        total_value = cursor.fetchone()[0]
    
    return render_template("products.html", request, products=products, categories=categories,
                          total_quantity=total_quantity, total_value=total_value)

@app.post("/add-product")
async def add_product(request: Request, product_name: str = Form(...), category_id: int = Form(...),
                      price: float = Form(...), quantity: int = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (name, category_id, price, quantity) VALUES (?, ?, ?, ?)",
                       (product_name.strip(), category_id, price, quantity))
    return RedirectResponse(url="/products?success=added", status_code=302)

@app.post("/edit-product/{product_id}")
async def edit_product(request: Request, product_id: int, product_name: str = Form(...),
                       category_id: int = Form(...), price: float = Form(...), quantity: int = Form(...)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE products SET name=?, category_id=?, price=?, quantity=? WHERE id=?",
                       (product_name.strip(), category_id, price, quantity, product_id))
    return RedirectResponse(url="/products?success=updated", status_code=302)

@app.post("/delete-product/{product_id}")
async def delete_product(request: Request, product_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return RedirectResponse(url="/products?success=deleted", status_code=302)

# ========== POS ==========
@app.get("/pos", response_class=HTMLResponse)
async def pos_page(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.id, p.name, p.price, p.quantity, c.name as category_name
            FROM products p JOIN categories c ON p.category_id = c.id
            WHERE p.quantity > 0 ORDER BY p.name
        """)
        products = cursor.fetchall()
        cursor.execute("SELECT * FROM categories ORDER BY name")
        categories = cursor.fetchall()
    return render_template("pos.html", request, products=products, categories=categories)

@app.post("/process-sale")
async def process_sale(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    form_data = await request.form()
    customer_name = form_data.get("customer_name", "Walk-in Customer")
    customer_company = form_data.get("customer_company", "")
    cart_items_str = form_data.get("cart_items")
    
    if not cart_items_str:
        return RedirectResponse(url="/pos?error=Cart empty", status_code=302)
    
    cart_items = json.loads(cart_items_str)
    if not cart_items:
        return RedirectResponse(url="/pos?error=Cart empty", status_code=302)
    
    # Calculate totals
    subtotal = sum(item["total"] for item in cart_items)
    total_quantity = sum(item["quantity"] for item in cart_items)
    total_amount = subtotal
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO sales (customer_name, customer_company, total_amount, developer_fee, net_amount)
                          VALUES (?, ?, ?, ?, ?)""", (customer_name, customer_company, total_amount, 0, total_amount))
        sale_id = cursor.lastrowid
        
        for item in cart_items:
            cursor.execute("""INSERT INTO sale_items (sale_id, product_id, product_name, category_name, quantity, unit_price, total_price)
                              VALUES (?, ?, ?, ?, ?, ?, ?)""", (sale_id, item["id"], item["name"], item["category"], item["quantity"], item["price"], item["total"]))
            cursor.execute("UPDATE products SET quantity = quantity - ? WHERE id = ?", (item["quantity"], item["id"]))
            cursor.execute("""INSERT INTO vault_transactions (sale_id, amount, category_name, description)
                              VALUES (?, ?, ?, ?)""", (sale_id, item["total"], item["category"], f"Sale of {item['quantity']} x {item['name']}"))
    
    return RedirectResponse(url=f"/receipt/{sale_id}?total_qty={total_quantity}", status_code=302)

# ========== RECEIPT ==========
@app.get("/receipt/{sale_id}", response_class=HTMLResponse)
async def receipt_page(request: Request, sale_id: int):
    shop = get_shop_details()
    total_quantity = request.query_params.get("total_qty", 0)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sales WHERE id = ?", (sale_id,))
        sale = cursor.fetchone()
        cursor.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,))
        items = cursor.fetchall()
    
    return render_template("receipt.html", request, shop=shop, sale=sale, items=items, 
                          total_quantity=total_quantity)

# ========== RECEIPT MANAGEMENT ==========
@app.get("/receipt-management", response_class=HTMLResponse)
async def receipt_management_page(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    success_message = None
    if request.query_params.get("success") == "all_deleted":
        success_message = "✓ All receipts have been permanently deleted!"
    elif request.query_params.get("success") == "deleted":
        success_message = "✓ Receipt permanently deleted!"
    
    return render_template("receipt_management.html", request, success_message=success_message)

@app.post("/verify-receipt-password")
async def verify_receipt_password(request: Request, password: str = Form(...)):
    if verify_owner_password(password):
        request.session["receipt_deletion_allowed"] = True
        return RedirectResponse(url="/receipt-list", status_code=302)
    return render_template("receipt_management.html", request, error="Invalid password")

@app.get("/receipt-list", response_class=HTMLResponse)
async def receipt_list_page(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    if not request.session.get("receipt_deletion_allowed"):
        return RedirectResponse(url="/receipt-management", status_code=302)
    
    success_message = None
    if request.query_params.get("success") == "deleted":
        success_message = "✓ Receipt permanently deleted!"
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.sale_date, s.customer_name, s.customer_company, s.total_amount,
                   COUNT(si.id) as item_count
            FROM sales s
            LEFT JOIN sale_items si ON s.id = si.sale_id
            GROUP BY s.id
            ORDER BY s.sale_date DESC
        """)
        receipts = cursor.fetchall()
    
    return render_template("receipt_list.html", request, receipts=receipts, success_message=success_message)

@app.post("/delete-receipt/{receipt_id}")
async def delete_receipt(request: Request, receipt_id: int):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    if not request.session.get("receipt_deletion_allowed"):
        return RedirectResponse(url="/receipt-management", status_code=302)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sale_items WHERE sale_id = ?", (receipt_id,))
        cursor.execute("DELETE FROM vault_transactions WHERE sale_id = ?", (receipt_id,))
        cursor.execute("DELETE FROM sales WHERE id = ?", (receipt_id,))
    
    return RedirectResponse(url="/receipt-list?success=deleted", status_code=302)

@app.post("/delete-all-receipts")
async def delete_all_receipts(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    if not request.session.get("receipt_deletion_allowed"):
        return RedirectResponse(url="/receipt-management", status_code=302)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sale_items")
        cursor.execute("DELETE FROM vault_transactions")
        cursor.execute("DELETE FROM sales")
    
    request.session["receipt_deletion_allowed"] = False
    return RedirectResponse(url="/receipt-management?success=all_deleted", status_code=302)

@app.get("/receipt-deletion-logout")
async def receipt_deletion_logout(request: Request):
    request.session["receipt_deletion_allowed"] = False
    return RedirectResponse(url="/receipt-management", status_code=302)

# ========== REPORTS ==========
@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    return render_template("reports.html", request)

@app.get("/api/sales-report")
async def get_sales_report(request: Request, period: str):
    if period == "daily":
        date_filter = "DATE(sale_date) = DATE('now')"
    elif period == "weekly":
        date_filter = "sale_date >= DATE('now', '-7 days')"
    elif period == "monthly":
        date_filter = "sale_date >= DATE('now', 'start of month')"
    else:
        date_filter = "sale_date >= DATE('now', 'start of year')"
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT s.id, s.sale_date, s.customer_name, s.customer_company, s.total_amount,
                   GROUP_CONCAT(si.product_name || ' (x' || si.quantity || ')', ', ') as items
            FROM sales s 
            LEFT JOIN sale_items si ON s.id = si.sale_id
            WHERE {date_filter} 
            GROUP BY s.id 
            ORDER BY s.sale_date DESC
        """)
        sales = cursor.fetchall()
        
        cursor.execute(f"""
            SELECT 
                COALESCE(SUM(total_amount), 0) as total_sales, 
                COUNT(*) as total_transactions
            FROM sales WHERE {date_filter}
        """)
        totals = cursor.fetchone()
        
        cursor.execute(f"""
            SELECT si.category_name, COALESCE(SUM(si.total_price), 0) as total
            FROM sale_items si
            JOIN sales s ON si.sale_id = s.id
            WHERE {date_filter}
            GROUP BY si.category_name
            ORDER BY total DESC
        """)
        category_sales = cursor.fetchall()
    
    return {
        "sales": [dict(s) for s in sales],
        "totals": dict(totals),
        "category_sales": [dict(c) for c in category_sales]
    }

# ========== MONEY VAULT ==========
@app.get("/money-vault", response_class=HTMLResponse)
async def money_vault_login_page(request: Request):
    return render_template("money_vault_login.html", request)

@app.post("/money-vault/verify")
async def verify_money_vault(request: Request, password: str = Form(...)):
    if verify_vault_password(password):
        request.session["vault_accessed"] = True
        return RedirectResponse(url="/money-vault/dashboard", status_code=302)
    return render_template("money_vault_login.html", request, error="Invalid password")

@app.get("/money-vault/dashboard", response_class=HTMLResponse)
async def money_vault_dashboard(request: Request):
    if not request.session.get("vault_accessed"):
        return RedirectResponse(url="/money-vault", status_code=302)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get all sales grouped by receipt
        cursor.execute("""
            SELECT 
                s.id as sale_id,
                s.sale_date,
                s.customer_name,
                s.customer_company,
                s.total_amount,
                COUNT(si.id) as item_count
            FROM sales s
            LEFT JOIN sale_items si ON s.id = si.sale_id
            GROUP BY s.id
            ORDER BY s.sale_date DESC
        """)
        sales = cursor.fetchall()
        
        # Build grouped transactions
        grouped_transactions = []
        for sale in sales:
            # Get product items for this specific sale
            cursor.execute("""
                SELECT 
                    product_name,
                    category_name,
                    quantity,
                    unit_price,
                    total_price
                FROM sale_items
                WHERE sale_id = ?
            """, (sale['sale_id'],))
            product_data = cursor.fetchall()
            
            # Create product items list
            product_items_list = []
            for item in product_data:
                product_items_list.append({
                    'product_name': str(item['product_name']),
                    'category_name': str(item['category_name']),
                    'quantity': int(item['quantity']),
                    'unit_price': float(item['unit_price']),
                    'total_price': float(item['total_price'])
                })
            
            # Format date
            sale_date = str(sale['sale_date'])
            date_parts = sale_date.split(' ')
            date_part = date_parts[0] if len(date_parts) > 0 else sale_date
            time_part = date_parts[1] if len(date_parts) > 1 else ''
            
            grouped_transactions.append({
                'sale_id': int(sale['sale_id']),
                'date': str(date_part),
                'time': str(time_part),
                'customer_name': str(sale['customer_name']) if sale['customer_name'] else 'Walk-in Customer',
                'customer_company': str(sale['customer_company']) if sale['customer_company'] else '',
                'total_amount': float(sale['total_amount']),
                'item_count': int(sale['item_count']),
                'product_items': product_items_list  # Changed from 'items' to 'product_items'
            })
        
        # Get total revenue
        cursor.execute("SELECT COALESCE(SUM(amount), 0) as total_revenue FROM vault_transactions")
        total_row = cursor.fetchone()
        total_revenue = float(total_row[0]) if total_row else 0
        
        # Get category totals
        cursor.execute("""
            SELECT 
                category_name, 
                COALESCE(SUM(amount), 0) as total 
            FROM vault_transactions 
            WHERE category_name IS NOT NULL AND category_name != ''
            GROUP BY category_name 
            ORDER BY total DESC
        """)
        category_data = cursor.fetchall()
        
        category_totals = []
        for cat in category_data:
            category_totals.append({
                'category_name': str(cat['category_name']),
                'total': float(cat['total'])
            })
        
        totals = {
            "total_revenue": total_revenue,
            "total_transactions": len(grouped_transactions)
        }
    
    return render_template("money_vault_dashboard.html", request, 
                          grouped_transactions=grouped_transactions,
                          totals=totals, 
                          category_totals=category_totals)
    
# Add to imports at the top
import csv
import io
from fastapi.responses import StreamingResponse

# ========== EXPORT TO EXCEL ==========
@app.get("/export/sales")
async def export_sales_to_excel(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                s.id as 'Receipt #',
                s.sale_date as 'Date',
                s.customer_name as 'Customer',
                s.customer_company as 'Company',
                s.total_amount as 'Total Amount (GH₵)',
                COUNT(si.id) as 'Items Count'
            FROM sales s
            LEFT JOIN sale_items si ON s.id = si.sale_id
            GROUP BY s.id
            ORDER BY s.sale_date DESC
        """)
        sales = cursor.fetchall()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    if sales:
        writer.writerow(sales[0].keys())
        # Write data
        for sale in sales:
            writer.writerow(list(sale))
    
    # Return as Excel/CSV
    response = StreamingResponse(
        iter([output.getvalue().encode('utf-8-sig')]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hardstock_sales_report.csv"}
    )
    return response

@app.get("/export/products")
async def export_products_to_excel(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                p.name as 'Product Name',
                c.name as 'Category',
                p.price as 'Price (GH₵)',
                p.quantity as 'Stock Quantity',
                (p.price * p.quantity) as 'Total Value (GH₵)'
            FROM products p
            JOIN categories c ON p.category_id = c.id
            ORDER BY p.name
        """)
        products = cursor.fetchall()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    if products:
        writer.writerow(products[0].keys())
        for product in products:
            writer.writerow(list(product))
    
    response = StreamingResponse(
        iter([output.getvalue().encode('utf-8-sig')]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hardstock_products.csv"}
    )
    return response

# ========== BACKUP SYSTEM ==========
import shutil
from datetime import datetime
import zipfile

@app.get("/backup")
async def backup_database(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    
    # Password verification for backup
    return render_template("backup.html", request)

@app.post("/verify-backup-password")
async def verify_backup_password(request: Request, password: str = Form(...)):
    if verify_owner_password(password):
        request.session["backup_allowed"] = True
        return RedirectResponse(url="/perform-backup", status_code=302)
    return render_template("backup.html", request, error="Invalid password")

@app.get("/perform-backup")
async def perform_backup(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)
    if not request.session.get("backup_allowed"):
        return RedirectResponse(url="/backup", status_code=302)
    
    # Get database path
    from database import DB_NAME
    import os
    
    # Create backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"HardStock_Backup_{timestamp}"
    
    # Get Downloads folder path
    downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
    backup_folder = os.path.join(downloads_path, backup_filename)
    
    # Create backup folder
    os.makedirs(backup_folder, exist_ok=True)
    
    # Copy database file
    if os.path.exists(DB_NAME):
        shutil.copy2(DB_NAME, os.path.join(backup_folder, "hardstock.db"))
    
    # Export all data to CSV
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Export sales
        cursor.execute("SELECT * FROM sales")
        sales = cursor.fetchall()
        if sales:
            export_to_csv(sales, os.path.join(backup_folder, "sales_backup.csv"))
        
        # Export products
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()
        if products:
            export_to_csv(products, os.path.join(backup_folder, "products_backup.csv"))
        
        # Export categories
        cursor.execute("SELECT * FROM categories")
        categories = cursor.fetchall()
        if categories:
            export_to_csv(categories, os.path.join(backup_folder, "categories_backup.csv"))
        
        # Export customers/shop details
        cursor.execute("SELECT * FROM shop_details")
        shops = cursor.fetchall()
        if shops:
            export_to_csv(shops, os.path.join(backup_folder, "shop_details_backup.csv"))
    
    # Create zip file
    zip_path = os.path.join(downloads_path, f"{backup_filename}.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(backup_folder):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, backup_folder)
                zipf.write(file_path, arcname)
    
    # Clean up temporary folder
    shutil.rmtree(backup_folder)
    
    # Clear session flag
    request.session["backup_allowed"] = False
    
    # Return success page with download link
    return render_template("backup_success.html", request, 
                          backup_file=f"{backup_filename}.zip",
                          download_path=zip_path)

def export_to_csv(data, filename):
    """Helper function to export query results to CSV"""
    import csv
    if not data:
        return
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
        if data:
            writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
            writer.writeheader()
            for row in data:
                writer.writerow(dict(row))

@app.get("/money-vault/logout")
async def money_vault_logout(request: Request):
    request.session["vault_accessed"] = False
    return RedirectResponse(url="/money-vault", status_code=302)

# ========== PASSWORD RECOVERY ==========
@app.get("/recover-password", response_class=HTMLResponse)
async def recover_password_page(request: Request):
    return render_template("recover_password.html", request)

@app.post("/do-recover-password")
async def do_recover_password(request: Request, recovery_code: str = Form(...)):
    if recovery_code == "HardStockMasterKey2024":
        import random, string
        temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        create_owner_password(temp_password)
        create_money_vault_password(temp_password)
        return render_template("recover_password.html", request, success=True, temp_password=temp_password)
    return render_template("recover_password.html", request, error="Invalid recovery code")

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("HardStock Hardware Shop System")
    print("=" * 50)
    print("URL: http://127.0.0.1:8000")
    print("Developer Password: HardStock@2024")
    print("Recovery Code: HardStockMasterKey2024")
    print("=" * 50)
    uvicorn.run(app, host="127.0.0.1", port=8000)