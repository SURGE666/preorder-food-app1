import streamlit as st
import requests
from dotenv import load_dotenv
import os
from PIL import Image
import io

load_dotenv()

# Load backend URL from .env file or default
API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:5000/api")
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "http://127.0.0.1:5000/uploads")

# --- Helper Functions to call Backend API ---

def api_request(method, endpoint, data=None, json=None, files=None, params=None):
    """General function to make API requests."""
    url = f"{API_URL}/{endpoint}"
    try:
        response = requests.request(method, url, data=data, json=json, files=files, params=params, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        # Handle cases where response might be empty but successful (e.g., 204 No Content)
        if response.status_code == 204:
             return None
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error(f"Connection Error: Could not connect to the backend at {url}. Is the Flask server running?")
        return None
    except requests.exceptions.Timeout:
        st.error("Request timed out. The backend might be busy or unresponsive.")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"HTTP Error: {e.response.status_code} {e.response.reason}")
        try:
             # Try to get error message from backend response
             error_data = e.response.json()
             st.error(f"Backend message: {error_data.get('message', 'No specific message.')}")
        except ValueError: # If response is not JSON
             st.error(f"Backend response: {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"An unexpected error occurred: {e}")
        return None
    except ValueError: # JSONDecodeError if response isn't valid JSON
        st.error("Received non-JSON response from the backend.")
        return None


# --- Authentication ---
def login(username, password):
    return api_request('post', 'login', json={'username': username, 'password': password})

def register(username, password, role):
    return api_request('post', 'register', json={'username': username, 'password': password, 'role': role})

# --- Menu ---
def get_menu():
    return api_request('get', 'menu')

def add_menu_item_api(name, description, price, image_file):
    files = {'image': (image_file.name, image_file, image_file.type)} if image_file else None
    data = {'name': name, 'description': description, 'price': price}
    # Use data=data for form fields, files=files for the image
    return api_request('post', 'menu', data=data, files=files)

def update_menu_item_api(item_id, name, description, price, is_available, image_file):
    files = {'image': (image_file.name, image_file, image_file.type)} if image_file else None
    data = {}
    if name: data['name'] = name
    if description is not None: data['description'] = description # Allow empty string
    if price: data['price'] = price
    if is_available is not None: data['is_available'] = str(is_available) # Send as string

    # Only include fields that have values
    if not data and not files:
        st.warning("No changes detected.")
        return None # Or return a specific value indicating no update needed

    return api_request('put', f'menu/{item_id}', data=data, files=files)


def delete_menu_item_api(item_id):
     return api_request('delete', f'menu/{item_id}')


# --- Orders ---
def place_order_api(student_id, items, coupon_code=None):
    payload = {'student_id': student_id, 'items': items}
    if coupon_code:
        payload['coupon_code'] = coupon_code
    return api_request('post', 'orders', json=payload)

def get_orders_api(student_id=None):
    params = {}
    if student_id:
        params['student_id'] = student_id
    # In a real app, you'd pass the user's role implicitly via auth token
    return api_request('get', 'orders', params=params)

def update_order_status_api(order_id, status):
     return api_request('put', f'orders/{order_id}/status', json={'status': status})

# --- Coupons ---
def add_coupon_api(code, discount_percentage, discount_fixed, valid_until, max_uses):
     payload = {'code': code, 'discount_percentage': discount_percentage, 'discount_fixed': discount_fixed, 'valid_until': valid_until, 'max_uses': max_uses}
     # Remove None values before sending
     payload = {k: v for k, v in payload.items() if v is not None}
     return api_request('post', 'coupons', json=payload)

def get_coupons_api():
     return api_request('get', 'coupons')

def delete_coupon_api(coupon_id):
     return api_request('delete', f'coupons/{coupon_id}')


# --- Streamlit UI Components ---

def login_page():
    st.header("Login / Register")
    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                if not username or not password:
                    st.warning("Please enter username and password.")
                else:
                    response = login(username, password)
                    if response and 'user' in response:
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = response['user']
                        st.session_state['cart'] = {} # Initialize cart on login
                        st.success("Login Successful!")
                        st.rerun() # Rerun to update the page view
                    elif response: # Error message from backend handled by api_request
                        pass # Error already shown
                    # else: connection error handled by api_request

    with register_tab:
        with st.form("register_form"):
            reg_username = st.text_input("Choose Username", key="reg_user")
            reg_password = st.text_input("Choose Password", type="password", key="reg_pass")
            reg_role = st.selectbox("Register as:", ["student", "canteen"], key="reg_role")
            reg_submitted = st.form_submit_button("Register")
            if reg_submitted:
                if not reg_username or not reg_password:
                    st.warning("Please fill in all fields.")
                else:
                    response = register(reg_username, reg_password, reg_role)
                    if response and response.get('user_id'):
                        st.success(f"Registration successful for {reg_username}! Please login.")
                    elif response:
                        pass # Error handled by api_request
                    # else: connection error handled

def student_dashboard():
    st.title(f"Welcome, {st.session_state['user']['username']} (Student)")
    st.sidebar.button("Logout", on_click=logout)

    menu_tab, cart_tab, orders_tab = st.tabs(["Browse Menu", "My Cart", "My Orders"])

    with menu_tab:
        st.subheader("Today's Menu")
        menu_items = get_menu()
        if menu_items:
            cols = st.columns(3) # Adjust number of columns as needed
            col_idx = 0
            for item in menu_items:
                 if item.get('is_available', True): # Only show available items
                    with cols[col_idx % len(cols)]:
                        st.markdown(f"**{item['name']}**")
                        if item.get('image_url'):
                            st.image(item['image_url'], width=150) # Use URL from backend
                        else:
                            st.caption("No Image") # Placeholder
                        st.markdown(f"_{item.get('description', '')}_")
                        st.markdown(f"**Price:** ₹{float(item['price']):.2f}")
                        # Add to cart button
                        if st.button(f"Add to Cart", key=f"add_{item['id']}"):
                            add_to_cart(item['id'], item)
                            st.success(f"{item['name']} added to cart!")
                            st.rerun() # Optional: Rerun to potentially update cart count display elsewhere
                    col_idx += 1
        else:
            st.info("Menu is currently empty or could not be loaded.")


    with cart_tab:
        st.subheader("Your Cart")
        cart = st.session_state.get('cart', {})
        if not cart:
            st.info("Your cart is empty. Add items from the Menu tab!")
        else:
            total = 0
            items_payload = [] # For placing order API
            for item_id, details in cart.items():
                item_total = details['price'] * details['quantity']
                st.write(f"{details['name']} (x{details['quantity']}) - ₹{item_total:.2f}")
                total += item_total
                items_payload.append({'menu_item_id': item_id, 'quantity': details['quantity']})

            st.write("---")
            st.subheader(f"Total: ₹{total:.2f}")

            # Coupon Code Input (optional)
            coupon_code = st.text_input("Enter Coupon Code (optional)")

            if st.button("Place Order"):
                 if not items_payload:
                      st.warning("Cannot place an empty order.")
                 else:
                    student_id = st.session_state['user']['id']
                    response = place_order_api(student_id, items_payload, coupon_code if coupon_code else None)
                    if response and response.get('order_id'):
                        st.success(f"Order placed successfully! Order ID: {response['order_id']}")
                        st.session_state['cart'] = {} # Clear cart
                        st.rerun()
                    else:
                        st.error("Failed to place order.") # More specific error shown by api_request


    with orders_tab:
        st.subheader("Your Order History")
        student_id = st.session_state['user']['id']
        orders = get_orders_api(student_id=student_id)
        if orders:
            for order in orders:
                with st.expander(f"Order #{order['id']} - Status: {order['status']} ({order['order_date']})"):
                    st.write(f"**Total Amount:** ₹{float(order['total_amount']):.2f}")
                    if order['coupon_code']:
                         st.write(f"**Coupon:** {order['coupon_code']} (-₹{float(order['discount_amount']):.2f})")
                    st.write(f"**Final Amount:** ₹{float(order['final_amount']):.2f}")
                    st.write("**Items:**")
                    if order.get('items'):
                         for item in order['items']:
                             st.write(f"- {item['item_name']} (x{item['quantity']}) @ ₹{float(item['price_at_order']):.2f} each")
                    else:
                         st.write("Item details not loaded.")

        elif orders == []: # Explicitly check for empty list vs None (error)
            st.info("You haven't placed any orders yet.")
        # else: Error message handled by get_orders_api

def canteen_dashboard():
    st.title(f"Welcome, {st.session_state['user']['username']} (Canteen Admin)")
    st.sidebar.button("Logout", on_click=logout)

    menu_tab, orders_tab, coupons_tab = st.tabs(["Manage Menu", "Manage Orders", "Manage Coupons"])

    with menu_tab:
        st.subheader("Edit Menu Items")

        # Display existing items with edit/delete options
        menu_items = get_menu() # Get all items for canteen view
        if menu_items:
             for item in menu_items:
                 cols = st.columns([3, 1, 1, 1, 1]) # Adjust layout
                 with cols[0]:
                      st.write(f"**{item['name']}** (₹{float(item['price']):.2f}) - Available: {'Yes' if item.get('is_available', True) else 'No'}")
                      if item.get('image_url'):
                          st.image(item['image_url'], width=100)
                 with cols[1]:
                      # Edit Button (opens a modal or expands a form)
                      if st.button("Edit", key=f"edit_{item['id']}"):
                          st.session_state['editing_item_id'] = item['id'] # Store which item to edit
                          st.rerun() # Rerun to show the edit form
                 with cols[2]:
                      # Delete Button
                      if st.button("Delete", key=f"del_{item['id']}"):
                          if st.confirm(f"Are you sure you want to delete {item['name']}?", key=f"confirm_del_{item['id']}"):
                               response = delete_menu_item_api(item['id'])
                               if response:
                                   st.success(f"{item['name']} deleted.")
                                   st.rerun()
                               # else: Error handled by api_request

             st.write("---")

             # Edit Form (shown if 'editing_item_id' is in session state)
             if 'editing_item_id' in st.session_state and st.session_state['editing_item_id']:
                 item_id_to_edit = st.session_state['editing_item_id']
                 # Find the item details to pre-fill the form
                 item_to_edit = next((item for item in menu_items if item['id'] == item_id_to_edit), None)
                 if item_to_edit:
                      st.subheader(f"Editing: {item_to_edit['name']}")
                      with st.form(key=f"edit_form_{item_id_to_edit}"):
                           edit_name = st.text_input("Name", value=item_to_edit['name'])
                           edit_desc = st.text_area("Description", value=item_to_edit.get('description', ''))
                           edit_price = st.number_input("Price (₹)", min_value=0.0, value=float(item_to_edit['price']), format="%.2f")
                           edit_available = st.checkbox("Is Available?", value=item_to_edit.get('is_available', True))
                           edit_image = st.file_uploader("Update Image (Optional)", type=['png', 'jpg', 'jpeg', 'gif'], key=f"edit_img_{item_id_to_edit}")

                           edit_submitted = st.form_submit_button("Save Changes")
                           cancel_edit = st.form_submit_button("Cancel Edit")

                           if edit_submitted:
                               response = update_menu_item_api(item_id_to_edit, edit_name, edit_desc, edit_price, edit_available, edit_image)
                               if response:
                                    st.success("Item updated successfully!")
                                    st.session_state['editing_item_id'] = None # Clear editing state
                                    st.rerun()
                               # else: Error handled by api_request
                           if cancel_edit:
                                st.session_state['editing_item_id'] = None
                                st.rerun()
                 else:
                      st.error("Could not find item to edit.")
                      st.session_state['editing_item_id'] = None # Clear state


        # Add New Item Form
        st.subheader("Add New Menu Item")
        with st.form("add_item_form", clear_on_submit=True):
            item_name = st.text_input("Item Name")
            item_desc = st.text_area("Description")
            item_price = st.number_input("Price (₹)", min_value=0.0, format="%.2f")
            item_image = st.file_uploader("Upload Image", type=['png', 'jpg', 'jpeg', 'gif'])
            add_submitted = st.form_submit_button("Add Item")
            if add_submitted:
                if not item_name or item_price <= 0:
                    st.warning("Please provide item name and a valid price.")
                else:
                    response = add_menu_item_api(item_name, item_desc, item_price, item_image)
                    if response and response.get('item_id'):
                        st.success(f"Item '{item_name}' added successfully!")
                        st.rerun()
                    # else: Error handled by api_request

    with orders_tab:
        st.subheader("Incoming Orders")
        orders = get_orders_api() # Get all orders for canteen
        if orders:
            valid_statuses = ['Pending', 'Preparing', 'Ready for Pickup', 'Completed', 'Cancelled']
            for order in orders:
                 st.write(f"---")
                 st.write(f"**Order #{order['id']}** - Student: {order['student_username']} ({order['order_date']})")
                 st.write(f"**Total:** ₹{float(order['final_amount']):.2f} ({len(order.get('items', []))} items)")
                 # Display items
                 if order.get('items'):
                     with st.expander("View Items"):
                         for item in order['items']:
                             st.write(f"- {item['item_name']} (x{item['quantity']})")

                 # Status Update Dropdown
                 current_status_index = valid_statuses.index(order['status']) if order['status'] in valid_statuses else 0
                 new_status = st.selectbox(
                     "Update Status:",
                     valid_statuses,
                     index=current_status_index,
                     key=f"status_{order['id']}"
                 )
                 if st.button("Update", key=f"update_{order['id']}"):
                     if new_status != order['status']:
                         response = update_order_status_api(order['id'], new_status)
                         if response:
                             st.success(f"Order #{order['id']} status updated to {new_status}")
                             st.rerun()
                         # else: Error handled by api_request
                     else:
                         st.info("Status is already set to this value.")

        elif orders == []:
             st.info("No orders received yet.")
        # else: Error handled by api_request

    with coupons_tab:
         st.subheader("Manage Discount Coupons")

         # Display existing coupons
         coupons = get_coupons_api()
         if coupons:
              for coupon in coupons:
                   discount_str = ""
                   if coupon.get('discount_percentage'):
                       discount_str = f"{coupon['discount_percentage']}%"
                   elif coupon.get('discount_fixed'):
                       discount_str = f"₹{float(coupon['discount_fixed']):.2f}"

                   valid_until_str = f"until {coupon['valid_until']}" if coupon['valid_until'] else "no expiry"
                   uses_str = f"{coupon['uses_count']}/{coupon['max_uses']}" if coupon['max_uses'] else f"{coupon['uses_count']}"
                   active_str = "Active" if coupon.get('is_active', True) else "Inactive"

                   st.write(f"**{coupon['code']}**: {discount_str} off | Uses: {uses_str} | {valid_until_str} | Status: {active_str}")
                   if st.button("Delete Coupon", key=f"del_coupon_{coupon['id']}"):
                        if st.confirm(f"Delete coupon {coupon['code']}?", key=f"conf_del_coup_{coupon['id']}"):
                            response = delete_coupon_api(coupon['id'])
                            if response:
                                st.success(f"Coupon {coupon['code']} deleted.")
                                st.rerun()
                            # else: Error handled

         # Add New Coupon Form
         st.subheader("Add New Coupon")
         with st.form("add_coupon_form", clear_on_submit=True):
              coupon_code = st.text_input("Coupon Code (e.g., SUMMER10)")
              discount_type = st.radio("Discount Type", ["Percentage (%)", "Fixed Amount (₹)"])
              disc_perc = None
              disc_fixed = None
              if discount_type == "Percentage (%)":
                   disc_perc = st.number_input("Discount Percentage", min_value=0.0, max_value=100.0, format="%.2f")
              else:
                   disc_fixed = st.number_input("Fixed Discount Amount (₹)", min_value=0.0, format="%.2f")

              valid_until_date = st.date_input("Valid Until (Optional)", value=None)
              # Convert date to string or None
              valid_until_str = valid_until_date.isoformat() if valid_until_date else None

              max_uses = st.number_input("Max Uses (Optional, 0 or leave blank for unlimited)", min_value=0, value=0, step=1)
              max_uses_val = max_uses if max_uses > 0 else None # Store None if unlimited

              add_coupon_submitted = st.form_submit_button("Add Coupon")

              if add_coupon_submitted:
                   if not coupon_code:
                        st.warning("Coupon code is required.")
                   elif disc_perc is None and disc_fixed is None:
                        st.warning("Please specify a discount percentage or fixed amount.")
                   elif disc_perc is not None and disc_fixed is not None:
                        st.warning("Please specify only ONE discount type (percentage OR fixed amount).") # Or handle this logic if needed
                   else:
                        response = add_coupon_api(coupon_code, disc_perc, disc_fixed, valid_until_str, max_uses_val)
                        if response and response.get('id'):
                             st.success(f"Coupon '{coupon_code}' added!")
                             st.rerun()
                        # else: Error handled


# --- Cart Management ---
def add_to_cart(item_id, item_details):
    if 'cart' not in st.session_state:
        st.session_state['cart'] = {}

    if item_id in st.session_state['cart']:
        st.session_state['cart'][item_id]['quantity'] += 1
    else:
        st.session_state['cart'][item_id] = {
            'name': item_details['name'],
            'price': float(item_details['price']), # Ensure price is float
            'quantity': 1
        }

# --- Logout ---
def logout():
    st.session_state['logged_in'] = False
    st.session_state.pop('user', None) # Remove user info
    st.session_state.pop('cart', None) # Clear cart on logout
    st.session_state.pop('editing_item_id', None) # Clear any editing state
    st.success("You have been logged out.")
    st.rerun()

# --- Main App Logic ---
def main():
    st.set_page_config(page_title="Food Preorder App", layout="wide")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if st.session_state['logged_in']:
        user_role = st.session_state['user']['role']
        if user_role == 'student':
            student_dashboard()
        elif user_role == 'canteen':
            canteen_dashboard()
        else:
            st.error("Invalid user role detected.")
            logout()
    else:
        login_page()

if __name__ == "__main__":
    main()