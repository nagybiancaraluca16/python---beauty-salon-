from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer as Serializer
from dotenv import load_dotenv
import os
import calendar
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)  # Corrected from app = Flask(_name_)
app.secret_key = 'secret_key_for_session'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mail Config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

mail = Mail(app)
db = SQLAlchemy(app)

# Serializer for token generation
serializer = Serializer(app.secret_key)

# Many-to-many relationship table for Service and Employee
service_employee = db.Table('service_employee',
    db.Column('service_id', db.Integer, db.ForeignKey('service.id'), primary_key=True),
    db.Column('employee_id', db.Integer, db.ForeignKey('employee.id'), primary_key=True)
)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default='client')

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    specialty = db.Column(db.String(150))
    services = db.relationship('Service', secondary=service_employee, backref=db.backref('employees', lazy='dynamic'))

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Float)  # Add the price field to the Service model


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    service = db.Column(db.String(100))
    date = db.Column(db.String(100))
    time = db.Column(db.String(100))
    user = db.relationship('User', backref='appointments')
    employee = db.relationship('Employee', backref='appointments')



# Helper function to get days of a month
def get_days_in_month(year, month):
    month_days = calendar.monthcalendar(year, month)
    return month_days

# Routes for login, register, forgot password, etc.

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['user_id'] = user.id
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))  # Admin dashboard
            else:
                return redirect(url_for('dashboard'))  # Regular user dashboard
        flash('Login failed!')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        existing_user = User.query.filter(
            (User.username == request.form['username']) | 
            (User.email == request.form['email'])
        ).first()
        if existing_user:
            flash('Acest username sau email există deja!')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(request.form['password'])
        new_user = User(username=request.form['username'], email=request.form['email'], password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash('Cont creat! Te poți loga acum.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            token = serializer.dumps(user.email)
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message("Resetare Parolă", sender=app.config['MAIL_USERNAME'], recipients=[email])
            msg.body = f"Click here to reset your password: {reset_url}"
            try:
                mail.send(msg)
                flash('Check your email for password reset instructions.')
            except Exception as e:
                flash(f'Error sending email: {str(e)}')
            return redirect(url_for('login'))
        flash('No user found with that email!')
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, max_age=3600)  # token valid for 1 hour
    except:
        flash('Invalid or expired token')
        return redirect(url_for('login'))
    if request.method == 'POST':
        new_password = generate_password_hash(request.form['password'])
        user = User.query.filter_by(email=email).first()
        user.password = new_password
        db.session.commit()
        flash('Password successfully updated!')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    appointments = Appointment.query.filter_by(user_id=user.id).all()
    return render_template('dashboard.html', user=user, appointments=appointments)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/book', methods=['GET', 'POST'])
def book():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Get the selected service from the form
    selected_service = request.form.get('service') or request.args.get('service')
    selected_employee = request.form.get('employee')  # Retain selected employee
    employees = []
    services = Service.query.all()  # Fetch services with their prices

    if selected_service:
        # Fetch the service by its ID and the employees associated with the selected service
        selected_service = Service.query.get(int(selected_service))  # Correctly fetch the service by its ID
        employees = Employee.query.join(service_employee).join(Service).filter(Service.id == selected_service.id).all()

    # Get the current month, year, and day for the calendar
    current_month = int(request.args.get('month', datetime.now().month))
    current_year = int(request.args.get('year', datetime.now().year))
    current_day = datetime.now().day  # This is today's date

    # Get the days in the selected month
    days_in_month = get_days_in_month(current_year, current_month)
    month_name = calendar.month_name[current_month]

    # Fetch booked appointments and extract the times
    booked_appointments = Appointment.query.filter_by(user_id=session['user_id']).all()
    booked_times = [appt.time for appt in booked_appointments]  # Only store times

    if request.method == 'POST' and 'confirm' in request.form:
        service_id = request.form['service']
        date = request.form['date']
        time = request.form['time']
        employee_id = request.form['employee']

        # Prevent double booking for the same date, time, and employee
        existing_appointment = Appointment.query.filter_by(date=date, time=time, employee_id=employee_id).first()
        if existing_appointment:
            flash('Această oră este deja rezervată pentru angajatul ales.')
            return redirect(url_for('book'))

        selected_service = Service.query.get(service_id)  # Get service details for selected service
        new_appt = Appointment(user_id=session['user_id'], employee_id=employee_id, service=selected_service.name, date=date, time=time)
        db.session.add(new_appt)
        db.session.commit()

        user = User.query.get(session['user_id'])
        msg = Message("Confirmare Programare", sender=app.config['MAIL_USERNAME'], recipients=[user.email])
        msg.body = f"Bună {user.username}, ai o programare pentru {selected_service.name} cu angajatul {employee_id} pe data de {date} la ora {time}."
        try:
            mail.send(msg)
        except:
            print("Email could not be sent.")

        flash('Programare adăugată!')
        return redirect(url_for('dashboard'))

    return render_template('book.html', 
                           selected_service=selected_service,  # Pass the selected service to template
                           selected_employee=selected_employee, 
                           employees=employees, 
                           services=services,  # Pass services with prices
                           current_month=current_month, 
                           current_year=current_year, 
                           days_in_month=days_in_month, 
                           month_name=month_name,
                           current_day=current_day, 
                           booked_times=booked_times)






@app.route('/get_booked_times', methods=['GET'])
def get_booked_times():
    date = request.args.get('date')  # Get the date from the frontend
    print(f"Fetching booked times for date: {date}")
    booked_appointments = Appointment.query.filter_by(date=date).all()
    booked_times = [appt.time for appt in booked_appointments]  # Extract booked times
    print(f"Booked times: {booked_times}")  # Debug the data being fetched
    return jsonify(booked_times)



@app.route('/confirm_appointment', methods=['GET', 'POST'])
def confirm_appointment():
    # Get the parameters from the URL
    service_id = request.args.get('service')
    date = request.args.get('date')
    time = request.args.get('time')
    employee_id = request.args.get('employee')
    
    # Fetch service and employee details
    selected_service = Service.query.get(service_id)
    selected_employee = Employee.query.get(employee_id)
    
    if request.method == 'POST':
        # If the form is submitted, confirm the appointment
        new_appt = Appointment(
            user_id=session['user_id'],
            service=selected_service.name,
            date=date,
            time=time,
            employee_id=employee_id
        )
        db.session.add(new_appt)
        db.session.commit()

        flash('Programare confirmată!')
        return redirect(url_for('dashboard'))

    # Render the confirmation page
    return render_template('confirm_appointment.html', 
                           selected_service=selected_service, 
                           selected_employee=selected_employee, 
                           selected_date=date, 
                           selected_time=time)


# Populating the database for employees, services, and the service_employee relationship
def populate_db():
    with app.app_context():
        db.create_all()

        # Add employees and services only if they do not exist
        if not Employee.query.first():
            db.session.add_all([
                Employee(name='Ana Pop', specialty='Tuns'),
                Employee(name='Maria Ionescu', specialty='Manichiura'),
                Employee(name='Alex Georgescu', specialty='Masaj'),
                Employee(name='Ion Popescu', specialty='Vopsit'),
                Employee(name='Livia Pavel', specialty='Pedichiura')
            ])
            db.session.commit()

        if not Service.query.first():
            db.session.add_all([
                Service(name='Tuns', price=100.0),  # Add price here
                Service(name='Vopsit', price=150.0),  # Add price here
                Service(name='Manichiura', price=80.0),  # Add price here
                Service(name='Pedichiura', price=90.0),  # Add price here
                Service(name='Masaj', price=120.0)  # Add price here
            ])
            db.session.commit()

        # Populate the service_employee relationship table
        if not db.session.query(service_employee).first():
            employees = Employee.query.all()
            services = Service.query.all()

            # Manually assign services to employees
            for employee in employees:
                if employee.specialty == 'Tuns':
                    employee.services.append(services[0])  # Tuns
                elif employee.specialty == 'Manichiura':
                    employee.services.append(services[2])  # Manichiura
                elif employee.specialty == 'Masaj':
                    employee.services.append(services[4])  # Masaj
                elif employee.specialty == 'Vopsit':
                    employee.services.append(services[1])  # Vopsit
                elif employee.specialty == 'Pedichiura':
                    employee.services.append(services[3])  # Pedichiura

            db.session.commit()


# Cancel appointment route (add this after all other routes)
@app.route('/cancel_appointment/<int:appointment_id>', methods=['GET', 'POST'])
def cancel_appointment(appointment_id):
    # Check if the user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get the appointment to be canceled
    appointment = Appointment.query.get(appointment_id)
    
    # Ensure that the appointment exists and that the logged-in user is the owner
    if appointment and appointment.user_id == session['user_id']:
        db.session.delete(appointment)  # Delete the appointment
        db.session.commit()
        flash('Programarea a fost anulată cu succes!')  # Success message for cancellation
    else:
        flash('Programarea nu a fost găsită sau nu ai permisiunea de a o anula.')  # Error message if appointment doesn't exist or isn't owned by the user
    
    return redirect(url_for('dashboard'))  # Redirect back to the dashboard

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    
    if user.role != 'admin':
        flash('You do not have permission to access this page.')
        return redirect(url_for('dashboard'))  # Redirect to normal user dashboard
    
    # Fetch all appointments, or anything that should be displayed on the admin dashboard
    appointments = Appointment.query.all()
    
    return render_template('admin_dashboard.html', appointments=appointments, user=user)


if __name__ == '__main__':
    populate_db()
    app.run(debug=True)
