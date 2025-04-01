from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import datetime
from functools import wraps
import os
import re
from dotenv import load_dotenv
from sqlalchemy import false

load_dotenv()  # Load environment variables from .env file

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:qazaq001@localhost/pet_store')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'your_very_strong_secret_key_here')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# Association tables
user_product = db.Table('user_product',
                        db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
                        db.Column('product_id', db.Integer, db.ForeignKey('product.id'), primary_key=True)
                        )

user_pet = db.Table('user_pet',
                    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
                    db.Column('pet_id', db.Integer, db.ForeignKey('pet.id'), primary_key=True)
                    )


# Models
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vet_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default="pending")
    date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('user_appointments', lazy=True))
    vet = db.relationship('User', foreign_keys=[vet_id], backref=db.backref('vet_appointments', lazy=True))


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=False, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='customer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship('Product', secondary=user_product, backref='buyers')
    pets = db.relationship('Pet', secondary=user_pet, backref='owners')
    sold_products = db.relationship('Product', backref='seller', lazy=True)
    sold_pets = db.relationship('Pet', backref='seller', lazy=True)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Pet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(100), nullable=False)
    breed = db.Column(db.String(100))
    age = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Helper functions and decorators
def role_required(role):
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            current_user = get_jwt_identity()
            if current_user['role'] != role:
                return jsonify({'message': f'Only {role}s can access this'}), 403
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def validate_email(email):
    """Simple email validation function."""
    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(email_regex, email)


# Error handlers
@app.errorhandler(400)
def bad_request(error):
    return jsonify({'message': 'Bad request'}), 400


@app.errorhandler(404)
def not_found(error):
    return jsonify({'message': 'Resource not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'message': 'Internal server error'}), 500


# Auth routes
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    # Check that all required fields are provided
    required_fields = ['username', 'email', 'password']
    if not data or not all(field in data for field in required_fields):
        return jsonify({'message': 'Username, email and password are required'}), 400

    # Validate email format
    if not validate_email(data['email']):
        return jsonify({'message': 'Invalid email format'}), 400

    # Check if email already exists
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'User with this email already exists'}), 400

    # Check if username already exists
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': 'Username already taken'}), 400

    # Hash the password
    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')

    # Create new user
    new_user = User(
        username=data['username'],
        email=data['email'],
        password=hashed_pw,
        role='customer'
    )

    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'User registered successfully'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'message': 'Email and password are required'}), 400

    user = User.query.filter_by(email=data['email']).first()

    if user and bcrypt.check_password_hash(user.password, data['password']):
        # Create token with proper identity
        access_token = create_access_token(identity={
            'id': user.id,
            'email': user.email,
            'role': user.role
        })
        return jsonify({
            'access_token': access_token,
            'user': {
                'id': user.id,
                'email': user.email,
                'role': user.role
            }
        }), 200

    return jsonify({'message': 'Invalid credentials'}), 401


# Product routes
@app.route('/products', methods=['GET'])
def get_all_products():
    products = Product.query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'price': p.price,
        'stock': p.stock,
        'seller_id': p.seller_id
    } for p in products])


@app.route('/products', methods=['POST'])
@role_required('seller')
def create_product():
    data = request.get_json()
    if not data or not data.get('name') or not data.get('price') or not data.get('stock'):
        return jsonify({'message': 'Name, price, and stock are required'}), 400

    current_user = get_jwt_identity()
    new_product = Product(
        name=data['name'],
        description=data.get('description', ''),
        price=float(data['price']),
        stock=int(data['stock']),
        seller_id=current_user['id']
    )
    db.session.add(new_product)
    db.session.commit()
    return jsonify({'message': 'Product added', 'id': new_product.id}), 201


@app.route('/products/<int:product_id>', methods=['PUT'])
@jwt_required()
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    current_user = get_jwt_identity()

    if product.seller_id != current_user['id']:
        return jsonify({'message': 'Only the seller can update the product'}), 403

    data = request.get_json()
    if 'name' in data:
        product.name = data['name']
    if 'description' in data:
        product.description = data['description']
    if 'price' in data:
        product.price = float(data['price'])
    if 'stock' in data:
        product.stock = int(data['stock'])

    db.session.commit()
    return jsonify({'message': 'Product updated'})


@app.route('/products/<int:product_id>', methods=['DELETE'])
@jwt_required()
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    current_user = get_jwt_identity()

    if product.seller_id != current_user['id'] and current_user['role'] != 'admin':
        return jsonify({'message': 'Only the seller or admin can delete the product'}), 403

    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted'})


# Pet routes
@app.route('/pets', methods=['GET'])
def get_all_pets():
    pets = Pet.query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'species': p.species,
        'breed': p.breed,
        'age': p.age,
        'price': p.price,
        'seller_id': p.seller_id
    } for p in pets])


@app.route('/pets', methods=['POST'])
@role_required('seller')
def create_pet():
    data = request.get_json()
    if not data or not data.get('name') or not data.get('species') or not data.get('age') or not data.get('price'):
        return jsonify({'message': 'Name, species, age, and price are required'}), 400

    current_user = get_jwt_identity()
    new_pet = Pet(
        name=data['name'],
        species=data['species'],
        breed=data.get('breed', ''),
        age=int(data['age']),
        price=float(data['price']),
        seller_id=current_user['id']
    )
    db.session.add(new_pet)
    db.session.commit()
    return jsonify({'message': 'Pet added', 'id': new_pet.id}), 201


@app.route('/pets/<int:pet_id>', methods=['PUT'])
@jwt_required()
def update_pet(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    current_user = get_jwt_identity()

    if pet.seller_id != current_user['id']:
        return jsonify({'message': 'Only the seller can update the pet'}), 403

    data = request.get_json()
    if 'name' in data:
        pet.name = data['name']
    if 'species' in data:
        pet.species = data['species']
    if 'breed' in data:
        pet.breed = data['breed']
    if 'age' in data:
        pet.age = int(data['age'])
    if 'price' in data:
        pet.price = float(data['price'])

    db.session.commit()
    return jsonify({'message': 'Pet updated'})


@app.route('/pets/<int:pet_id>', methods=['DELETE'])
@jwt_required()
def delete_pet(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    current_user = get_jwt_identity()

    if pet.seller_id != current_user['id'] and current_user['role'] != 'admin':
        return jsonify({'message': 'Only the seller or admin can delete the pet'}), 403

    db.session.delete(pet)
    db.session.commit()
    return jsonify({'message': 'Pet deleted'})


# Appointment routes
@app.route('/appointments', methods=['GET'])
@jwt_required()
def get_all_appointments():
    current_user = get_jwt_identity()

    if current_user['role'] == 'vet':
        appointments = Appointment.query.filter_by(vet_id=current_user['id']).all()
    elif current_user['role'] == 'customer':
        appointments = Appointment.query.filter_by(user_id=current_user['id']).all()
    else:
        return jsonify({'message': 'Unauthorized'}), 403

    return jsonify([{
        'id': a.id,
        'user_id': a.user_id,
        'vet_id': a.vet_id,
        'status': a.status,
        'date': a.date.isoformat(),
        'created_at': a.created_at.isoformat(),
        'updated_at': a.updated_at.isoformat()
    } for a in appointments])


@app.route('/appointments', methods=['POST'])
@role_required('customer')
def create_appointment():
    data = request.get_json()
    if not data or not data.get('vet_id') or not data.get('date'):
        return jsonify({'message': 'Vet ID and date are required'}), 400

    try:
        appointment_date = datetime.fromisoformat(data['date'])
    except (ValueError, TypeError):
        return jsonify({'message': 'Invalid date format'}), 400

    current_user = get_jwt_identity()

    vet = User.query.get(data['vet_id'])
    if not vet or vet.role != 'vet':
        return jsonify({'message': 'Invalid vet'}), 400

    new_appointment = Appointment(
        user_id=current_user['id'],
        vet_id=data['vet_id'],
        status="pending",
        date=appointment_date
    )
    db.session.add(new_appointment)
    db.session.commit()
    return jsonify({'message': 'Appointment booked', 'id': new_appointment.id}), 201


@app.route('/appointments/<int:appointment_id>', methods=['PUT'])
@jwt_required()
def update_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    current_user = get_jwt_identity()

    if current_user['role'] == 'vet' and appointment.vet_id == current_user['id']:
        data = request.get_json()
        if 'status' in data and data['status'] in ['pending', 'approved', 'rejected', 'cancelled']:
            appointment.status = data['status']
            db.session.commit()
            return jsonify({'message': 'Appointment updated'})
        return jsonify({'message': 'Invalid status'}), 400
    elif current_user['role'] == 'customer' and appointment.user_id == current_user['id']:
        return jsonify({'message': 'Customers can only cancel appointments'}), 403
    return jsonify({'message': 'Unauthorized'}), 403


@app.route('/appointments/<int:appointment_id>', methods=['DELETE'])
@jwt_required()
def cancel_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    current_user = get_jwt_identity()

    if (current_user['role'] == 'customer' and appointment.user_id == current_user['id']) or \
            (current_user['role'] == 'vet' and appointment.vet_id == current_user['id']):
        db.session.delete(appointment)
        db.session.commit()
        return jsonify({'message': 'Appointment cancelled'})
    return jsonify({'message': 'Unauthorized'}), 403


# Admin routes
@app.route('/users', methods=['GET'])
@role_required('admin')
def get_all_users():
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'role': u.role,
        'created_at': u.created_at.isoformat()
    } for u in users])


@app.route('/users/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'})

# Initialize database (this creates all tables in the database)
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
