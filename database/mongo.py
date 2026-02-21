from pymongo import MongoClient
from datetime import datetime

# ==========================
# MONGO CLIENT & DATABASE
# ==========================
client = MongoClient("mongodb://localhost:27017/")
db = client["world_pulse"]

# ==========================
# GENERIC INSERT FUNCTION
# ==========================
def insert(collection_name, data, unique_keys=None):
    """
    Insert data into MongoDB with duplicate checks.
    :param collection_name: Name of the collection
    :param data: List or dict of documents
    :param unique_keys: List of keys to check duplicates (e.g., ['data.title', 'data.query'])
    """
    if not data:
        return 0

    if isinstance(data, dict):
        data = [data]

    inserted_count = 0

    for d in data:
        d["collected_at"] = datetime.utcnow()

        # Build query for uniqueness
        query = {}
        if unique_keys:
            for key in unique_keys:
                val = d
                for k in key.split('.'):
                    val = val.get(k, None)
                    if val is None:
                        break
                if val is not None:
                    query[key] = val

        # Check if document exists
        if query and db[collection_name].count_documents(query) > 0:
            continue

        db[collection_name].insert_one(d)
        inserted_count += 1

    return inserted_count

# ==========================
# RUN METADATA
# ==========================
def insert_run_metadata(run_name, summary):
    """
    Store metadata for each orchestration run.
    Example summary: {"news": 5, "gdelt": 3, "errors": {"news": "timeout"}}
    """
    metadata_doc = {
        "run_name": run_name,
        "summary": summary,
        "run_at": datetime.utcnow()
    }
    db["run_metadata"].insert_one(metadata_doc)

# ==========================
# FEATURE STORE — GLOBAL FEATURES (Legacy)
# ==========================
def write_global_features(features_dict, version=1):
    """
    Store global features in MongoDB.
    """
    document = {
        "timestamp": datetime.utcnow(),
        "version": version,
        "features": features_dict
    }
    db["global_features"].insert_one(document)

def write_country_features(country, features_dict, version=1):
    """
    Store country-level features in MongoDB.
    """
    document = {
        "timestamp": datetime.utcnow(),
        "country": country,
        "version": version,
        "features": features_dict
    }
    db["country_features"].insert_one(document)

# ==========================
# VERSIONED FEATURE STORE — ONLINE/OFFLINE SPLIT
# ==========================
def write_global_features_v2(features, mode="online"):
    """
    Insert a versioned global feature document into MongoDB.
    Supports mode: 'online' (real-time) or 'offline' (training).
    Automatically increments the version based on the last document in that mode.
    """
    last_doc = list(db.global_features.find({"mode": mode}).sort("timestamp", -1).limit(1))
    
    if last_doc and "version" in last_doc[0]:
        version = last_doc[0]["version"] + 1
    else:
        version = 1  # fallback if no previous version exists

    doc = {
        "timestamp": datetime.utcnow(),
        "version": version,
        "mode": mode,
        "features": features
    }
    db.global_features.insert_one(doc)


def write_country_features_v2(country, features, mode="online"):
    """
    Insert a versioned country feature document into MongoDB.
    Supports mode: 'online' (real-time) or 'offline' (training).
    Automatically increments the version based on the last document for that country and mode.
    """
    last_doc = list(db.country_features.find({"country": country, "mode": mode}).sort("timestamp", -1).limit(1))
    
    if last_doc and "version" in last_doc[0]:
        version = last_doc[0]["version"] + 1
    else:
        version = 1  # fallback if no previous version exists

    doc = {
        "timestamp": datetime.utcnow(),
        "version": version,
        "country": country,
        "mode": mode,
        "features": features
    }
    db.country_features.insert_one(doc)


# ==========================
# RETRIEVE FEATURES
# ==========================
def get_latest_global_features(mode="online"):
    """
    Return the latest global features document by mode.
    """
    # Use _id ordering to avoid mixed-type timestamp sort issues (str vs datetime).
    return db["global_features"].find_one({"mode": mode}, sort=[("_id", -1)])

def get_historical_global_features(limit=1000, mode="online"):
    """
    Return the last 'limit' global features documents by mode.
    """
    cursor = db["global_features"].find({"mode": mode}).sort("_id", -1).limit(limit)
    return list(cursor)
