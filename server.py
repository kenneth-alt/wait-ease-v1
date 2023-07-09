import os
from dotenv import load_dotenv
from flask import Flask, render_template, url_for, redirect, flash, session, logging, request, g
import sqlite3
from flask_bootstrap import Bootstrap
from wtforms import Form, StringField, FileField, PasswordField, validators, EmailField
from wtforms.validators import DataRequired, EqualTo, Email, Length
from passlib.hash import sha256_crypt
from functools import wraps
import qrcode

load_dotenv()

app = Flask(__name__)
Bootstrap(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Config SQLite
app.config['DATABASE'] = 'db/queue_app.db'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db_path = os.path.join(os.getcwd(), app.config['DATABASE'])
        if not os.path.isfile(db_path):
            # Create the database file
            conn = sqlite3.connect(db_path)
            conn.close()
        db = g._database = sqlite3.connect(db_path)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# Init SQLite
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Check if the clients and queues tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='clients'")
        clients_table_exists = cursor.fetchone() is not None

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='queues'")
        queues_table_exists = cursor.fetchone() is not None

        # Create the clients table if it doesn't exist
        if not clients_table_exists:
            cursor.execute("""
                CREATE TABLE clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    password TEXT NOT NULL
                )
            """)

        # Create the queues table if it doesn't exist
        if not queues_table_exists:
            cursor.execute("""
                CREATE TABLE queues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    queue_name TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    created_by_client_id INTEGER NOT NULL,
                    FOREIGN KEY (created_by_client_id) REFERENCES clients (id)
                )
            """)

        db.commit()


init_db()

# Homepage
@app.route('/')
def homepage():
    return render_template('homepage.html')

# How it works
@app.route('/how_it_works')
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
        cur = get_db().cursor()
        
        # Execute querry
        cur.execute("INSERT INTO clients(business_name, email, phone_number, password) VALUES(%s, %s, %s, %s)", (business_name, email, phone_number, password))
        
        # Commit to DB
        get_db().commit()
    
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
        cur = get_db().cursor()
        
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
    cur = get_db().cursor()
    
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
            if request.method == 'POST' and 'delete_queue_id' in request.form:
                # Get the selected queue ID from the form data
                queue_id_to_delete = request.form['delete_queue_id']
                
                # Delete the queue
                cur.execute("DELETE FROM queues WHERE id = %s", (queue_id_to_delete,))

                # Delete the corresponding attendees table
                attendees_table_name = f"{selected_queue_name.replace(' ', '_')}_attendees"
                cur.execute(f"DROP TABLE IF EXISTS {attendees_table_name}")
                
                # Delete the QR code image for the queue
                qr_code_path = f"static/qr_codes/{selected_queue_id}_qr_code.png"
                if os.path.exists(qr_code_path):
                    os.remove(qr_code_path)

                # Commit to DB
                get_db().commit()
                
                flash('Queue Deleted Successfully!', 'success')
                
                return redirect(url_for('dashboard'))
            
            # Served Attendee
            if request.method == 'POST' and 'served_attendee_id' in request.form:
                served_attendee_id = request.form['served_attendee_id']

                # Delete the served attendee from the attendees table
                cur.execute(f"DELETE FROM {attendees_table_name} WHERE id = %s", (served_attendee_id,))

                # Commit to DB
                get_db().commit()

                flash('Attendee Served Successfully!', 'success')

                # Redirect back to the same queue
                return redirect(url_for('dashboard', queue_id=selected_queue_id, queue_name=selected_queue_name))

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
        cur = get_db().cursor()
        
        # Execute querry
        cur.execute("INSERT INTO queues(queue_name, purpose, instructions, created_by_client_id) VALUES(%s, %s, %s, %s)", (queue_name, purpose, instructions, session['id']))
        
        # Commit to DB
        get_db().commit()
        
        # Get the generated queue_id
        queue_id = cur.lastrowid
        
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
        get_db().commit()
        
        # Generate link for attendees to join the queue
        join_link = url_for('join_queue', queue_id=queue_id, _external=True)

        # Generate QR code
        qr = qrcode.QRCode()
        qr.add_data(join_link)
        qr.make(fit=True)
        qr_img = qr.make_image()

        # Save QR code image
        qr_img_path = f"static/qr_codes/{queue_id}_qr_code.png"
        qr_img.save(qr_img_path)
    
        # Close connection
        cur.close()
        
        flash('Queue Successfully Added!, You can manage your queue from your Dashboard.', 'success')
        
        return redirect(url_for('dashboard'))
 
    # Handle GET request (initial form display)
    return render_template('add_queue.html')


@app.route('/join_details/<int:queue_id>', methods=['GET'])
@is_logged_in
def join_details(queue_id):
    # Create cursor
    cur = get_db().cursor()

    # Get the queue details from the database
    cur.execute("SELECT * FROM queues WHERE id = %s", (queue_id,))
    queue_data = cur.fetchone()

    if queue_data:
        # Retrieve the queue details
        queue_name = queue_data['queue_name']
        purpose = queue_data['purpose']
        instructions = queue_data['instructions']

        # Retrieve the join URL and QR code image path based on the queue_id
        join_url = url_for('join_queue', queue_id=queue_id, _external=True)
        qr_code_path = f"qr_codes/{queue_id}_qr_code.png"

        # Close connection
        cur.close()

        return render_template('join_details.html', queue_id=queue_id, queue_name=queue_name, purpose=purpose, instructions=instructions, join_url=join_url, qr_code_path=qr_code_path)

    flash('Queue not found!', 'danger')
    return redirect(url_for('dashboard'))

# PUBLIC ROUTES ##########################################################################
# join Queue
@app.route('/join_queue/<int:queue_id>', methods=['GET', 'POST'])
def join_queue(queue_id):
    if request.method == 'POST':
        # Get attendee data from form fields
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        account_number = request.form['account_number']
        service_requested = request.form['service_requested']
        
        try: 
            # Create cursor
            cur = get_db().cursor()
            
            # Get the queue details from the database
            cur.execute("SELECT * FROM queues WHERE id = %s", (queue_id,))
            queue_data = cur.fetchone()
            
            if queue_data:
                # Retrieve the queue details
                queue_name = queue_data['queue_name']
        
                attendees_table_name = f"{queue_name.replace(' ', '_')}_attendees"
                
                 # Execute query to add attendee to attendees table
                insert_query = f"INSERT INTO {attendees_table_name} (first_name, last_name, account_number, service_requested, queue_id) VALUES (%s, %s, %s, %s, %s)"
                cur.execute(insert_query, (first_name, last_name, account_number, service_requested, queue_id))
            
                # Retrieve the attendee_id assigned to the attendee
                attendee_id = cur.lastrowid
                
                # Commit to DB
                get_db().commit()

        
                # Close connection
                cur.close()
            
                flash('You have successfully joined the queue!', 'success')
            
                # Redirect to the queue_status page with the queue_id and attendee_id as query parameters
                return redirect(url_for('queue_status', queue_id=queue_id, attendee_id=attendee_id))
            
        except Exception as e:
            flash(f'An error occurred while joining the queue. Please contact us on 080-OurBank for assistance.', 'danger')
            print(f"Database insert error: {e}")

    #Handle GET request (initial form display)
    return render_template('join_queue.html')


# Queue Status
@app.route('/queue_status/<int:queue_id>/<int:attendee_id>')
def queue_status(queue_id, attendee_id):
    position = None  # Default value for position
    try:
        # Create cursor
        cur = get_db().cursor()
        
        # Get the queue details from the database
        cur.execute("SELECT * FROM queues WHERE id = %s", (queue_id,))
        queue_data = cur.fetchone()
        
        if queue_data:
            # Retrieve the queue details
            queue_name = queue_data['queue_name']
            
            attendees_table_name = f"{queue_name.replace(' ', '_')}_attendees"
        
            cur.execute(f"SELECT COUNT(*) AS position FROM {attendees_table_name} WHERE id <= %s", (attendee_id,))
            position_data = cur.fetchone()
            position = position_data['position'] if position_data else None
            
            # Close connection
            cur.close()
        
            return render_template('queue_status.html', queue_name=queue_name, position=position, error=None)
    
    except Exception as e:
        error_message = f'An error occurred while fetching your queue status. Please contact us on 080-080-OurBank for assistance.'
        print(f"Database error: {e}")
        
        return render_template('queue_status.html', queue_name=None, position=None, first_name=None, error=error_message)
