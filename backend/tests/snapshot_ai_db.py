"""Read-only snapshot of AI-calling safety state (no writes)."""
import hashlib
import json
import os
from pymongo import MongoClient

env = dict(line.strip().split("=", 1) for line in open("/app/backend/.env") if "=" in line and not line.startswith("#"))
c = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
s = c.ai_call_settings.find_one({}) or {}
prov = c.ai_provider_settings.find_one({"_id": "bolna"}) or {}
print("db", env["DB_NAME"])
print("ai_calls", c.ai_calls.count_documents({}), "ai_call_jobs", c.ai_call_jobs.count_documents({}))
print("mode", s.get("mode"), "emergency_stop", s.get("emergency_stop"), "dispatch_lock", s.get("dispatch_lock"),
      "released_for", s.get("emergency_stop_released_for"))
print("provider_sha", hashlib.sha256(json.dumps(prov, sort_keys=True, default=str).encode()).hexdigest())
print("audit", c.ai_call_audit.count_documents({}))
print("candidates", [(str(x["_id"]), x.get("approved"), x.get("mode")) for x in c.ai_test_candidates.find({}, {"approved": 1, "mode": 1})])
