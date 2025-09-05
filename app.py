import mysql.connector 
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime
from fpdf import FPDF
from io import BytesIO


app = Flask(__name__)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:Comp7742@localhost/finance_tracker'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    wallet_balance = db.Column(db.Float, default=0.0)

# Transaction Model
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    payment_mode = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text, nullable=True)
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",  
        password="Comp7742",  
        database="finance_tracker"  
    )


@app.route('/')
def home():
    return render_template('homepage.html')

@app.route('/loginpage')
def login_page():
    return render_template('login.html')

@app.route('/homepage')
def home_page():
    return render_template('homepage.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password, password):
        session['user_id'] = user.id
        flash('Login successful!', 'success')
        return redirect(url_for('dashboard'))
    flash('Invalid credentials, please try again.', 'danger')
    return redirect(url_for('login_page'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, name=name, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login_page'))
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    user = User.query.get(session['user_id'])
    transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.date.desc()).limit(5).all()
    total_expense = sum(txn.amount for txn in transactions)
    category_totals = {}
    for txn in transactions:
        category_totals[txn.category] = category_totals.get(txn.category, 0) + txn.amount

    return render_template(
        'dashboard.html',
        user=user,
        transactions=transactions,
        category_totals=category_totals,
        total_expense=total_expense,
        wallet_balance=user.wallet_balance  # ✅ This is new
    )

@app.route('/update_wallet', methods=['POST'])
def update_wallet():
    action = request.form.get('action')
    amount_str = request.form.get('amount')

    if not amount_str:
        flash("Amount cannot be empty", "danger")
        return redirect(url_for('dashboard'))

    try:
        amount = float(amount_str)
    except ValueError:
        flash("Invalid amount entered", "danger")
        return redirect(url_for('dashboard'))

    user_id = session.get('user_id')

    
    conn = get_db_connection()
    cursor = conn.cursor()

    if action == 'edit':
        cursor.execute("UPDATE user SET wallet_balance = %s WHERE id = %s", (amount, user_id))
    elif action == 'add':
        cursor.execute("SELECT wallet_balance FROM user WHERE id = %s", (user_id,))
        current_balance = cursor.fetchone()[0] or 0
        new_balance = current_balance + amount
        cursor.execute("UPDATE user SET wallet_balance = %s WHERE id = %s", (new_balance, user_id))

    else:
        flash("Unknown action", "warning")
        return redirect(url_for('dashboard'))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Wallet updated successfully!", "success")
    return redirect(url_for('dashboard'))



@app.route('/index')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    
    user = User.query.get(session['user_id'])
    wallet_balance = user.wallet_balance  # Get the wallet balance from the User model
    return render_template('index.html', user=user, wallet_balance=wallet_balance)

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user = User.query.get(session['user_id'])
    filter_value = request.args.get("filter")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = Transaction.query.filter_by(user_id=user.id)

    # Handle filter by category or payment_mode
    if filter_value:
        try:
            filter_type, value = filter_value.split(":")
            if filter_type == "category":
                query = query.filter_by(category=value)
            elif filter_type == "payment":
                query = query.filter_by(payment_mode=value)
            else:
                flash("Invalid filter type provided.", "warning")
        except ValueError:
            flash("Invalid filter format. Expected 'filter_type:value'.", "warning")

    # Handle date range filter
    if start_date and end_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(Transaction.date.between(s_date, e_date))
        except ValueError:
            flash("Invalid date format. Expected 'YYYY-MM-DD'.", "warning")

    # Fetch transactions and order by date descending
    transactions = query.order_by(Transaction.date.desc()).all()

    if not transactions:
        flash("No transactions found for the selected filters.", "info")

    return render_template('history.html', user=user, transactions=transactions)

@app.route('/add_transaction', methods=['GET', 'POST'])
def add_transaction():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_id = session['user_id']
    user = User.query.get(user_id)
    wallet_balance = user.wallet_balance if user.wallet_balance is not None else 0.0

    if request.method == 'POST':
        name = request.form['name']
        amount = float(request.form['amount'])
        category = request.form['category']
        date_value = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        time_value = datetime.strptime(request.form['time'], "%H:%M").time()
        payment_mode = request.form['payment_mode']
        note = request.form['note']

        # Create transaction
        new_transaction = Transaction(
            name=name, amount=amount, user_id=user_id,
            category=category, date=date_value, time=time_value,
            payment_mode=payment_mode, note=note
        )
        db.session.add(new_transaction)

        if wallet_balance >= amount:
            user.wallet_balance -= amount
            db.session.commit()
            flash('Transaction added successfully!', 'success')
            return redirect(url_for('history'))
        else:
            flash(f"Insufficient wallet balance! Your current balance is ₹{wallet_balance:.2f}.", "danger")
            return redirect(url_for('history'))

    # For GET request: render form with wallet balance
    return render_template('index.html', wallet_balance=wallet_balance)




@app.route('/visualization')
def visualization():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    user_id = session['user_id']
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    data = [
        {
            "category": t.category,
            "amount": t.amount,
            "date": t.date.strftime("%Y-%m-%d")
        }
        for t in transactions
    ]
    return render_template('visual.html', transactions=data)

@app.route('/api/transactions')
def get_transactions():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session['user_id']
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    data = [
        {
            "category": t.category,
            "amount": t.amount,
            "date": t.date.strftime("%Y-%m-%d")
        }
        for t in transactions
    ]
    return jsonify(data)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/export_transactions')
def export_transactions():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    user_id = session['user_id']
    filter_value = request.args.get("filter")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = Transaction.query.filter_by(user_id=user_id)

    if filter_value:
        try:
            filter_type, value = filter_value.split(":")
            if filter_type == "category":
                query = query.filter_by(category=value)
            elif filter_type == "payment":
                query = query.filter_by(payment_mode=value)
        except ValueError:
            pass

    if start_date and end_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(Transaction.date.between(s_date, e_date))
        except ValueError:
            pass

    transactions = query.all()
    export_data = "ID,Name,Amount,Category,Date,Time,Payment Mode,Note\n"
    total_amount = 0
    for t in transactions:
        export_data += f"{t.id},{t.name},{t.amount},{t.category},{t.date},{t.time},{t.payment_mode},{t.note or ''}\n"
        total_amount += t.amount

    # Fetch wallet balance
    user = User.query.get(user_id)
    wallet_balance = user.wallet_balance if user else 0


    # Add total and balance row
    export_data += f",,,Total,,,{total_amount},\n"
    export_data += f",,,Remaining Wallet Balance,,,{wallet_balance},\n"

    response = app.response_class(
        export_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"}
    )
    return response

@app.route('/export_transactions_pdf')
def export_transactions_pdf():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session['user_id']
    filter_value = request.args.get("filter")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = Transaction.query.filter_by(user_id=user_id)

    if filter_value:
        try:
            filter_type, value = filter_value.split(":")
            if filter_type == "category":
                query = query.filter_by(category=value)
            elif filter_type == "payment":
                query = query.filter_by(payment_mode=value)
        except ValueError:
            pass

    if start_date and end_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(Transaction.date.between(s_date, e_date))
        except ValueError:
            pass

    transactions = query.all()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(200, 10, txt="Transaction Report", ln=True, align='C')
    pdf.ln(10)

    # Header row
    pdf.set_font("Arial", 'B', 10)
    headers = ['ID', 'Name', 'Amount', 'Category', 'Date', 'Time', 'Mode', 'Note']
    col_widths = [10, 30, 20, 30, 25, 20, 25, 30]

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, border=1)
    pdf.ln()

    # Fetch wallet balance
    user = User.query.get(user_id)
    wallet_balance = user.wallet_balance if user else 0


    # Data rows
    pdf.set_font("Arial", '', 9)
    total_amount = 0
    for t in transactions:
        total_amount += t.amount
        row = [
            str(t.id),
            t.name[:15],
            f"{t.amount:.2f}",
            t.category[:15],
            t.date.strftime('%Y-%m-%d'),
            t.time.strftime('%H:%M'),
            t.payment_mode[:10],
            (t.note[:20] + '...') if t.note and len(t.note) > 20 else (t.note or '')
        ]
        for i, item in enumerate(row):
            pdf.cell(col_widths[i], 8, item, border=1)
        pdf.ln()

    # Add the "Total" row
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(col_widths[0] + col_widths[1], 8, "Total", border=1, align='C')  # Merge first two cells
    pdf.cell(col_widths[2], 8, f"{total_amount:.2f}", border=1, align='C')    # Total amount cell
    for w in col_widths[3:]:
        pdf.cell(w, 8, "", border=1)  # Fill remaining columns for alignment
    pdf.ln()

    # Add the "Remaining Wallet Balance" row (spanning multiple cells)
    cell_height = 16  # Increased height to fit the text
    pdf.cell(col_widths[0] + col_widths[1] + col_widths[2], cell_height, "Remaining Wallet Balance", border=1, align='C')  # Merge cells for the label
    pdf.cell(col_widths[3] + col_widths[4] + col_widths[5] + col_widths[6] + col_widths[7], cell_height, f"{wallet_balance:.2f}", border=1, align='C')  # Wallet balance amount
   

    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    return send_file(BytesIO(pdf_bytes), download_name="transactions.pdf", as_attachment=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
