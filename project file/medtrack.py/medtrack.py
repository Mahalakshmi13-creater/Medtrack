from flask import Flask, render_template, request, redirect, session, url_for, flash
import boto3
from datetime import datetime
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(_name_)
app.secret_key = 'your-secret-key'

# ---------------- AWS CONFIG ----------------
REGION = 'us-east-1'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns = boto3.client('sns', region_name=REGION)

user_table = dynamodb.Table('UsersTable')
appointment_table = dynamodb.Table('AppointmentsTable')

ENABLE_EMAIL = True
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SENDER_EMAIL = 'your_email@gmail.com'
SENDER_PASSWORD = 'your_app_password'
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:727646474213:notifications:420ef00c-2702-4d49-aa9f-4a06a2c6939e"  # Optional

# ---------------- EMAIL FUNCTION ----------------
def send_email(to_email, subject, body):
    if not ENABLE_EMAIL:
        return
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Email error: {e}")

# ---------------- ROUTES ----------------
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form['role']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        age = request.form['age']
        gender = request.form['gender']
        spec = request.form.get('specialization', '')

        existing = user_table.get_item(Key={'email': email}).get('Item')
        if existing:
            flash('User already exists.', 'danger')
            return redirect('/register')

        user = {
            'email': email,
            'name': name,
            'password': password,
            'age': age,
            'gender': gender,
            'role': role,
            'created_at': datetime.now().isoformat(),
        }
        if role == 'doctor':
            user['specialization'] = spec

        user_table.put_item(Item=user)

        send_email(email, "Welcome to MedTrack", f"Hi {name},\nThanks for registering as a {role}.")

        if SNS_TOPIC_ARN:
            sns.publish(TopicArn=SNS_TOPIC_ARN, Subject="New Registration", Message=f"New {role}: {email}")

        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        user = user_table.get_item(Key={'email': email}).get('Item')
        if user and user['password'] == password and user['role'] == role:
            session['email'] = email
            session['role'] = role
            session['name'] = user['name']
            return redirect('/dashboard')
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect('/login')
    return render_template('dashboard.html', role=session['role'])

@app.route('/doctor')
def doctor_dashboard():
    email = session.get('email')
    response = appointment_table.scan(
        FilterExpression='doctor_email = :email',
        ExpressionAttributeValues={':email': email}
    )
    return render_template('doctor_dashboard.html', appointments=response['Items'])

@app.route('/patient')
def patient_dashboard():
    email = session.get('email')
    appointments = appointment_table.scan(
        FilterExpression='patient_email = :email',
        ExpressionAttributeValues={':email': email}
    )['Items']
    doctors = user_table.scan(
        FilterExpression='role = :role',
        ExpressionAttributeValues={':role': 'doctor'}
    )['Items']
    return render_template('patient_dashboard.html', appointments=appointments, doctors=doctors)

@app.route('/book_appointment', methods=['GET', 'POST'])
def book_appointment():
    if request.method == 'POST':
        doctor_email = request.form['doctor_email']
        symptoms = request.form['symptoms']
        date = request.form['appointment_date']

        appointment = {
            'appointment_id': str(uuid.uuid4()),
            'doctor_email': doctor_email,
            'patient_email': session['email'],
            'doctor_name': user_table.get_item(Key={'email': doctor_email}).get('Item', {}).get('name', 'Doctor'),
            'patient_name': session['name'],
            'symptoms': symptoms,
            'status': 'pending',
            'appointment_date': date,
            'created_at': datetime.now().isoformat()
        }
        appointment_table.put_item(Item=appointment)

        send_email(doctor_email, "New Appointment", f"New appointment from {session['name']} on {date}")
        send_email(session['email'], "Appointment Booked", f"You booked an appointment with Dr. {appointment['doctor_name']}")

        return redirect('/patient')

    doctors = user_table.scan(
        FilterExpression='role = :role',
        ExpressionAttributeValues={':role': 'doctor'}
    )['Items']
    return render_template('book_appointment.html', doctors=doctors)

@app.route('/view_appointment/<appointment_id>', methods=['GET', 'POST'])
def view_appointment(appointment_id):
    appt = appointment_table.get_item(Key={'appointment_id': appointment_id}).get('Item')
    if not appt:
        return "Not found", 404

    if request.method == 'POST' and session['role'] == 'doctor':
        diagnosis = request.form['diagnosis']
        treatment = request.form['treatment_plan']
        prescription = request.form['prescription']

        appointment_table.update_item(
            Key={'appointment_id': appointment_id},
            UpdateExpression="SET diagnosis = :d, treatment_plan = :t, prescription = :p, #status = :s",
            ExpressionAttributeValues={
                ':d': diagnosis,
                ':t': treatment,
                ':p': prescription,
                ':s': 'completed'
            },
            ExpressionAttributeNames={"#status": "status"}
        )

        send_email(appt['patient_email'], "Appointment Completed", f"Diagnosis: {diagnosis}\nTreatment: {treatment}")
        return redirect('/doctor')

    template = 'view_appointment_doctor.html' if session['role'] == 'doctor' else 'view_appointment_patient.html'
    return render_template(template, appointment=appt)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if _name_ == '_main_':
    app.run(debug=True)
