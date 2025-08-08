from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Supplier, Medicine, Batch, Order, OrderItem, StockTransaction
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from sqlalchemy import func
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Ensure all required packages are installed:
# pip install flask flask-login sqlalchemy apscheduler reportlab

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_change_in_production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rhu_inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def check_expiring_medicines():
    """Check for medicines expiring in the next 30 days"""
    with app.app_context():
        thirty_days_from_now = datetime.now().date() + timedelta(days=30)
        expiring_batches = Batch.query.filter(
            Batch.expiration_date <= thirty_days_from_now,
            Batch.expiration_date > datetime.now().date()
        ).all()

        if expiring_batches:
            # Send email to managers
            managers = User.query.filter_by(role='manager').all()
            for manager in managers:
                send_expiration_alert(manager.email, expiring_batches)

def send_expiration_alert(email, batches):
    """Send email alert for expiring medicines"""
    # Configure your email settings
    sender_email = "your-email@example.com"
    sender_password = "your-password"

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = email
    msg['Subject'] = "Medicine Expiration Alert"

    body = "The following medicines are expiring soon:\n\n"
    for batch in batches:
        body += f"Medicine: {batch.medicine.name}\n"
        body += f"Batch Number: {batch.batch_number}\n"
        body += f"Expiration Date: {batch.expiration_date}\n"
        body += f"Quantity Remaining: {batch.quantity}\n\n"

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

# Set up the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    check_expiring_medicines,
    trigger=CronTrigger(hour=9),  # Run daily at 9 AM
    id='check_expiring_medicines',
    name='Check for expiring medicines'
)

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get low stock items (quantity <= 10)
    low_stock = Batch.query.filter(Batch.quantity <= 10).all()
    # Get items expiring in the next 30 days
    thirty_days_from_now = datetime.now().date() + timedelta(days=30)
    expiring_soon = Batch.query.filter(
        Batch.expiration_date <= thirty_days_from_now,
        Batch.expiration_date > datetime.now().date()
    ).all()
    # Get recent transactions
    recent_transactions = StockTransaction.query.order_by(
        StockTransaction.transaction_date.desc()
    ).limit(10).all()
    # Get total counts
    total_medicines = Medicine.query.count()
    total_suppliers = Supplier.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    return render_template('dashboard.html',
                         low_stock=low_stock,
                         expiring_soon=expiring_soon,
                         recent_transactions=recent_transactions,
                         total_medicines=total_medicines,
                         total_suppliers=total_suppliers,
                         pending_orders=pending_orders)

@app.route('/orders')
@login_required
def orders():
    orders = Order.query.order_by(Order.order_date.desc()).all()

    # Correctly filter medicines that have a total quantity greater than 0
    medicines = db.session.query(Medicine).join(Batch).group_by(Medicine.id).having(func.sum(Batch.quantity) > 0).all()

    return render_template('orders.html', orders=orders, medicines=medicines)

@app.route('/suppliers')
@login_required
def suppliers():
    suppliers = Supplier.query.all()
    return render_template('suppliers.html', suppliers=suppliers)

@app.route('/inventory')
@login_required
def inventory():
    medicines = Medicine.query.all()
    return render_template('inventory.html', medicines=medicines)

@app.route('/batches')
@login_required
def batches():
    batches = Batch.query.all()
    return render_template('batches.html', batches=batches)

@app.route('/reports')
@login_required
def reports():
    # Allow admin, sub-admin, and employee to access reports
    if current_user.role not in ['admin', 'sub-admin', 'employee']:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))
    # Stock levels report
    stock_report = db.session.query(
        Medicine.name,
        func.sum(Batch.quantity).label('total_quantity')
    ).join(Batch).group_by(Medicine.name).all()
    # Expiring medicines report
    thirty_days_from_now = datetime.now().date() + timedelta(days=30)
    expiring_report = Batch.query.filter(
        Batch.expiration_date <= thirty_days_from_now
    ).all()
    return render_template('reports.html',
                         stock_report=stock_report,
                         expiring_report=expiring_report)

@app.route('/api/stock-levels')
@login_required
def api_stock_levels():
    """API endpoint for stock levels data"""
    stock_data = db.session.query(
        Medicine.name,
        func.sum(Batch.quantity).label('total_quantity')
    ).join(Batch).group_by(Medicine.name).all()
    return jsonify([{
        'medicine': item.name,
        'quantity': item.total_quantity
    } for item in stock_data])

@app.route('/order/<int:id>/deliver', methods=['POST'])
@login_required
def deliver_order(id):
    order = Order.query.get_or_404(id)
    order.status = 'delivered'
    db.session.commit()
    flash('Order marked as delivered', 'success')
    return redirect(url_for('orders'))

@app.route('/order/<int:id>/process', methods=['POST'])
@login_required
def process_order(id):
    # Only admin and sub-admin can process orders
    if current_user.role not in ['admin', 'sub-admin']:
        flash('You do not have permission to process orders.', 'danger')
        return redirect(url_for('orders'))
    order = Order.query.get_or_404(id)
    if order.status != 'pending':
        flash('Order is already processed.', 'warning')
        return redirect(url_for('orders'))
    # Mark order as delivered
    order.status = 'delivered'

    # Add to StockTransaction for each item in the order
    for item in order.items:
        # Find a batch for this medicine or create a new one (simple logic)
        batch = Batch.query.filter_by(medicine_id=item.medicine_id).order_by(Batch.expiration_date.desc()).first()
        if batch and not batch.is_expired:
            batch.quantity += item.quantity
        else:
            # If no batch exists or all are expired, create a new batch
            batch = Batch(
                batch_number=f"ORDER-{order.id}-{item.medicine_id}",
                medicine_id=item.medicine_id,
                quantity=item.quantity,
                expiration_date=datetime.now().date() + timedelta(days=365),
                manufacturing_date=datetime.now().date(),
                unit_price=item.unit_price
            )
            db.session.add(batch)

        # Record StockTransaction
        transaction = StockTransaction(
            batch_id=batch.id,
            transaction_type='in',
            quantity=item.quantity, # FIX: Changed from 'dispense_from_batch' to 'item.quantity'
            performed_by=current_user.id,
            notes=f"From Order #{order.id}"
        )
        db.session.add(transaction)

    db.session.commit()
    flash('Order processed and stock updated. Transactions recorded.', 'success')
    return redirect(url_for('orders'))

@app.route('/order/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_order(id):
    # Only admin can cancel orders
    if current_user.role != 'admin':
        flash('You do not have permission to cancel orders.', 'danger')
        return redirect(url_for('orders'))

    order = Order.query.get_or_404(id)
    if order.status == 'pending':
        order.status = 'cancelled'
        db.session.commit()
        flash('Order has been successfully cancelled.', 'success')
    else:
        flash('Only pending orders can be cancelled.', 'warning')

    return redirect(url_for('orders'))

@app.route('/dispense', methods=['POST'])
@login_required
def process_dispense():
    medicine_ids = request.form.getlist('medicine_id[]')
    quantities = request.form.getlist('quantity[]')

    for i in range(len(medicine_ids)):
        if not (medicine_ids[i] and quantities[i]):
            continue

        medicine_id = int(medicine_ids[i])
        quantity_to_dispense = int(quantities[i])

        medicine = Medicine.query.get_or_404(medicine_id)

        if medicine.total_quantity < quantity_to_dispense:
            flash(f'Not enough stock for {medicine.name}. Available: {medicine.total_quantity}, Requested: {quantity_to_dispense}', 'danger')
            return redirect(url_for('orders'))

        # Dispense from batches, oldest first
        batches = sorted(medicine.available_batches, key=lambda b: b.expiration_date)

        temp_qty_to_dispense = quantity_to_dispense
        for batch in batches:
            if temp_qty_to_dispense == 0:
                break

            dispense_from_batch = min(temp_qty_to_dispense, batch.quantity)

            if dispense_from_batch > 0:
                batch.quantity -= dispense_from_batch
                temp_qty_to_dispense -= dispense_from_batch

                # Record transaction
                transaction = StockTransaction(
                    batch_id=batch.id,
                    transaction_type='out',
                    quantity=dispense_from_batch,
                    performed_by=current_user.id,
                    notes="Dispensed to patient"
                )
                db.session.add(transaction)

    db.session.commit()
    flash('Medicines dispensed successfully.', 'success')
    return redirect(url_for('orders'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        role = request.form['role']

        # Check if the username or email already exists
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing_user:
            flash('Username or email already exists', 'error')
            return redirect(url_for('register'))

        # Create a new user
        new_user = User(
            username=username,
            password=generate_password_hash(password),
            email=email,
            role=role
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful. You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            # In a real app, send a reset email here
            flash('If this email is registered, you will receive instructions to reset your password.', 'info')
        else:
            flash('If this email is registered, you will receive instructions to reset your password.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/medicine/add', methods=['GET', 'POST'])
@login_required
def add_medicine():
    if request.method == 'POST':
        medicine = Medicine(
            name=request.form['name'],
            generic_name=request.form['generic_name'],
            category=request.form['category'],
            unit=request.form['unit'],
            supplier_id=request.form['supplier_id']
        )
        db.session.add(medicine)
        db.session.commit()
        flash('Medicine added successfully', 'success')
        return redirect(url_for('inventory'))
    suppliers = Supplier.query.all()
    return render_template('add_medicine.html', suppliers=suppliers)

@app.route('/medicine/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_medicine(id):
    # Only admin and sub-admin can edit, employee cannot
    if current_user.role not in ['admin', 'sub-admin']:
        flash('You do not have permission to edit medicines.', 'danger')
        return redirect(url_for('inventory'))
    medicine = Medicine.query.get_or_404(id)
    if request.method == 'POST':
        medicine.name = request.form['name']
        medicine.generic_name = request.form['generic_name']
        medicine.category = request.form['category']
        medicine.unit = request.form['unit']
        medicine.supplier_id = request.form['supplier_id']
        db.session.commit()
        flash('Medicine updated successfully', 'success')
        return redirect(url_for('inventory'))
    suppliers = Supplier.query.all()
    return render_template('edit_medicine.html', medicine=medicine, suppliers=suppliers)

@app.route('/medicine/<int:id>/delete', methods=['POST'])
@login_required
def delete_medicine(id):
    # Only admin can delete, sub-admin cannot
    if current_user.role != 'admin':
        flash('You do not have permission to delete medicines.', 'danger')
        return redirect(url_for('inventory'))
    medicine = Medicine.query.get_or_404(id)
    # Delete all order items related to this medicine first to avoid integrity error
    OrderItem.query.filter_by(medicine_id=medicine.id).delete()
    # Delete all batches related to this medicine
    Batch.query.filter_by(medicine_id=medicine.id).delete()
    db.session.delete(medicine)
    db.session.commit()
    flash('Medicine and its related batches and order items deleted successfully', 'success')
    return redirect(url_for('inventory'))

@app.route('/batch/add', methods=['GET', 'POST'])
@login_required
def add_batch():
    if request.method == 'POST':
        batch = Batch(
            batch_number=request.form['batch_number'],
            medicine_id=request.form['medicine_id'],
            quantity=request.form['quantity'],
            expiration_date=datetime.strptime(request.form['expiration_date'], '%Y-%m-%d').date(),
            manufacturing_date=datetime.strptime(request.form['manufacturing_date'], '%Y-%m-%d').date(),
            unit_price=float(request.form['unit_price'])
        )
        db.session.add(batch)
        db.session.commit()
        flash('Batch added successfully', 'success')
        return redirect(url_for('batches'))
    medicines = Medicine.query.all()
    return render_template('add_batch.html', medicines=medicines)

@app.route('/batch/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_batch(id):
    batch = Batch.query.get_or_404(id)
    if request.method == 'POST':
        batch.batch_number = request.form['batch_number']
        batch.medicine_id = request.form['medicine_id']
        batch.quantity = request.form['quantity']
        batch.expiration_date = datetime.strptime(request.form['expiration_date'], '%Y-%m-%d').date()
        batch.manufacturing_date = datetime.strptime(request.form['manufacturing_date'], '%Y-%m-%d').date()
        batch.unit_price = float(request.form['unit_price'])
        db.session.commit()
        flash('Batch updated successfully', 'success')
        return redirect(url_for('batches'))
    medicines = Medicine.query.all()
    return render_template('edit_batch.html', batch=batch, medicines=medicines)

@app.route('/batch/<int:id>/delete', methods=['POST'])
@login_required
def delete_batch(id):
    batch = Batch.query.get_or_404(id)
    db.session.delete(batch)
    db.session.commit()
    flash('Batch deleted successfully', 'success')
    return redirect(url_for('batches'))

@app.route('/supplier/add', methods=['GET', 'POST'])
@login_required
def add_supplier():
    if request.method == 'POST':
        supplier = Supplier(
            name=request.form['name'],
            contact_person=request.form['contact_person'],
            phone=request.form['phone'],
            email=request.form['email'],
            address=request.form['address']
        )
        db.session.add(supplier)
        db.session.commit()
        flash('Supplier added successfully', 'success')
        return redirect(url_for('suppliers'))
    return render_template('add_supplier.html')

@app.route('/supplier/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_supplier(id):
    # Only admin and sub-admin can edit, employee cannot
    if current_user.role not in ['admin', 'sub-admin']:
        flash('You do not have permission to edit suppliers.', 'danger')
        return redirect(url_for('suppliers'))
    supplier = Supplier.query.get_or_404(id)
    if request.method == 'POST':
        supplier.name = request.form['name']
        supplier.contact_person = request.form['contact_person']
        supplier.phone = request.form['phone']
        supplier.email = request.form['email']
        supplier.address = request.form['address']
        db.session.commit()
        flash('Supplier updated successfully', 'success')
        return redirect(url_for('suppliers'))
    return render_template('edit_supplier.html', supplier=supplier)

@app.route('/supplier/<int:id>/delete', methods=['POST'])
@login_required
def delete_supplier(id):
    # Only admin can delete, sub-admin cannot
    if current_user.role != 'admin':
        flash('You do not have permission to delete suppliers.', 'danger')
        return redirect(url_for('suppliers'))
    supplier = Supplier.query.get_or_404(id)
    db.session.delete(supplier)
    db.session.commit()
    flash('Supplier deleted successfully', 'success')
    return redirect(url_for('suppliers'))

@app.route('/order/add', methods=['GET', 'POST'])
@login_required
def add_order():
    if request.method == 'POST':
        # Prevent double submission by checking for recent similar orders
        last_order = Order.query.filter_by(
            supplier_id=request.form['supplier_id'],
            created_by=current_user.id
        ).order_by(Order.order_date.desc()).first()

        if last_order and (datetime.now() - last_order.order_date).total_seconds() < 5:
            flash('This order might have been submitted already. Please check the orders list.', 'warning')
            return redirect(url_for('orders'))

        order = Order(
            supplier_id=request.form['supplier_id'],
            created_by=current_user.id,
            status='pending'  # New orders are pending by default
        )
        db.session.add(order)
        db.session.flush()  # Get the order ID

        medicine_ids = request.form.getlist('medicine_id[]')
        quantities = request.form.getlist('quantity[]')
        unit_prices = request.form.getlist('unit_price[]')

        for i in range(len(medicine_ids)):
            if medicine_ids[i] and quantities[i]:
                # Create OrderItem
                order_item = OrderItem(
                    order_id=order.id,
                    medicine_id=medicine_ids[i],
                    quantity=int(quantities[i]),
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0.0
                )
                db.session.add(order_item)

        db.session.commit()
        flash('Order created successfully.', 'success')
        return redirect(url_for('orders'))
    suppliers = Supplier.query.all()
    medicines = Medicine.query.all()
    return render_template('add_order.html', suppliers=suppliers, medicines=medicines)

@app.route('/download-purchase-history', methods=['GET'])
@login_required
def download_purchase_history():
    # Get filter from query string: 'today' or 'all'
    filter_type = request.args.get('filter', 'all')
    query = StockTransaction.query.order_by(StockTransaction.transaction_date.desc())
    if filter_type == 'today':
        today = datetime.now().date()
        query = query.filter(func.date(StockTransaction.transaction_date) == today)
    transactions = query.all()

    # Generate visually appealing PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Header
    p.setFillColorRGB(0.13, 0.45, 0.71)  # Blue header
    p.rect(0, height - 70, width, 70, fill=1, stroke=0)
    p.setFillColorRGB(1, 1, 1)
    p.setFont("Helvetica-Bold", 22)
    p.drawString(50, height - 45, "RHU Inventory Purchase History")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 65, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    p.drawRightString(width - 50, height - 65, f"Filter: {'Today' if filter_type == 'today' else 'All'}")

    # Table header styling
    y = height - 90
    p.setFillColorRGB(0.9, 0.9, 0.9)
    p.rect(40, y - 5, width - 80, 25, fill=1, stroke=0)
    p.setFillColorRGB(0.13, 0.45, 0.71)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(45, y + 10, "Date")
    p.drawString(110, y + 10, "Medicine")
    p.drawString(220, y + 10, "Batch")
    p.drawString(280, y + 10, "Type")
    p.drawString(325, y + 10, "Qty")
    p.drawString(360, y + 10, "Unit Price")
    p.drawString(430, y + 10, "Total Price")
    p.drawString(510, y + 10, "By")
    p.drawString(570, y + 10, "Role")
    # Draw a visible line under the table header
    p.setStrokeColorRGB(0.13, 0.45, 0.71)
    p.setLineWidth(1.5)
    p.line(40, y - 2, width - 40, y - 2)
    y -= 25  # More spacing after header

    # Table rows
    p.setFont("Helvetica", 10)
    alt = False
    for tx in transactions:
        if y < 60:
            p.showPage()
            # Redraw header and table header on new page
            p.setFillColorRGB(0.13, 0.45, 0.71)
            p.rect(0, height - 70, width, 70, fill=1, stroke=0)
            p.setFillColorRGB(1, 1, 1)
            p.setFont("Helvetica-Bold", 22)
            p.drawString(50, height - 45, "RHU Inventory Purchase History")
            p.setFont("Helvetica", 12)
            p.drawString(50, height - 65, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            p.drawRightString(width - 50, height - 65, f"Filter: {'Today' if filter_type == 'today' else 'All'}")
            y = height - 90
            p.setFillColorRGB(0.9, 0.9, 0.9)
            p.rect(40, y - 5, width - 80, 25, fill=1, stroke=0)
            p.setFillColorRGB(0.13, 0.45, 0.71)
            p.setFont("Helvetica-Bold", 11)
            p.drawString(45, y + 10, "Date")
            p.drawString(110, y + 10, "Medicine")
            p.drawString(220, y + 10, "Batch")
            p.drawString(280, y + 10, "Type")
            p.drawString(325, y + 10, "Qty")
            p.drawString(360, y + 10, "Unit Price")
            p.drawString(430, y + 10, "Total Price")
            p.drawString(510, y + 10, "By")
            p.drawString(570, y + 10, "Role")
            p.setStrokeColorRGB(0.13, 0.45, 0.71)
            p.setLineWidth(1.5)
            p.line(40, y - 2, width - 40, y - 2)
            y -= 25
            p.setFont("Helvetica", 10)

        # Alternate row color
        if alt:
            p.setFillColorRGB(0.96, 0.98, 1)
            p.rect(40, y - 2, width - 80, 18, fill=1, stroke=0)
        alt = not alt

        # Data extraction
        date_str = tx.transaction_date.strftime('%Y-%m-%d\n%H:%M')
        medicine = tx.batch.medicine.name if tx.batch and tx.batch.medicine else "N/A"
        batch_number = tx.batch.batch_number if tx.batch else "N/A"
        tx_type = tx.transaction_type.upper()
        qty = str(tx.quantity)
        unit_price = f"{getattr(tx.batch, 'unit_price', 0):,.2f}" if tx.batch else "0.00"
        try:
            total_price = f"{float(unit_price.replace(',', '')) * tx.quantity:,.2f}"
        except Exception:
            total_price = "0.00"
        username = tx.user.username if hasattr(tx, 'user') and tx.user else str(tx.performed_by)
        role = tx.user.role if hasattr(tx, 'user') and tx.user and hasattr(tx.user, 'role') else "N/A"

        # Type color
        if tx_type == "IN":
            p.setFillColorRGB(0.2, 0.7, 0.2)  # Green
        elif tx_type == "OUT":
            p.setFillColorRGB(0.85, 0.2, 0.2)  # Red
        else:
            p.setFillColorRGB(0.2, 0.2, 0.2)  # Gray

        # Draw columns with more spacing and vertical lines
        col_x = [45, 110, 220, 280, 325, 360, 430, 510, 570, width - 40]
        p.setFont("Helvetica", 10)
        p.setFillColorRGB(0, 0, 0)
        p.drawRightString(col_x[1] - 5, y + 8, date_str)  # Date (right-aligned, multi-line)
        p.drawString(col_x[1] + 2, y + 8, medicine)
        p.drawString(col_x[2], y + 8, batch_number)
        p.setFont("Helvetica-Bold", 10)
        if tx_type == "IN":
            p.setFillColorRGB(0.2, 0.7, 0.2)
        elif tx_type == "OUT":
            p.setFillColorRGB(0.85, 0.2, 0.2)
        else:
            p.setFillColorRGB(0.2, 0.2, 0.2)
        p.drawString(col_x[3], y + 8, tx_type)
        p.setFont("Helvetica", 10)
        p.setFillColorRGB(0, 0, 0)
        p.drawString(col_x[4], y + 8, qty)
        p.drawRightString(col_x[5] + 55, y + 8, unit_price)
        p.drawRightString(col_x[6] + 70, y + 8, total_price)
        p.drawString(col_x[7], y + 8, username)
        p.drawString(col_x[8], y + 8, role)

        # Draw vertical lines for columns
        p.setStrokeColorRGB(0.7, 0.7, 0.7)
        p.setLineWidth(0.5)
        for x in col_x:
            p.line(x - 5, y - 2, x - 5, y + 16)

        y -= 20  # Increased row height for clarity

    # Footer
    p.setFillColorRGB(0.13, 0.45, 0.71)
    p.rect(0, 0, width, 30, fill=1, stroke=0)
    p.setFillColorRGB(1, 1, 1)
    p.setFont("Helvetica", 10)
    p.drawString(50, 12, "RHU Inventory System | Purchase History Report")
    p.drawRightString(width - 50, 12, f"Page 1")

    p.save()
    buffer.seek(0)
    filename = f"purchase_history_{filter_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

@app.route('/clear-transactions', methods=['POST'])
@login_required
def clear_transactions():
    # Only admin can clear all transactions
    if current_user.role != 'admin':
        flash('You do not have permission to clear transactions.', 'danger')
        return redirect(url_for('dashboard'))
    StockTransaction.query.delete()
    db.session.commit()
    flash('All transaction history cleared.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/clear-orders', methods=['POST'])
@login_required
def clear_orders():
    # Only admin can clear all orders
    if current_user.role != 'admin':
        flash('You do not have permission to clear orders.', 'danger')
        return redirect(url_for('orders'))
    # Delete all order items first to avoid integrity errors
    OrderItem.query.delete()
    # Delete all orders
    Order.query.delete()
    db.session.commit()
    flash('All orders and their items have been cleared.', 'success')
    return redirect(url_for('orders'))

# To fix this error, install the reportlab package:
# Run this command in your terminal:
# pip install reportlab

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create default admin user if it doesn't exist
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                role='admin',
                email='admin@example.com'
            )
            db.session.add(admin)
            print("Default admin user created (username: admin, password: admin123)")
        # Create 'Jan' user if it doesn't exist
        if not User.query.filter_by(username='Jan').first():
            jan_user = User(
                username='Jan',
                password=generate_password_hash('Jan123'),
                role='employee',
                email='asd@example.com'
            )
            db.session.add(jan_user)

        if not User.query.filter_by(username='Bot').first():
            bot_user = User(
                username='Bot',
                password=generate_password_hash('Bot123'),
                role='sub-admin',
                email='frafsd@gmail.com'
            )
            db.session.add(bot_user)

        db.session.commit()
        # Start the scheduler only if not already running
        try:
            if not getattr(scheduler, 'running', False):
                scheduler.start()
        except Exception as e:
            print(f"Error starting scheduler: {e}")
    app.run(debug=True, port=5000)