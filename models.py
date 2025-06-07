from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # pharmacist, manager, assistant
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    medicines = db.relationship('Medicine', backref='supplier', lazy=True)
    orders = db.relationship('Order', backref='supplier', lazy=True)

    def __repr__(self):
        return f'<Supplier {self.name}>'

class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    generic_name = db.Column(db.String(100))
    category = db.Column(db.String(50))
    unit = db.Column(db.String(20))  # e.g., tablets, bottles, etc.
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    batches = db.relationship('Batch', backref='medicine', lazy=True)
    order_items = db.relationship('OrderItem', backref='medicine', lazy=True)

    @property
    def total_quantity(self):
        """Calculate total quantity across all batches"""
        return sum(batch.quantity for batch in self.batches)

    @property
    def available_batches(self):
        """Get batches with quantity > 0"""
        return [batch for batch in self.batches if batch.quantity > 0]

    def __repr__(self):
        return f'<Medicine {self.name}>'

class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_number = db.Column(db.String(50), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    expiration_date = db.Column(db.Date, nullable=False)
    manufacturing_date = db.Column(db.Date)
    unit_price = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('StockTransaction', backref='batch', lazy=True)

    @property
    def is_expired(self):
        """Check if batch is expired"""
        return self.expiration_date < datetime.now().date()

    @property
    def days_until_expiration(self):
        """Calculate days until expiration"""
        delta = self.expiration_date - datetime.now().date()
        return delta.days

    @property
    def is_expiring_soon(self, days=30):
        """Check if batch is expiring within specified days"""
        return 0 <= self.days_until_expiration <= days

    def __repr__(self):
        return f'<Batch {self.batch_number} - {self.medicine.name}>'

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, delivered, cancelled
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    creator = db.relationship('User', backref='orders')

    @property
    def total_amount(self):
        """Calculate total order amount"""
        return sum(item.total_price for item in self.items)

    @property
    def total_items(self):
        """Calculate total number of items"""
        return sum(item.quantity for item in self.items)

    def __repr__(self):
        return f'<Order #{self.id} - {self.supplier.name}>'

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    medicine_id = db.Column(db.Integer, db.ForeignKey('medicine.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float)

    @property
    def total_price(self):
        """Calculate total price for this item"""
        return (self.unit_price or 0) * self.quantity

    def __repr__(self):
        return f'<OrderItem {self.medicine.name} - {self.quantity} units>'
    
class StockTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # in, out
    quantity = db.Column(db.Integer, nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    performed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes = db.Column(db.String(200))
    
    # Relationships
    user = db.relationship('User', backref='transactions')

    def __repr__(self):
        return f'<Transaction {self.transaction_type} - {self.batch.medicine.name}>'