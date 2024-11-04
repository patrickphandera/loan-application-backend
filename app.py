from flask import Flask, request, jsonify
from joblib import load
import pandas as pd
import traceback
import os
from flask_pymongo import PyMongo
from flask_cors import CORS 
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
from bson.objectid import ObjectId

app = Flask(__name__)

# Use environment variables for sensitive information
MONGO_URI = os.getenv('MONGO_URI')
app.config["MONGO_URI"] = MONGO_URI
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')
mongo = PyMongo(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
CORS(app)

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

# Register User
@app.route('/register', methods=['POST'])
def register():
    fullname = request.json.get('fullname')
    email = request.json.get('email')
    phone = request.json.get('phone')
    password = request.json.get('password')
    role = request.json.get('role')

    if mongo.db.users.find_one({"email": email}):
        return jsonify({"msg": "User already exists!"}), 400

    hashed_password = generate_password_hash(password)
    mongo.db.users.insert_one({
        "fullname": fullname,
        "email": email,
        "phone": phone,
        "password": hashed_password,
        "role": role
    })
           
    return jsonify({"msg": "User registered successfully!"}), 201

# Get All Users
@app.route('/users', methods=['GET'])
def get_users():
    users = mongo.db.users.find()
    user_list = []
    for user in users:
        user['_id'] = str(user['_id'])  # Convert ObjectId to string for JSON
        user.pop('password', None)  # Remove password for security
        user_list.append(user)
    return jsonify(user_list), 200

# Read User
@app.route('/user/<user_id>', methods=['GET'])
def get_user(user_id):
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if user:
        user['_id'] = str(user['_id'])
        return jsonify(user), 200
    return jsonify({"msg": "User not found"}), 404

# Update User
@app.route('/user/<user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.json
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"msg": "User not found"}), 404

    mongo.db.users.update_one({"_id": ObjectId(user_id)}, {"$set": data})
    return jsonify({"msg": "User updated successfully"}), 200

# Delete User
@app.route('/user/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    result = mongo.db.users.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count:
        return jsonify({"msg": "User deleted successfully"}), 200
    return jsonify({"msg": "User not found"}), 404

@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username')
    password = request.json.get('password')

    user = mongo.db.users.find_one({"email": username})
    if user and check_password_hash(user['password'], password):
        # Create JWT token
        token = jwt.encode({
            'user': username,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }, app.secret_key, algorithm='HS256')
        user_id=str(user['_id'])
        return jsonify(access_token=token, role=user['role'],user=str(user['_id'])), 200
    else:
        return jsonify({"msg": "Invalid username or password!"}), 401

@app.route('/predict', methods=['POST'])
def predict():
    try:
        if not request.is_json:
            return jsonify({'error': 'Request must be in JSON format.'}), 400

        data = request.get_json()
        required_fields = ['gender', 'age', 'dependents', 'income', 'loanamount', 'collateral', 'term', 'rate', 'loantype']
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

        df = pd.DataFrame([[gender, age, dependents, income, loanamount, collateral, term, rate, loantype]],
                          columns=['Gender', 'Age', 'Dependents', 'Income', 
                                   'LoanAmount', 'Collateral', 'Term', 'Rate', 'LoanType'])

        df[NUMERICAL_COLUMNS] = scaler.transform(df[NUMERICAL_COLUMNS])
        prediction = loaded_model.predict(df)[0]
        result = outcome[prediction]

        return jsonify({'prediction': result})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f"An error occurred during prediction: {str(e)}"}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part', 400
    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400

    if file and file.filename.endswith('.csv'):
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(file_path)
        return 'File successfully uploaded', 200
    else:
        return 'Invalid file type. Only CSV files are allowed.', 400

@app.route('/process', methods=['POST'])
def process_file():
    data = request.get_json()
    filetype = data.get('filetype')
    filename = data.get('filename')

    if filetype == 'csv':
        try:
            df = pd.read_csv(f'uploads/{filename}')
            columns = ['gender', 'age', 'dependents', 'income', 'loanamount', 'term', 'collateral', 'rate', 'loantype']

            for col in columns:
                if not contains_only_numbers(df[col]):
                    return f'Data validation failed, {col} column is not clean'

            return 'Data successfully validated'
        
        except FileNotFoundError:
            return jsonify({"error": "File not found. Please check the filename."}), 404
        except KeyError as e:
            return jsonify({"error": f"Missing column in the CSV file: {str(e)}"}), 400
        except Exception as e:
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    
    return jsonify({"error": "Invalid filetype. Only 'csv' is supported."}), 400

@app.route('/predict_many', methods=['POST'])
def predict_many():
    columns = ['Gender', 'Age', 'Dependents', 'Income', 'LoanAmount', 'Collateral', 'Term', 'Rate', 'LoanType']
    
    df1 = pd.DataFrame(columns=columns + ['Result'])
    data = request.get_json()
    filetype = data.get('filetype')
    filename = data.get('filename')

    if filetype == 'csv':
        try:
            df = pd.read_csv(f'uploads/{filename}')
            df.columns = df.columns.str.lower()

            missing_cols = set(col.lower() for col in columns) - set(df.columns)
            if missing_cols:
                return jsonify({"error": f"Missing columns in the CSV file: {list(missing_cols)}"}), 400

            for index, row in df.iterrows():
                input_data = row[['gender', 'age', 'dependents', 'income', 'loanamount', 'collateral', 'term', 'rate', 'loantype']].values
                input_df = pd.DataFrame([input_data], columns=columns[:-1])
                input_df[NUMERICAL_COLUMNS] = scaler.transform(input_df[NUMERICAL_COLUMNS])
                prediction = loaded_model.predict(input_df)[0]
                df1 = df1.append({'Gender': row['gender'], 'Age': row['age'], 'Dependents': row['dependents'], 'Income': row['income'], 
                                  'LoanAmount': row['loanamount'], 'Collateral': row['collateral'], 'Term': row['term'], 
                                  'Rate': row['rate'], 'LoanType': row['loantype'], 'Result': outcome[prediction]}, 
                                  ignore_index=True)

            return jsonify(df1.to_dict(orient='records')), 200

        except Exception as e:
            traceback.print_exc()
            return jsonify({'error': f"An error occurred during prediction: {str(e)}"}), 500
