from flask import Flask, request, jsonify
from joblib import load
import pandas as pd
import traceback
from flask_pymongo import PyMongo
from flask_cors import CORS 
import jwt
from werkzeug.security import generate_password_hash,check_password_hash
import datetime

app = Flask(__name__)
CORS(app)
MONGO_URI='mongodb+srv://userxyz:userxyz@cluster0.5be8y.mongodb.net/recommender?retryWrites=true&w=majority'
app.config["MONGO_URI"] = MONGO_URI # Change to your MongoDB URI
app.secret_key = 'your_secret_key'  # Change to a random secret key
mongo = PyMongo(app)


app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# Define possible outcomes
outcome = ['Eligible', 'Not eligible']

# Load the pre-trained model and scaler once when the server starts
try:
    loaded_model = load('random_forest_model.joblib')
    scaler = load('scaler.joblib')
    print("Model and scaler loaded successfully.")
except Exception as e:
    print(f"Error loading model or scaler: {e}")
    exit(1)

# Columns that need scaling
NUMERICAL_COLUMNS = ['Age', 'Income', 'LoanAmount', 'Collateral', 'Term', 'Rate']

@app.route('/')
def home():
    return "Welcome to the Loan Eligibility Prediction API!"

@app.route('/register', methods=['POST'])
def register():
    username = request.json.get('username')
    password = request.json.get('password')

    if mongo.db.users.find_one({"username": username}):
        return jsonify({"msg": "User already exists!"}), 400

    hashed_password = generate_password_hash(password)
    mongo.db.users.insert_one({"username": username, "password": hashed_password})

    return jsonify({"msg": "User registered successfully!"}), 201



@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username')
    password = request.json.get('password')

    user = mongo.db.users.find_one({"username": username})
    if user and check_password_hash(user['password'], password):
        # Create JWT token
        token = jwt.encode({
            'user': username,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # Token expires in 1 hour
        }, app.secret_key, algorithm='HS256')
        return jsonify(access_token=token), 200
    else:
        return jsonify({"msg": "Invalid username or password!"}), 401
    
@app.route('/logout', methods=['POST'])
def logout():
    # Normally, you would handle token revocation here, but we are not storing tokens.
    return jsonify({"msg": "Logout successful!"}), 200


@app.route('/predict', methods=['POST'])
def predict():
    try:
        # Ensure the request is in JSON format
        if not request.is_json:
            return jsonify({'error': 'Request must be in JSON format.'}), 400

        data = request.get_json()

        # Required fields
        required_fields = ['gender', 'age', 'dependents', 'income',
                           'loanamount', 'collateral', 'term', 'rate', 'loantype']

        # Check for missing fields
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({'error': f'Missing fields: {", ".join(missing_fields)}'}), 400

        # Extract and validate input data
        gender = data['gender']
        age = float(data['age'])
        dependents = int(data['dependents'])
        income = float(data['income'])
        loanamount = float(data['loanamount'])
        collateral = float(data['collateral'])
        term = float(data['term'])
        rate = float(data['rate'])
        loantype = data['loantype']

        # Create the DataFrame
        df = pd.DataFrame([[
            gender, age, dependents, income, loanamount, collateral, term, rate, loantype
        ]], columns=['Gender', 'Age', 'Dependents', 'Income', 
                    'LoanAmount', 'Collateral', 'Term', 'Rate', 'LoanType'])
        print(request)
        # Apply encoders if necessary
        # Example:
        # gender_encoder = load('gender_encoder.joblib')
        # loan_type_encoder = load('loan_type_encoder.joblib')
        # df['Gender'] = gender_encoder.transform(df['Gender'])
        # df['LoanType'] = loan_type_encoder.transform(df['LoanType'])

        # For demonstration, assuming gender and loan type are already encoded as integers
        # If they are categorical, you need to apply encoding here

        # Scale numerical features
        df[NUMERICAL_COLUMNS] = scaler.transform(df[NUMERICAL_COLUMNS])

        # Predict
        prediction = loaded_model.predict(df)[0]
        result = outcome[prediction]

        return jsonify({'prediction': result})

    except Exception as e:
        # For debugging purposes; in production, consider logging the error
        traceback.print_exc()
        return jsonify({'error': f"An error occurred during prediction: {str(e)}"}), 500

