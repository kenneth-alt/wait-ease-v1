import os
from dotenv import load_dotenv
from flask import Flask, render_template, url_for, redirect, flash, session, logging, request
from flask_mysqldb import MySQL
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from wtforms import Form, StringField, FileField, PasswordField, validators, EmailField
from flask_wtf.file import FileAllowed, FileSize, FileRequired
from wtforms.validators import DataRequired, EqualTo, Email, Length
from passlib.hash import sha256_crypt
from functools import wraps
import qrcode

load_dotenv()

app = Flask(__name__)
Bootstrap(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Config MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

# Init MySQL
mysql = MySQL(app)

# Homepage
@app.route('/')
def homepage():
    return render_template('homepage.html')

# How it works
@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

# Registration form with flask-WTF
class RegistrationForm(Form):
    business_name = StringField('Business Name', validators=[DataRequired(), Length(min=1, max=100)])
    email = StringField('Email', validators=[DataRequired(), Length(min=1, max=100), Email()])
    phone_number = StringField('Phone Number', validators=[DataRequired(), Length(min=1, max=50)])
    password = PasswordField('Password', validators=[DataRequired(), EqualTo('confirm', message='Passwords do not match')])
    confirm = PasswordField('Confirm Password')

# User Registration
@app.route('/register', methods=['POST', 'GET'])
def register():
    form = RegistrationForm(request.form)
    if request.method == 'POST' and form.validate():
        business_name = form.business_name.data
        email = form.email.data
        phone_number = form.phone_number.data
        password = sha256_crypt.encrypt(str(form.password.data))
        
        # Create cursor
        cur = mysql.connection.cursor()
        
        # Execute querry
        cur.execute("INSERT INTO clients(business_name, email, phone_number, password) VALUES(%s, %s, %s, %s)", (business_name, email, phone_number, password))
        
        # Commit to DB
        mysql.connection.commit()
    
        # Close connection
        cur.close()
        
        flash('Registration Sucessful, You can login to create your first Queue!', 'success')
        
        return redirect(url_for('homepage'))
 
    # Handle GET request (initial form display)
    return render_template('register.html', form=form)


# User Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method =='POST':
        # Get email and password from form fields
        user_email = request.form['user_email']
        user_password = request.form['user_password']
        
        # create cursor
        cur = mysql.connection.cursor()
        
        # Get clients by email
        result = cur.execute("SELECT * FROM clients WHERE email = %s", [user_email])
        if result > 0:
            # Get stored hash
            data = cur.fetchone()
            id = data['id']
            business_name = data['business_name']
            password = data['password']
            
            # Compare passwords
            if sha256_crypt.verify(user_password, password):
                # Passed
                session['logged_in'] = True
                session['id'] = id
                session['user_email'] = user_email
                session['business_name'] = business_name
                
                flash('Successfully Logged in', 'success')
                return redirect(url_for('dashboard'))
            else:
                error = 'Invalid Login Credentials'
                return render_template('login.html', error=error)
            # Close connection
            cur.close()

        else:
            error = 'Client with this Login details does not exist'
            return render_template('login.html', error=error)
        
    return render_template('login.html')


# Check if user is logged in
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please Login!', 'danger')
            return redirect(url_for('login'))
    return wrap

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('You are now logged out!', 'success')
    return redirect(url_for('homepage'))  


# Dashboard
@app.route('/dashboard', methods=['GET', 'POST'])
@is_logged_in
def dashboard():
    # Create cursor
    cur = mysql.connection.cursor()
    
    # Get the queues for the logged-in client
    cur.execute("SELECT * FROM queues WHERE created_by_client_id = %s", (session['id'],))
    queues = cur.fetchall()
    
    # Get the selected queue ID from the URL parameter
    selected_queue_id = request.args.get('queue_id')
    selected_queue_name = request.args.get('queue_name')

    # Get the attendees table name for the selected queue
    selected_queue_name = None
    attendees_table_name = None
    attendees = []  # Initialize the attendees list
    if selected_queue_id:
        cur.execute("SELECT queue_name FROM queues WHERE id = %s", (selected_queue_id,))
        queue_data = cur.fetchone()
        if queue_data:
            selected_queue_name = queue_data['queue_name']
            attendees_table_name = f"{selected_queue_name.replace(' ', '_')}_attendees"

            # Get the attendees for the selected queue
            if attendees_table_name:
                cur.execute(f"SELECT * FROM {attendees_table_name}")
                attendees = cur.fetchall()
                
            # Delete Queue
            if request.method == 'POST' and selected_queue_id:
                # Get the selected queue ID from the URL parameter
                queue_id_to_delete = selected_queue_id
                
                # Delete the queue
                cur.execute("DELETE FROM queues WHERE id = %s", (queue_id_to_delete,))

                # Delete the corresponding attendees table
                attendees_table_name = f"{selected_queue_name.replace(' ', '_')}_attendees"
                cur.execute(f"DROP TABLE IF EXISTS {attendees_table_name}")

                # Commit to DB
                mysql.connection.commit()
                
                flash('Queue Deleted Successfully!', 'success')
                
                return redirect(url_for('dashboard'))

            # Close connection
            cur.close()
    
    return render_template('dashboard.html', queues=queues, attendees=attendees, selected_queue_id=selected_queue_id, selected_queue_name=selected_queue_name)


# Add queue
@app.route('/add_queue', methods=['GET', 'POST'])
@is_logged_in
def add_queue():
    if request.method == 'POST':
        # Get queue data from form fields
        queue_name = request.form['queue_name']
        purpose = request.form['purpose']
        instructions = request.form['instructions']
        
        # Create cursor
        cur = mysql.connection.cursor()
        
        # Execute querry
        cur.execute("INSERT INTO queues(queue_name, purpose, instructions, created_by_client_id) VALUES(%s, %s, %s, %s)", (queue_name, purpose, instructions, session['id']))
        
        # Commit to DB
        mysql.connection.commit()
        
        # Create a new table for attendees dynamically
        attendees_table_name = f"{queue_name.replace(' ', '_')}_attendees"
        create_table_query = f"""
            CREATE TABLE {attendees_table_name} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                account_number VARCHAR(255),
                service_requested TEXT,
                queue_id INT,
                FOREIGN KEY (queue_id) REFERENCES queues(id)
            )
        """
        cur.execute(create_table_query)

        # Commit to DB
        mysql.connection.commit()
        
        # Generate link for attendees to join the queue
        join_link = url_for('join_queue', queue_name=queue_name, _external=True)

        # Generate QR code
        qr = qrcode.QRCode()
        qr.add_data(join_link)
        qr.make(fit=True)
        qr_img = qr.make_image()

        # Save QR code image
        qr_img_path = f"static/qr_codes/{queue_name.replace(' ', '_')}_qr_code.png"
        qr_img.save(qr_img_path)
    
        # Close connection
        cur.close()
        
        flash('Queue Successfully Added!, You can manage your queue from your Dashboard.', 'success')
        
        return redirect(url_for('dashboard'))
 
    # Handle GET request (initial form display)
    return render_template('add_queue.html')


# join Queue
@app.route('/join_queue/<queue_name>', methods=['GET', 'POST'])
def join_queue(queue_name):
    if request.method == 'POST':
        # Get attendee data from form fields
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        account_number = request.form['account_number']
        service_requested = request.form['service_requested']
        
        # Create cursor
        cur = mysql.connection.cursor()
        
        # Get queue_id based on queue_name
        cur.execute("SELECT id FROM queues WHERE queue_name = %s", (queue_name,))
        queue_id = cur.fetchone()['id']
        
        # Execute query to add attendee to attendees table
        cur.execute("INSERT INTO attendees (first_name, last_name, account_number, service_requested, queue_id) VALUES (%s, %s, %s, %s, %s)",
                    (first_name, last_name, account_number, service_requested, queue_id))
        
        # Commit to DB
        mysql.connection.commit()
    
        # Close connection
        cur.close()
        
        flash('You have successfully joined the queue!', 'success')
        
        # Redirect to a separate page where attendees can see their position in the queue
        return redirect(url_for('queue_status', queue_id=queue_id))
 
    # Handle GET request (initial form display)
    return render_template('join_queue.html', queue_name=queue_name, business_name=session['business_name'])


# Queue Status
@app.route('/queue_status/<int:queue_id>')
def queue_status(queue_id):
    # Create cursor
    cur = mysql.connection.cursor()
    
    # Get queue name based on queue_id
    cur.execute("SELECT queue_name FROM queues WHERE id = %s", (queue_id,))
    queue_name = cur.fetchone()['queue_name']
    
    # Get the position of the current attendee in the queue
    cur.execute("SELECT COUNT(*) FROM attendees WHERE queue_id = %s AND id <= (SELECT id FROM attendees WHERE queue_id = %s AND first_name = %s AND last_name = %s)",
                (queue_id, queue_id, session['first_name'], session['last_name']))
    position = cur.fetchone()[0]
    
    # Close connection
    cur.close()
    
    return render_template('queue_status.html', queue_name=queue_name, position=position)


# Logout
@app.route('/join_details')
def join_details():
    return render_template('join_details.html')  
