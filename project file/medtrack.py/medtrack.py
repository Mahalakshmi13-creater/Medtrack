from flask import Flask, render_template, request, redirect, session
from flask_mail import Mail, Message
import boto3
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# ---------- AWS DynamoDB Configuration ----------
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')  # Update region if needed
users_table = dynamodb.Table('users')
appointments_table = dynamodb.Table('appointments')

# ---------- AWS SNS Configuration ----------
sns = boto3.client('sns', region_name='us-east-1')  # Update region if needed

# ---------- Email (SMTP) Configuration ----------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'       # ✅ Your Gmail
app.config['MAIL_PASSWORD'] = 'your_app_password'          # ✅ Use Gmail App Password

mail = Mail(app)

# ---------- Routes ----------

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form['role']
        username = request.form['username']  # Assuming it's an email
        password = request.form['password']

        # Check if user exists
        response = users_table.get_item(Key={'username': username})
        if 'Item' in response:
            return "User already exists!"

        # Add new user
        users_table.put_item(Item={
            'username': username,
            'password': password,
            'role': role
        })

        # Send Welcome Email
        try:
            msg = Message(
                subject="Welcome to MedTrack!",
                sender=app.config['MAIL_USERNAME'],
                recipients=[username],
                body=f"Hello {username},\n\nThank you for registering as a {role} on MedTrack."
            )
            mail.send(msg)
        except Exception as e:
            print(f"Email error: {e}")

        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        response = users_table.get_item(Key={'username': username})
        user = response.get('Item')

        if user and user['password'] == password:
            session['username'] = username
            session['role'] = user['role']
            return redirect(f"/{user['role']}")
        return "Invalid credentials!"

    return render_template('login.html')


@app.route('/doctor')
def doctor_dashboard():
    if 'role' in session and session['role'] == 'doctor':
        response = appointments_table.scan()
        appointments = [a for a in response.get('Items', []) if a['doctor_email'] == session['username']]
        return render_template('doctor_dashboard.html', username=session['username'], appointments=appointments)
    return redirect('/login')


@app.route('/patient')
def patient_dashboard():
    if 'role' in session and session['role'] == 'patient':
        response = appointments_table.scan()
        appointments = [a for a in response.get('Items', []) if a['patient_email'] == session['username']]
        return render_template('patient_dashboard.html', username=session['username'], appointments=appointments)
    return redirect('/login')


@app.route('/book', methods=['GET', 'POST'])
def book_appointment():
    if 'role' not in session or session['role'] != 'patient':
        return redirect('/login')

    if request.method == 'POST':
        doctor_email = request.form['doctor_email']
        patient_email = session['username']
        date = request.form['date']
        reason = request.form['reason']

        appointment_id = str(uuid.uuid4())

        # Save appointment to DynamoDB
        appointments_table.put_item(Item={
            'appointment_id': appointment_id,
            'doctor_email': doctor_email,
            'patient_email': patient_email,
            'date': date,
            'reason': reason,
            'timestamp': datetime.utcnow().isoformat()
        })

        # Send Email Notification to Doctor
        try:
            msg = Message(
                subject="New Appointment Booked",
                sender=app.config['MAIL_USERNAME'],
                recipients=[doctor_email],
                body=f"You have a new appointment from {patient_email} on {date}.\nReason: {reason}"
            )
            mail.send(msg)
        except Exception as e:
            print(f"Email error: {e}")

        # Send SMS Notification using SNS (number must be verified in AWS SNS sandbox)
        try:
            sns.publish(
                PhoneNumber='+15555555555',  # Replace with actual/verified number
                Message=f"New appointment: {patient_email} -> {doctor_email} on {date}"
            )
        except Exception as e:
            print(f"SNS error: {e}")

        return "Appointment booked successfully!"

    return render_template('book_appointment.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)
