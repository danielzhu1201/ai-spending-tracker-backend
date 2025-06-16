from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory "database" for users
users = []
user_id_counter = 1

@app.route('/')
def hello_world():
    return 'Hello, World!'

# Create a new user
@app.route('/users', methods=['POST'])
def create_user():
    global user_id_counter
    data = request.get_json()
    if not data or not 'name' in data or not 'email' in data:
        return jsonify({'error': 'Missing name or email'}), 400
    
    new_user = {
        'id': user_id_counter,
        'name': data['name'],
        'email': data['email']
    }
    users.append(new_user)
    user_id_counter += 1
    return jsonify(new_user), 201

# Get all users
@app.route('/users', methods=['GET'])
def get_users():
    return jsonify(users), 200

# Get a specific user by ID
@app.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = next((user for user in users if user['id'] == user_id), None)
    if user:
        return jsonify(user), 200
    return jsonify({'error': 'User not found'}), 404

# Update an existing user
@app.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.get_json()
    user = next((user for user in users if user['id'] == user_id), None)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if 'name' in data:
        user['name'] = data['name']
    if 'email' in data:
        user['email'] = data['email']
    
    return jsonify(user), 200

# Delete a user
@app.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    global users
    user = next((user for user in users if user['id'] == user_id), None)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    users = [u for u in users if u['id'] != user_id]
    return '', 204

if __name__ == '__main__':
    app.run(debug=True)
