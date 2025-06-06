from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Supplier, Medicine, Batch, Order, OrderItem, StockTransaction
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
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
    # Check for medicines expiring in the next 30 days
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

    # Setup the email server and send the message
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
scheduler.start()

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
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    low_stock = Batch.query.filter(Batch.quantity <= 10).all()
    expiring_soon = Batch.query.filter(
        Batch.expiration_date <= datetime.now().date() + timedelta(days=30)
    ).all()
    return render_template('dashboard.html', low_stock=low_stock, expiring_soon=expiring_soon)

@app.route('/inventory')
@login_required
def inventory():
    medicines = Medicine.query.all()
    return render_template('inventory.html', medicines=medicines)

@app.route('/suppliers')
@login_required
def suppliers():
    suppliers = Supplier.query.all()
    return render_template('suppliers.html', suppliers=suppliers)

@app.route('/orders')
@login_required
def orders():
    orders = Order.query.all()
    return render_template('orders.html', orders=orders)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create admin user if it doesn't exist
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                role='manager',
                email='admin@example.com'
            )
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)