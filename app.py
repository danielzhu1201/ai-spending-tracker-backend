import base64
import io
import os
from datetime import datetime, time, timedelta
from flask import Flask, g, request, jsonify
from flask_cors import CORS
import firebase_admin
from firebase_admin import auth, credentials, firestore
from google import genai
from PIL import Image

app = Flask(__name__)
CORS(app)

SPENDING_CATEGORIES = [
    "Food & Dining", "Shopping", "Transportation", "Health & Fitness",
    "Entertainment", "Utilities", "Travel", "Other"
]

# --- Google Services Init ---

try:
    FIREBASE_CONFIG_DIR = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    cred = credentials.Certificate(FIREBASE_CONFIG_DIR)
    firebase_admin.initialize_app(cred)
    
    # Initialize Firestore DB
    db = firestore.client()
    print("Successfully connected to Firestore!")

    # Initialize Gemini AI model
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    
    model = genai.Client()
    print("Successfully initialized Gemini AI model (gemini-1.5-flash-latest)!")

except Exception as e:
    print(f"Error during initialization: {e}")
    db = None
    model = None

# --- Authentication Middleware ---

@app.before_request
def verify_token():
    # Skip token verification for the healthcheck endpoint
    if request.path == '/healthcheck':
        return

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({"error": "Authorization header with Bearer token is required"}), 401

    id_token = auth_header.split('Bearer ')[1]
    try:
        g.user = auth.verify_id_token(id_token)
    except (auth.InvalidIdTokenError, ValueError) as e:
        return jsonify({"error": f"Invalid or expired token: {e}"}), 401

# --- API Endpoints ---

@app.route('/healthcheck')
def healthcheck():
    """
    Performs a health check on the server.
    Checks if Firestore and Gemini AI clients are initialized.
    """
    if db and model:
        return "Flask server is running. Firestore and Gemini AI integration are active."
    else:
        return jsonify({"error": "Firestore or Gemini AI integration is not active."}), 500

@app.route('/users', methods=['GET'])
def get_users():
    """
    Fetches all documents from the 'users' collection in Firestore.
    """
    if not db:
        return jsonify({"error": "Firestore is not initialized."}), 500

    try:
        users_ref = db.collection('users')
        docs_stream = users_ref.stream()
        
        documents = []
        for doc in docs_stream:
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id
            documents.append(doc_data)
        
        if not documents:
            return jsonify({"message": "No documents found in collection 'users' or collection does not exist."}), 404
            
        return jsonify(documents), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/users', methods=['POST'])
def create_user():
    """
    Creates a new user in the 'users' collection.
    Expects 'email' and 'displayName' in the JSON body.
    The 'createdAt' field is automatically added with the server timestamp.
    """
    if not db:
        return jsonify({"error": "Firestore is not initialized."}), 500

    try:
        data = request.get_json()
        if not data or 'email' not in data or 'displayName' not in data:
            return jsonify({"error": "Missing required fields: email and displayName"}), 400

        user_data = {
            'email': data['email'],
            'displayName': data['displayName'],
            'createdAt': firestore.SERVER_TIMESTAMP
        }

        # Add a new doc with a generated ID and return its ID
        update_time, doc_ref = db.collection('users').add(user_data)
        return jsonify({"message": "User created successfully", "id": doc_ref.id}), 201
    except Exception as e:
        return jsonify({"error": f"An error occurred while creating user: {e}"}), 500

@app.route('/transactions', methods=['GET'])
def get_transactions():
    """
    Fetches all transactions for the authenticated user from Firestore.
    """
    if not db:
        return jsonify({"error": "Firestore is not initialized."}), 500

    try:
        user_id = g.user['uid']

        # Query for transactions belonging to the user
        trans_ref = db.collection('transactions').where('userId', '==', user_id)
        docs_stream = trans_ref.stream()

        documents = []
        for doc in docs_stream:
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id
            documents.append(doc_data)

        if not documents:
            return jsonify({"message": f"No transactions found for user {user_id}."}), 404

        return jsonify(documents), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/summary/spending', methods=['GET'])
def get_spending_summary():
    """
    Calculates spending summary by category for the authenticated user
    for a specified period (daily, weekly, monthly).
    """
    if not db:
        return jsonify({"error": "Firestore is not initialized."}), 500

    try:
        user_id = g.user['uid']
        period = request.args.get('period', 'monthly').lower()

        if period not in ['daily', 'weekly', 'monthly']:
            return jsonify({"error": "Invalid period. Supported values are 'daily', 'weekly', 'monthly'."}), 400

        now = datetime.now()
        if period == 'daily':
            start_date = datetime.combine(now.date(), time.min)
        elif period == 'weekly':
            start_of_week = now.date() - timedelta(days=now.weekday())
            start_date = datetime.combine(start_of_week, time.min)
        else:  # monthly
            start_of_month = now.date().replace(day=1)
            start_date = datetime.combine(start_of_month, time.min)

        # Query for transactions belonging to the user within the period
        trans_ref = db.collection('transactions')
        query = trans_ref.where('userId', '==', user_id).where('date', '>=', start_date)
        docs_stream = query.stream()

        spending_by_category = {}
        total_spent = 0
        for doc in docs_stream:
            transaction = doc.to_dict()
            category = transaction.get('category', 'Other')
            amount = transaction.get('amount', 0)

            if isinstance(amount, (int, float)):
                spending_by_category[category] = spending_by_category.get(category, 0) + amount
                total_spent += amount

        if not spending_by_category:
            return jsonify({"message": f"No transactions found for user {user_id} in the '{period}' period."}), 404

        # Sort categories by total spending in descending order
        sorted_summary = sorted(
            [{"category": k, "total_amount": v} for k, v in spending_by_category.items()],
            key=lambda x: x['total_amount'],
            reverse=True
        )

        result = {
            "period": period,
            "totalSpent": total_spent,
            "topCategories": sorted_summary
        }

        prompt = "Based on the spending summary, provide a concise analysis of the user's spending habits. Include insights on top spending categories and any notable trends." + str(result)
        
        response = model.models.generate_content(
            model="gemini-2.5-flash-lite-preview-06-17", contents=[prompt]
        )

        result['insights'] = response.text

        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred: {e}"}), 500

@app.route('/transactions', methods=['POST'])
def create_transaction():
    """
    Creates a new transaction for the authenticated user.
    Expects 'merchantName', 'amount', 'category', and 'date' in the JSON body.
    The 'userId' and 'createdAt' fields are automatically added. The 'date' should be in 'YYYY-MM-DD' format.
    """
    if not db:
        return jsonify({"error": "Firestore is not initialized."}), 500

    try:
        data = request.get_json()
        print(f"Received data for transaction creation: {data}")
        required_fields = ['amount', 'category', 'date', 'merchantName']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Convert date string (e.g., 'YYYY-MM-DD') to a datetime object for proper querying
        try:
            transaction_date = datetime.strptime(data['date'], '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Please use YYYY-MM-DD."}), 400

        user_id = g.user['uid']

        transaction_data = {
            'userId': user_id,
            'merchantName': data['merchantName'],
            'amount': data['amount'],
            'category': data['category'],
            'date': transaction_date,
            'createdAt': firestore.SERVER_TIMESTAMP
        }

        # Add a new doc with a generated ID and return its ID
        update_time, doc_ref = db.collection('transactions').add(transaction_data)
        return jsonify({"message": "Transaction created successfully", "id": doc_ref.id}), 201
    except Exception as e:
        return jsonify({"error": f"An error occurred while creating transaction: {e}"}), 500

@app.route('/receipt', methods=['POST'])
def receipt_scan():
    """
    Analyzes an image with a given prompt using the Gemini AI model.
    Expects a base64-encoded 'image_data' in the JSON body.
    """
    try:
        data = request.get_json()
        prompt = "Scan this receipt. Based on the entire receipt, provide me in JSON format the below information: date(yyyy-MM-dd), merchantName, category(only one category based on the merchant, must select from " + ", ".join(SPENDING_CATEGORIES) + "), amount(total amount in the receipt). If the receipt is not valid, return an empty JSON object. "
        image_data = data['image_data']
        try:
            image_data = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_data))
        except Exception as e:
            return jsonify({"error": f"Failed to process image data: {e}"}), 400
        
        response = model.models.generate_content(
            model="gemini-2.5-flash-lite-preview-06-17", contents=[prompt, image]
        )
        return jsonify({"response": response.text})
    except Exception as e:
        return jsonify({"error": f"An error occurred while generating content: {e}"}), 500


if __name__ == '__main__':
    app.run(debug=True)
