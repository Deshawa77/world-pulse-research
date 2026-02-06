from pymongo import MongoClient, ASCENDING
from datetime import datetime

client = MongoClient("mongodb://localhost:27017/")
db = client["world_pulse"]

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

        
        if query and db[collection_name].find_one(query):
            continue
        db[collection_name].insert_one(d)
        inserted_count += 1

    return inserted_count


def insert_run_metadata(run_name, summary):
    """
    Store metadata for each orchestration run.
    Example summary: {"news": 5, "gdelt": 3, "errors": {"news": "timeout"}}
    """
    metadata = {
        "run_name": run_name,
        "summary": summary,
        "run_at": datetime.utcnow()
    }
    db["run_metadata"].insert_one(metadata)
