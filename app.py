from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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

@app.route('/inventory')
@login_required
def inventory():
    medicines = Medicine.query.all()
    return render_template('inventory.html', medicines=medicines)

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
    medicine = Medicine.query.get_or_404(id)
    db.session.delete(medicine)
    db.session.commit()
    flash('Medicine deleted successfully', 'success')
    return redirect(url_for('inventory'))

@app.route('/suppliers')
@login_required
def suppliers():
    suppliers = Supplier.query.all()
    return render_template('suppliers.html', suppliers=suppliers)

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
    supplier = Supplier.query.get_or_404(id)
    db.session.delete(supplier)
    db.session.commit()
    flash('Supplier deleted successfully', 'success')
    return redirect(url_for('suppliers'))

@app.route('/batches')
@login_required
def batches():
    batches = Batch.query.all()
    return render_template('batches.html', batches=batches)

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
        
        # Add stock transaction
        transaction = StockTransaction(
            batch_id=batch.id,
            transaction_type='in',
            quantity=batch.quantity,
            performed_by=current_user.id
        )
        db.session.add(transaction)
        db.session.commit()
        
        flash('Batch added successfully', 'success')
        return redirect(url_for('batches'))
    
    medicines = Medicine.query.all()
    return render_template('add_batch.html', medicines=medicines)

@app.route('/orders')
@login_required
def orders():
    orders = Order.query.all()
    return render_template('orders.html', orders=orders)

@app.route('/order/add', methods=['GET', 'POST'])
@login_required
def add_order():
    if request.method == 'POST':
        order = Order(
            supplier_id=request.form['supplier_id'],
            created_by=current_user.id
        )
        db.session.add(order)
        db.session.flush()  # Get the order ID
        
        # Add order items
        medicine_ids = request.form.getlist('medicine_id')
        quantities = request.form.getlist('quantity')
        unit_prices = request.form.getlist('unit_price')
        
        for i in range(len(medicine_ids)):
            if medicine_ids[i] and quantities[i]:
                order_item = OrderItem(
                    order_id=order.id,
                    medicine_id=medicine_ids[i],
                    quantity=int(quantities[i]),
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0
                )
                db.session.add(order_item)
        
        db.session.commit()
        flash('Order created successfully', 'success')
        return redirect(url_for('orders'))
    
    suppliers = Supplier.query.all()
    medicines = Medicine.query.all()
    return render_template('add_order.html', suppliers=suppliers, medicines=medicines)

@app.route('/reports')
@login_required
def reports():
    # Stock levels report
    stock_report = db.session.query(
        Medicine.name,
        db.func.sum(Batch.quantity).label('total_quantity')
    ).join(Batch).group_by(Medicine.id).all()
    
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
        db.func.sum(Batch.quantity).label('total_quantity')
    ).join(Batch).group_by(Medicine.id).all()
    
    return jsonify([{
        'medicine': item.name,
        'quantity': item.total_quantity
    } for item in stock_data])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create default admin user if it doesn't exist
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                role='manager',
                email='admin@example.com'
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created (username: admin, password: admin123)")
        
        # Start the scheduler
        try:
            scheduler.start()
        except:
            pass  # Scheduler might already be running
    
    app.run(debug=True, port=5000)