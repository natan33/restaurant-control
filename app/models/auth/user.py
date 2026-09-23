from datetime import datetime, timezone
from app import db 
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class User(db.Model,UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    reset_code = db.Column(db.String(100), nullable=True)

    last_seen_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Gerado no momento do insert
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relacionamento
    registrations = db.relationship('Registration', backref='owner', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'
    
    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()
    
   
 


class Registration(db.Model):
    __tablename__ = 'registrations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    status = db.Column(db.String(20), default='pending')

    last_seen_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # SENIOR TIP: onupdate garante que o Postgres/SQLAlchemy atualize a data 
    # automaticamente em cada modificação do registro.
    update_at = db.Column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f'<Registration {self.id} for User {self.user_id}>'
    
    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()