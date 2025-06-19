import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

def initialize_firestore():
    """
    Initializes the Firebase Admin SDK and returns a Firestore client instance.
    
    Returns:
        firestore.Client: An instance of the Firestore client, or None if initialization fails.
    """
    try:
        # Replace "path/to/your/serviceAccountKey.json" with the path to your service account key file.
        cred = credentials.Certificate("/Users/zhaosongzhu/Downloads/financial-app-d3ac9-firebase-adminsdk-fbsvc-2394db1dd3.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Successfully connected to Firestore!")
        return db
    except Exception as e:
        print(f"Error initializing Firestore: {e}")
        return None

def fetch_collection_data(db, collection_name):
    """
    Fetches all documents from a specified collection.

    Args:
        db (firestore.Client): The Firestore client instance.
        collection_name (str): The name of the collection to fetch data from.
    
    Returns:
        list: A list of dictionaries, where each dictionary represents a document.
              Returns an empty list if the collection is not found or an error occurs.
    """
    if not db:
        print("Firestore client is not initialized. Cannot fetch data.")
        return []

    try:
        docs_stream = db.collection(collection_name).stream()
        documents = []
        for doc in docs_stream:
            doc_data = doc.to_dict()
            doc_data['id'] = doc.id # Optionally include the document ID
            documents.append(doc_data)
        
        if not documents:
            print(f"No documents found in collection '{collection_name}' or collection does not exist.")
        return documents
    except Exception as e:
        print(f"Error fetching collection '{collection_name}': {e}")
        return []

def main():
    """
    Main function to initialize Firestore and fetch collection data.
    """
    db = initialize_firestore()

    if db:
        # Replace "your-collection-name" with the actual name of your collection.
        collection_name = "users" 
        print(f"\nFetching data from collection: '{collection_name}'...")
        
        data = fetch_collection_data(db, collection_name)
        
        if data:
            print(f"\n--- Data from '{collection_name}' ---")
            for item in data:
                print(item)
            print("--- End of data ---")
        else:
            print(f"Could not retrieve data from '{collection_name}'.")

if __name__ == "__main__":
    main()
