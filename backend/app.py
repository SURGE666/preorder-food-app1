import os
import mysql.connector
from mysql.connector import Error
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from passlib.hash import pbkdf2_sha256 as sha256 # Password hashing
from dotenv import load_dotenv
import datetime

load_dotenv() # Load environment variables from .env file

app = Flask(__name__)
CORS(app) # Allow requests from frontend (different origin)

# Configuration from environment variables
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', 'uploads')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Optional: Limit upload size (16MB)

# Ensure the upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# --- Database Connection ---


def get_db_connection():
    try:
        db_host = os.getenv('DATABASE_HOST') # Get the value
        db_user = os.getenv('DATABASE_USER')
        db_pass = os.getenv('DATABASE_PASSWORD')
        db_name = os.getenv('DATABASE_DB')

        # --- ADD THIS LINE FOR DEBUGGING ---
        print(f"DEBUG: Connecting with host={db_host}, user={db_user}, db={db_name}")
        # ------------------------------------

        conn = mysql.connector.connect(
            host=db_host,            # Use the variable
            user=db_user,
            password=db_pass,
            database=db_name,
        )
        # print("DB Connection Successful")
        return conn
    except Error as e:
        print(f"Error connecting to MySQL Database: {e}")
        return None
    # No finally block needed here as connection closing happens in the route

# --- Helper Functions ---
def hash_password(password):
    return sha256.hash(password)

def verify_password(stored_password_hash, provided_password):
    return sha256.verify(provided_password, stored_password_hash)

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
# Add this inside backend/app.py

@app.route('/')
def index():
    return "Flask Backend is Running!"

# --- API Endpoints ---
# (Keep your existing /api/... routes below this)
# ...
# --- API Endpoints ---

# User Authentication
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role') # 'student' or 'canteen'

    if not username or not password or not role:
        return jsonify({'message': 'Missing username, password, or role'}), 400
    if role not in ['student', 'canteen']:
         return jsonify({'message': 'Invalid role specified'}), 400

    hashed_password = hash_password(password)
    conn = get_db_connection()
    if not conn: return jsonify({'message': 'Database connection failed'}), 500
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return jsonify({'message': 'Username already exists'}), 409 # Conflict

        cursor.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            (username, hashed_password, role)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return jsonify({'message': 'User registered successfully', 'user_id': user_id}), 201
    except Error as e:
        conn.rollback()
        print(f"Error during registration: {e}")
        return jsonify({'message': 'Registration failed'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Missing username or password'}), 400

    conn = get_db_connection()
    if not conn: return jsonify({'message': 'Database connection failed'}), 500
    # Use dictionary=True to get results as dicts
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT id, username, password_hash, role FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user and verify_password(user['password_hash'], password):
            # Login successful
            # In a real app, you'd issue a token (JWT) here instead of just sending user info
            return jsonify({
                'message': 'Login successful',
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'role': user['role']
                }
            }), 200
        else:
            # Invalid credentials
            return jsonify({'message': 'Invalid username or password'}), 401
    except Error as e:
        print(f"Error during login: {e}")
        return jsonify({'message': 'Login failed'}), 500
    finally:
        cursor.close()
        conn.close()

# Menu Management (Canteen)
@app.route('/api/menu', methods=['POST'])
def add_menu_item():
    # TODO: Add authentication check - only canteen users should access this
    data = request.form # Use request.form because we might receive image data
    name = data.get('name')
    description = data.get('description')
    price = data.get('price')
    image_path = None

    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(filepath)
                image_path = filename # Store only the filename
            except Exception as e:
                 print(f"Error saving file: {e}")
                 return jsonify({'message': 'Failed to save image'}), 500
        elif file.filename != '': # File uploaded but not allowed type
             return jsonify({'message': 'Invalid image file type'}), 400

    if not name or not price:
        return jsonify({'message': 'Missing name or price'}), 400

    conn = get_db_connection()
    if not conn: return jsonify({'message': 'Database connection failed'}), 500
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO menu_items (name, description, price, image_path) VALUES (%s, %s, %s, %s)",
            (name, description, price, image_path)
        )
        conn.commit()
        item_id = cursor.lastrowid
        return jsonify({'message': 'Menu item added', 'item_id': item_id, 'image_path': image_path}), 201
    except Error as e:
        conn.rollback()
        print(f"Error adding menu item: {e}")
        return jsonify({'message': 'Failed to add menu item'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/menu/<int:item_id>', methods=['PUT'])
def update_menu_item(item_id):
    # TODO: Add authentication check - only canteen users
    data = request.form
    name = data.get('name')
    description = data.get('description')
    price = data.get('price')
    is_available_str = data.get('is_available') # Comes as string
    is_available = None
    if is_available_str:
        is_available = is_available_str.lower() in ['true', '1', 't', 'yes']

    image_path_update = None # Will store the new filename if uploaded

    # Check for image update
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
             filename = secure_filename(f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
             filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
             try:
                 # TODO: Optionally delete the old image file if it exists
                 file.save(filepath)
                 image_path_update = filename # Prepare to update DB path
             except Exception as e:
                  print(f"Error saving updated file: {e}")
                  return jsonify({'message': 'Failed to save updated image'}), 500
        elif file.filename != '':
             return jsonify({'message': 'Invalid image file type for update'}), 400

    conn = get_db_connection()
    if not conn: return jsonify({'message': 'Database connection failed'}), 500
    cursor = conn.cursor()

    update_fields = []
    params = []
    if name:
        update_fields.append("name = %s")
        params.append(name)
    if description is not None: # Allow empty description
        update_fields.append("description = %s")
        params.append(description)
    if price:
        update_fields.append("price = %s")
        params.append(price)
    if image_path_update:
        update_fields.append("image_path = %s")
        params.append(image_path_update)
    if is_available is not None:
        update_fields.append("is_available = %s")
        params.append(is_available)

    if not update_fields:
        return jsonify({'message': 'No fields provided for update'}), 400

    sql = f"UPDATE menu_items SET {', '.join(update_fields)} WHERE id = %s"
    params.append(item_id)

    try:
        cursor.execute(sql, tuple(params))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'message': 'Menu item not found or no changes made'}), 404
        return jsonify({'message': 'Menu item updated successfully'}), 200
    except Error as e:
        conn.rollback()
        print(f"Error updating menu item {item_id}: {e}")
        return jsonify({'message': 'Failed to update menu item'}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/api/menu/<int:item_id>', methods=['DELETE'])
def delete_menu_item(item_id):
     # TODO: Add authentication check - only canteen users
     conn = get_db_connection()
     if not conn: return jsonify({'message': 'Database connection failed'}), 500
     cursor = conn.cursor(dictionary=True)
     try:
         # Optional: Get image path to delete the file later
         cursor.execute("SELECT image_path FROM menu_items WHERE id = %s", (item_id,))
         item = cursor.fetchone()
         image_to_delete = item['image_path'] if item else None

         cursor.execute("DELETE FROM menu_items WHERE id = %s", (item_id,))
         conn.commit()

         if cursor.rowcount == 0:
             return jsonify({'message': 'Menu item not found'}), 404

         # Optional: Delete the associated image file
         if image_to_delete:
             try:
                 os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image_to_delete))
             except OSError as e:
                 print(f"Error deleting image file {image_to_delete}: {e}") # Log error but proceed

         return jsonify({'message': 'Menu item deleted successfully'}), 200
     except Error as e:
         conn.rollback()
         print(f"Error deleting menu item {item_id}: {e}")
         # Handle potential foreign key constraint errors if item is in an order
         if "foreign key constraint fails" in str(e).lower():
              return jsonify({'message': 'Cannot delete item, it is part of existing orders. Consider marking as unavailable instead.'}), 409
         return jsonify({'message': 'Failed to delete menu item'}), 500
     finally:
         cursor.close()
         conn.close()


# Serve Menu Item Images
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Security: Ensure filename is safe and doesn't allow directory traversal
    safe_path = os.path.abspath(app.config['UPLOAD_FOLDER'])
    requested_path = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    if not requested_path.startswith(safe_path):
        return "Forbidden", 403
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
         return "File not found", 404


# Menu Viewing (Student/Public)
@app.route('/api/menu', methods=['GET'])
def get_menu():
    conn = get_db_connection()
    if not conn: return jsonify({'message': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True) # Get results as dicts
    try:
        # Fetch only available items for students
        # Add "WHERE is_available = TRUE" for student view if needed
        cursor.execute("SELECT id, name, description, price, image_path, is_available FROM menu_items ORDER BY name")
        menu = cursor.fetchall()
        # Construct full image URLs
        base_url = request.host_url.rstrip('/') # Gets http://127.0.0.1:5000 or similar
        for item in menu:
            if item['image_path']:
                item['image_url'] = f"{base_url}/uploads/{item['image_path']}"
            else:
                item['image_url'] = None # Or a placeholder image URL
        return jsonify(menu), 200
    except Error as e:
        print(f"Error fetching menu: {e}")
        return jsonify({'message': 'Failed to fetch menu'}), 500
    finally:
        cursor.close()
        conn.close()

# Ordering (Student)
@app.route('/api/orders', methods=['POST'])
def place_order():
    # TODO: Add authentication check - only student users
    data = request.get_json()
    student_id = data.get('student_id')
    items = data.get('items') # List of {'menu_item_id': id, 'quantity': qty}
    coupon_code = data.get('coupon_code') # Optional

    if not student_id or not items:
        return jsonify({'message': 'Missing student ID or items'}), 400

    conn = get_db_connection()
    if not conn: return jsonify({'message': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)

    try:
        total_amount = 0
        final_amount = 0
        discount_amount = 0
        order_items_data = [] # To store data for inserting into order_items table

        # 1. Validate items and calculate total amount
        item_ids = [item['menu_item_id'] for item in items]
        if not item_ids: return jsonify({'message': 'No items in order'}), 400

        # Fetch prices in one go
        sql_placeholders = ','.join(['%s'] * len(item_ids))
        cursor.execute(f"SELECT id, price, name, is_available FROM menu_items WHERE id IN ({sql_placeholders})", tuple(item_ids))
        menu_items_db = {item['id']: item for item in cursor.fetchall()}

        for item in items:
            menu_item_id = item['menu_item_id']
            quantity = item['quantity']
            db_item = menu_items_db.get(menu_item_id)

            if not db_item:
                conn.rollback()
                return jsonify({'message': f'Menu item with ID {menu_item_id} not found'}), 404
            if not db_item['is_available']:
                 conn.rollback()
                 return jsonify({'message': f'Item "{db_item["name"]}" is currently unavailable'}), 400
            if quantity <= 0:
                conn.rollback()
                return jsonify({'message': f'Invalid quantity for item ID {menu_item_id}'}), 400

            price_at_order = db_item['price']
            item_total = price_at_order * quantity
            total_amount += item_total
            order_items_data.append({
                'menu_item_id': menu_item_id,
                'quantity': quantity,
                'price_at_order': price_at_order
            })

        # 2. Apply Coupon (if any)
        if coupon_code:
             # Fetch coupon details (implement /api/coupons/validate endpoint or logic here)
             # For simplicity, assume validation happens here. In reality, call a validation function/endpoint.
             cursor.execute(
                 """SELECT id, code, discount_percentage, discount_fixed, valid_until, uses_count, max_uses, is_active
                    FROM coupons
                    WHERE code = %s AND is_active = TRUE""", (coupon_code,)
             )
             coupon = cursor.fetchone()

             now = datetime.datetime.now()
             valid = False
             if coupon:
                 if coupon['valid_until'] is None or coupon['valid_until'] > now:
                     if coupon['max_uses'] is None or coupon['uses_count'] < coupon['max_uses']:
                         valid = True

             if valid:
                 if coupon['discount_percentage']:
                     discount_amount = total_amount * (coupon['discount_percentage'] / 100)
                 elif coupon['discount_fixed']:
                     discount_amount = min(total_amount, coupon['discount_fixed']) # Cannot discount more than total

                 # Optionally, increment coupon uses_count here or after successful order insertion
             else:
                 # Coupon invalid or expired, ignore it or return an error
                 coupon_code = None # Clear the code if invalid
                 discount_amount = 0
                 # Optionally: return jsonify({'message': 'Invalid or expired coupon code'}), 400

        final_amount = total_amount - discount_amount

        # 3. Insert Order
        cursor.execute(
            """INSERT INTO orders (student_id, total_amount, coupon_code, discount_amount, final_amount, status)
               VALUES (%s, %s, %s, %s, %s, 'Pending')""",
            (student_id, total_amount, coupon_code, discount_amount, final_amount)
        )
        order_id = cursor.lastrowid

        # 4. Insert Order Items
        order_items_sql = """INSERT INTO order_items (order_id, menu_item_id, quantity, price_at_order)
                            VALUES (%s, %s, %s, %s)"""
        order_items_values = [
            (order_id, item['menu_item_id'], item['quantity'], item['price_at_order'])
            for item in order_items_data
        ]
        cursor.executemany(order_items_sql, order_items_values)

        # 5. Optionally: Increment coupon usage count if one was successfully applied
        if coupon_code and valid and coupon: # Check 'valid' flag again
            cursor.execute("UPDATE coupons SET uses_count = uses_count + 1 WHERE id = %s", (coupon['id'],))

        conn.commit()
        return jsonify({'message': 'Order placed successfully', 'order_id': order_id}), 201

    except Error as e:
        conn.rollback()
        print(f"Error placing order: {e}")
        return jsonify({'message': 'Failed to place order'}), 500
    except Exception as e: # Catch other potential errors (like division by zero if quantity is bad)
         conn.rollback()
         print(f"Unexpected error placing order: {e}")
         return jsonify({'message': 'An unexpected error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

# Order Tracking / Viewing
@app.route('/api/orders', methods=['GET'])
def get_orders():
    # This endpoint could be used by both students (filtered) and canteens (all)
    # We'll need to know the user's role and ID from the request (e.g., via headers/tokens in a real app)
    # For simplicity, let's add query parameters for filtering
    student_id = request.args.get('student_id')
    # role = request.args.get('role') # Get role from authenticated user in real app

    conn = get_db_connection()
    if not conn: return jsonify({'message': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        base_sql = """
            SELECT o.id, o.student_id, u.username as student_username, o.order_date,
                   o.total_amount, o.status, o.coupon_code, o.discount_amount, o.final_amount
            FROM orders o
            JOIN users u ON o.student_id = u.id
        """
        params = []
        if student_id:
             # If a student ID is provided, filter by it (student view)
             base_sql += " WHERE o.student_id = %s"
             params.append(student_id)
        # Add more filtering based on role if needed (e.g., canteen sees all)

        base_sql += " ORDER BY o.order_date DESC"

        cursor.execute(base_sql, tuple(params))
        orders = cursor.fetchall()

        # Optionally, fetch order items for each order (can be slow for many orders - N+1 problem)
        # Consider a separate endpoint like /api/orders/<order_id>/items
        for order in orders:
            order['order_date'] = order['order_date'].isoformat() # Make datetime JSON serializable
            # Fetch items for this specific order
            cursor.execute("""
                SELECT oi.quantity, oi.price_at_order, mi.name as item_name
                FROM order_items oi
                JOIN menu_items mi ON oi.menu_item_id = mi.id
                WHERE oi.order_id = %s
            """, (order['id'],))
            order['items'] = cursor.fetchall()


        return jsonify(orders), 200
    except Error as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'message': 'Failed to fetch orders'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    # TODO: Add authentication check - only canteen users
    data = request.get_json()
    new_status = data.get('status')
    valid_statuses = ['Pending', 'Preparing', 'Ready for Pickup', 'Completed', 'Cancelled']

    if not new_status or new_status not in valid_statuses:
        return jsonify({'message': 'Invalid or missing status'}), 400

    conn = get_db_connection()
    if not conn: return jsonify({'message': 'Database connection failed'}), 500
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, order_id))
        conn.commit()
        if cursor.rowcount == 0:
             return jsonify({'message': 'Order not found'}), 404
        return jsonify({'message': f'Order {order_id} status updated to {new_status}'}), 200
    except Error as e:
        conn.rollback()
        print(f"Error updating order status for {order_id}: {e}")
        return jsonify({'message': 'Failed to update order status'}), 500
    finally:
        cursor.close()
        conn.close()

# Coupon Management (Canteen) - Basic examples
@app.route('/api/coupons', methods=['POST'])
def add_coupon():
     # TODO: Auth check - canteen only
     data = request.get_json()
     # Basic validation - add more as needed
     if not data.get('code'): return jsonify({'message': 'Coupon code required'}), 400
     # Ensure either percentage or fixed amount, not both?

     conn = get_db_connection()
     if not conn: return jsonify({'message': 'DB connection error'}), 500
     cursor = conn.cursor()
     try:
          cursor.execute("""
             INSERT INTO coupons (code, discount_percentage, discount_fixed, valid_from, valid_until, max_uses, is_active)
             VALUES (%s, %s, %s, %s, %s, %s, %s)
          """, (
              data.get('code'), data.get('discount_percentage'), data.get('discount_fixed'),
              data.get('valid_from'), data.get('valid_until'), data.get('max_uses'),
              data.get('is_active', True)
          ))
          conn.commit()
          return jsonify({'message': 'Coupon added', 'id': cursor.lastrowid}), 201
     except Error as e:
          conn.rollback()
          if "Duplicate entry" in str(e):
                return jsonify({'message': 'Coupon code already exists'}), 409
          print(f"Error adding coupon: {e}")
          return jsonify({'message': 'Failed to add coupon'}), 500
     finally:
          cursor.close()
          conn.close()

@app.route('/api/coupons', methods=['GET'])
def get_coupons():
    # TODO: Auth check - canteen only
    conn = get_db_connection()
    if not conn: return jsonify({'message': 'DB connection error'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM coupons ORDER BY created_at DESC")
        coupons = cursor.fetchall()
        # Convert datetime objects for JSON
        for coupon in coupons:
            for key in ['valid_from', 'valid_until', 'created_at']:
                if coupon[key] and isinstance(coupon[key], datetime.datetime):
                    coupon[key] = coupon[key].isoformat()
        return jsonify(coupons), 200
    except Error as e:
         print(f"Error getting coupons: {e}")
         return jsonify({'message': 'Failed to get coupons'}), 500
    finally:
         cursor.close()
         conn.close()

@app.route('/api/coupons/<int:coupon_id>', methods=['DELETE'])
def delete_coupon(coupon_id):
     # TODO: Auth check - canteen only
     conn = get_db_connection()
     if not conn: return jsonify({'message': 'DB connection error'}), 500
     cursor = conn.cursor()
     try:
         cursor.execute("DELETE FROM coupons WHERE id = %s", (coupon_id,))
         conn.commit()
         if cursor.rowcount == 0: return jsonify({'message': 'Coupon not found'}), 404
         return jsonify({'message': 'Coupon deleted'}), 200
     except Error as e:
          conn.rollback()
          print(f"Error deleting coupon: {e}")
          return jsonify({'message': 'Failed to delete coupon'}), 500
     finally:
          cursor.close()
          conn.close()


# --- Run the App ---
if __name__ == '__main__':
    # Note: Use a proper WSGI server like Gunicorn or Waitress for production
    app.run(debug=True, port=5000) # Run on port 5000