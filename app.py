from flask import Flask, request, jsonify
import openai
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
# from flask_pymongo import PyMongo
from flask_cors import CORS
from pymongo import MongoClient
from config import Config

from bson import ObjectId

# Initialize Flask app and configurations
app = Flask(__name__)

app.config.from_object(Config)

# Initialize extensions
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
# mongo = PyMongo(app)
# from database import mongo  # Import your separate PyMongo instance
client = MongoClient(app.config['MONGO_URI'])
# mongo = mongo_client.get_database()

db = client['umunthuai']
users_collection=db['users']
# Set up OpenAI API key
openai.api_key = app.config["OPENAI_API_KEY"]
MODEL = app.config["MODEL"]
blacklist = set() 
system_context = 'you are a helpful assistant that answers question from user from chichewa constitution of malawi in the form Chapter:<constitution_chapter>,Section:<costitution_section>, <answer_from_chichewa_constititution>'
CORS(app)
# Helper function to convert MongoDB documents to JSON-compatible dicts
def user_to_json(user):
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "phone": user["phone"],
        "age": user["age"],
        "district": user["district"]
    }

def query_model(query):
    try:
        
        response = openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_context},
                {"role": "user", "content": query },
            ],
            temperature=0,
        )
        generated_text = response.choices[0].message.content
        return generated_text
    except Exception as e:
        return f"Error during API call: {str(e)}"

def is_token_valid(token):
    return token not in blacklist

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    phone = data.get('phone')
    password = data.get('password')
    age = data.get('age')
    district = data.get('district')

    if not (username and phone and password and age and district):
        return jsonify({"error": "All fields are required"}), 400

    if users_collection.find_one({"$or": [{"username": username}, {"phone": phone}]}):
        return jsonify({"error": "User already exists"}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = {
        "username": username,
        "phone": phone,
        "password": hashed_password,
        "age": age,
        "district": district
    }
    user_id = users_collection.insert_one(new_user).inserted_id

    return  "User registered successfully", 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    print(data)
    phone = data.get('phone')
    password = data.get('password')

    user = users_collection.find_one({"phone": phone})
    if user and bcrypt.check_password_hash(user['password'], password):
        access_token = create_access_token(identity=str(user["_id"]),expires_delta=timedelta(hours=4))
        return jsonify({"access_token": access_token}), 200
    else:
        return jsonify({"error": "Invalid phone or password"}), 401

@app.route('/profile', methods=['GET'])
@jwt_required()
def profile():
    user_id = get_jwt_identity()
    
    # Check if token is valid
    if not is_token_valid(request.headers.get('Authorization').split(" ")[1]):
        return jsonify({"error": "You dont have required permissions, please login "}), 401

    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if user:
        return jsonify(user_to_json(user)), 200
    return jsonify({"error": "User not found"}), 404

@app.route('/update', methods=['PUT'])
@jwt_required()
def update_user():
    user_id = get_jwt_identity()
    data = request.get_json()
    
    # Check if token is valid
    if not is_token_valid(request.headers.get('Authorization').split(" ")[1]):
        return jsonify({"error": "You dont have required permissions, please login "}), 401

    user = users_collection.find_one({"_id": ObjectId(user_id)})

    if not user:
        return jsonify({"error": "User not found"}), 404

    updated_data = {}
    if "username" in data:
        updated_data["username"] = data["username"]
    if "phone" in data:
        updated_data["phone"] = data["phone"]
    if "age" in data:
        updated_data["age"] = data["age"]
    if "district" in data:
        updated_data["district"] = data["district"]
    if "password" in data:
        updated_data["password"] = bcrypt.generate_password_hash(data["password"]).decode('utf-8')

    users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": updated_data})
    return "User updated successfully", 200

@app.route('/delete', methods=['DELETE'])
@jwt_required()
def delete_user():
    user_id = get_jwt_identity()
    
    # Check if token is valid
    if not is_token_valid(request.headers.get('Authorization').split(" ")[1]):
        return jsonify({"error": "You dont have required permissions, please login "}), 401

    result = users_collection.delete_one({"_id": ObjectId(user_id)})

    if result.deleted_count == 1:
        return 'User deleted successfully', 200
    else:
        return jsonify({"error": "User not found"}), 404

# @app.route('/chat', methods=['POST'])
# def chat():
#     # Extract message from form data
#     data = request.get_json()
#     user_message =data['message']
#     if not is_token_valid(request.headers.get('Authorization').split(" ")[1]):
#         return jsonify({"error": "You dont have required permissions, please login "}), 401
    
#     if not user_message:
#         return jsonify({"error": "No message provided"}), 400

#     # Use OpenAI API to get a response from GPT-3.5 or GPT-4
#     try:
#         user_response = query_model(user_message)
#         return user_response
    
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
   
   
 # Create Chat Message
try:
    # Ping the server
    client.admin.command('ping')
    print("MongoDB is reachable!")
except ConnectionError:
    print("MongoDB is not reachable!")
except Exception as e:
    print(f"An error occurred: {e}")
finally:
    client.close()
      

@app.route('/chat', methods=['POST'])
@jwt_required()
def create_chat():
    data = request.get_json()
    user_message = data.get('message')
    
    if not is_token_valid(request.headers.get('Authorization').split(" ")[1]):
        return jsonify({"error": "Unauthorized access, please login"}), 401

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    try:
        user_response = query_model(user_message)
        chat_data = {
            "user_id": get_jwt_identity(),
            "message": user_message,
            "response": user_response
        }
        result=users_collection.insert_one(chat_data)
        chat_data["_id"] = str(result.inserted_id)
        return jsonify(chat_data), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    
    
# Read Chat Messages
@app.route('/chat', methods=['GET'])
@jwt_required()
def get_chats():
    user_id = get_jwt_identity()
    
    if not is_token_valid(request.headers.get('Authorization').split(" ")[1]):
        return jsonify({"error": "Unauthorized access, please login"}), 401

    chats = users_collection.find({"user_id": user_id})
    chat_list = [{"id": str(chat["_id"]), "message": chat["message"], "response": chat["response"]} for chat in chats]
    return jsonify(chat_list), 200  
    
    
     # Update Chat Message
@app.route('/chat/<chat_id>', methods=['PUT'])
@jwt_required()
def update_chat(chat_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    updated_message = data.get('message')

    if not is_token_valid(request.headers.get('Authorization').split(" ")[1]):
        return jsonify({"error": "Unauthorized access, please login"}), 401

    if not updated_message:
        return jsonify({"error": "No message provided"}), 400

    result = users_collection.update_one(
        {"_id": ObjectId(chat_id), "user_id": user_id},
        {"$set": {"message": updated_message}}
    )

    if result.matched_count == 1:
        return jsonify({"message": "Chat message updated successfully"}), 200
    else:
        return jsonify({"error": "Chat message not found"}), 404
    
    
# Delete Chat Message
@app.route('/chat/<chat_id>', methods=['DELETE'])
@jwt_required()
def delete_chat(chat_id):
    user_id = get_jwt_identity()

    if not is_token_valid(request.headers.get('Authorization').split(" ")[1]):
        return jsonify({"error": "Unauthorized access, please login"}), 401

    result = users_collection.delete_one({"_id": ObjectId(chat_id), "user_id": user_id})
    if result.deleted_count == 1:
        return jsonify({"message": "Chat message deleted successfully"}), 200
    else:
        return jsonify({"error": "Chat message not found"}), 404  
    
    
     
@app.route('/logout', methods=['POST'])
def logout():
    print(request.headers.get('Authorization'))
    token = request.headers.get('Authorization').split(" ")[1]  # Extract token from Authorization header
    blacklist.add(token)  # Add token to blacklist
    return "Successfully logged out", 200

if __name__=='__main__':
    app.run(debug=True)