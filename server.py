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


@app.route('/')
def index():
    return render_template('home.html')


@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

class RegistrationForm(Form):
    business_name = StringField('Business Name', validators=[DataRequired(), Length(min=1, max=100)])
    email = StringField('Email', validators=[DataRequired(), Length(min=1, max=100), Email()])
    phone_number = StringField('Phone Number', validators=[DataRequired(), Length(min=1, max=50)])
    password = PasswordField('Password', validators=[DataRequired(), EqualTo('confirm', message='Passwords do not match')])
    confirm = PasswordField('Confirm Password')

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
        
        return redirect(url_for('index'))
 
    # Handle GET request (initial form display)
    return render_template('register.html', form=form)


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
            business_name = data['business_name']
            password = data['password']
            
            # Compare passwords
            if sha256_crypt.verify(user_password, password):
                # Passed
                session['loggedin'] = True
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
        
   

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')