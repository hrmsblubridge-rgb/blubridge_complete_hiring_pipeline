"""Read-only snapshot of AI calling collections (counts + provider settings hash)."""
import hashlib
import json
from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017")["hiring_ai_testing"]
out = {c: db[c].count_documents({}) for c in ("ai_calls", "ai_call_jobs", "ai_test_candidates", "ai_candidate_consents",
                                             "bb_registrations", "pipeline_data", "ai_call_audit")}
s = db.ai_call_settings.find_one({}) or {}
out["emergency_stop"] = s.get("emergency_stop")
out["ai_test_enabled"] = s.get("ai_test_enabled")
out["ai_live_enabled"] = s.get("ai_live_enabled")
out["live_daily_call_limit"] = s.get("live_daily_call_limit")
out["live_max_concurrent_calls"] = s.get("live_max_concurrent_calls")
out["mode_version"] = s.get("mode_version")
prov = db.ai_provider_settings.find_one({}) if "ai_provider_settings" in db.list_collection_names() else None
out["provider_hash"] = hashlib.sha256(json.dumps(prov, default=str, sort_keys=True).encode()).hexdigest()[:16] if prov else None
print(json.dumps(out))
