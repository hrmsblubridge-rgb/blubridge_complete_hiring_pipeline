"""Read-only snapshot of AI calling state + collection counts (hiring_ai_testing). Usage: python snapshot_ai_state.py out.json"""
import json
import sys

from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017")["hiring_ai_testing"]
prov = db.ai_provider_settings.find_one({}) or {}
keys = ["config_version", "api_key_last4", "status", "agent_id", "caller_number", "webhook_token_hash",
        "api_key_encrypted", "updated_at", "verified_at"]
out = {
    "provider": {k: prov.get(k) for k in keys},
    "provider_all_keys": sorted(prov.keys()),
    "provider_full_repr_hash": __import__("hashlib").sha256(json.dumps(prov, sort_keys=True, default=str).encode()).hexdigest(),
    "counts": {c: db[c].count_documents({}) for c in sorted(db.list_collection_names())},
    "settings": {k: v for k, v in (db.ai_call_settings.find_one({"_id": "global"}) or {}).items() if k in ("mode", "emergency_stop", "mode_version")},
    "webhook_events": [{k: v for k, v in e.items() if k != "_id"} for e in db.ai_webhook_events.find({})],
}
json.dump(out, open(sys.argv[1], "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
