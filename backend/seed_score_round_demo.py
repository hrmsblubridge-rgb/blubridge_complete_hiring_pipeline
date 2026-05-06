"""Iter57 — Seed 10 demo candidates for Score & Round module.

Idempotent: re-running re-seeds the same 10 records via upsert by email.
All rows tagged `isTest: True` and `seed: 'score_round_iter57'` for safe cleanup.
Run:
    python3 /app/backend/seed_score_round_demo.py
Cleanup:
    python3 /app/backend/seed_score_round_demo.py --cleanup
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

SEED_TAG = "score_round_iter57"

NOW = datetime.now(timezone.utc).isoformat()


def _ymd(days_offset):
    return (datetime.now(timezone.utc) + timedelta(days=days_offset)).strftime("%Y-%m-%d")


CANDIDATES = [
    {
        "name": "Aarav Sharma",
        "email": "aarav.sharma.demo@example.com",
        "phone": "9876543201",
        "college": "Anna University",
        "degree": "B.Tech",
        "course": "Computer Science",
        "year_of_graduation": 2025,
        "job_role": "AI/ML Engineer",
        "result_status": "Shortlisted",
        "schedule_date": _ymd(-30),
        "scores": [
            {"round_name": "BA", "date": _ymd(-29), "score": 88, "command": "Strong analytical skills", "status": "Shortlisted"},
            {"round_name": "Java", "date": _ymd(-28), "score": 92, "command": "Solid OOP fundamentals", "status": "Shortlisted"},
            {"round_name": "Mensa", "date": _ymd(-27), "score": 75, "command": "Above-average reasoning", "status": "Shortlisted"},
        ],
        "date_of_joining": _ymd(20),
        "date_of_documentation": _ymd(25),
        "date_of_induction": _ymd(30),
        "overall_status": "Shortlisted",
    },
    {
        "name": "Diya Patel",
        "email": "diya.patel.demo@example.com",
        "phone": "9876543202",
        "college": "VIT Vellore",
        "degree": "B.E.",
        "course": "Information Technology",
        "year_of_graduation": 2024,
        "job_role": "Software Engineer",
        "result_status": "OnBoard",
        "schedule_date": _ymd(-45),
        "scores": [
            {"round_name": "C++", "date": _ymd(-44), "score": 78, "command": "Good with templates", "status": "Shortlisted"},
            {"round_name": "BA", "date": _ymd(-43), "score": 82, "command": "Solid logical reasoning", "status": "Shortlisted"},
            {"round_name": "BP", "date": _ymd(-42), "score": 90, "command": "Excellent business acumen", "status": "OnBoard"},
        ],
        "date_of_joining": _ymd(5),
        "date_of_documentation": _ymd(10),
        "date_of_induction": _ymd(15),
        "overall_status": "OnBoard",
    },
    {
        "name": "Rohan Iyer",
        "email": "rohan.iyer.demo@example.com",
        "phone": "9876543203",
        "college": "IIT Madras",
        "degree": "B.Tech",
        "course": "Electrical",
        "year_of_graduation": 2025,
        "job_role": "Data Scientist",
        "result_status": "Active/On-track",
        "schedule_date": _ymd(-15),
        "scores": [
            {"round_name": "Mensa", "date": _ymd(-14), "score": 95, "command": "Top score in cohort", "status": "Active/On-track"},
            {"round_name": "Mensa Org", "date": _ymd(-13), "score": 89, "command": "Strong organisational thinking", "status": "Active/On-track"},
        ],
        "date_of_joining": "",
        "date_of_documentation": "",
        "date_of_induction": "",
        "overall_status": "Active/On-track",
    },
    {
        "name": "Meera Krishnan",
        "email": "meera.krishnan.demo@example.com",
        "phone": "9876543204",
        "college": "SRM University",
        "degree": "BCA",
        "course": "Computer Applications",
        "year_of_graduation": 2024,
        "job_role": "Backend Developer",
        "result_status": "On-Hold",
        "schedule_date": _ymd(-10),
        "scores": [
            {"round_name": "Java", "date": _ymd(-9), "score": 65, "command": "Needs more practice with Spring", "status": "On-Hold"},
            {"round_name": "BA", "date": _ymd(-8), "score": 70, "command": "Average analytical skills", "status": "On-Hold"},
        ],
        "date_of_joining": "",
        "date_of_documentation": "",
        "date_of_induction": "",
        "overall_status": "On-Hold",
    },
    {
        "name": "Karthik Raman",
        "email": "karthik.raman.demo@example.com",
        "phone": "9876543205",
        "college": "PSG Tech",
        "degree": "B.E.",
        "course": "Mechanical",
        "year_of_graduation": 2025,
        "job_role": "QA Engineer",
        "result_status": "Confirmed For Exam",
        "schedule_date": _ymd(7),
        "scores": [
            {"round_name": "LA", "date": _ymd(-1), "score": 80, "command": "Sharp logical aptitude", "status": "Confirmed For Exam"},
        ],
        "date_of_joining": "",
        "date_of_documentation": "",
        "date_of_induction": "",
        "overall_status": "Confirmed For Exam",
    },
    {
        "name": "Anaya Reddy",
        "email": "anaya.reddy.demo@example.com",
        "phone": "9876543206",
        "college": "BITS Pilani",
        "degree": "M.Tech",
        "course": "Data Science",
        "year_of_graduation": 2025,
        "job_role": "ML Engineer",
        "result_status": "Doubtfull/Monitor",
        "schedule_date": _ymd(-5),
        "scores": [
            {"round_name": "Mensa", "date": _ymd(-4), "score": 60, "command": "Borderline — recheck", "status": "Doubtfull/Monitor"},
            {"round_name": "BA", "date": _ymd(-3), "score": 55, "command": "Weak in business reasoning", "status": "Doubtfull/Monitor"},
        ],
        "date_of_joining": "",
        "date_of_documentation": "",
        "date_of_induction": "",
        "overall_status": "Doubtfull/Monitor",
    },
    {
        "name": "Vikram Joshi",
        "email": "vikram.joshi.demo@example.com",
        "phone": "9876543207",
        "college": "NIT Trichy",
        "degree": "B.Tech",
        "course": "Civil",
        "year_of_graduation": 2024,
        "job_role": "Project Engineer",
        "result_status": "Rejected",
        "schedule_date": _ymd(-60),
        "scores": [
            {"round_name": "BP", "date": _ymd(-59), "score": 35, "command": "Did not meet bar", "status": "Rejected"},
            {"round_name": "BA", "date": _ymd(-58), "score": 42, "command": "Significant gaps", "status": "Rejected"},
        ],
        "date_of_joining": "",
        "date_of_documentation": "",
        "date_of_induction": "",
        "overall_status": "Rejected",
    },
    {
        "name": "Priya Nair",
        "email": "priya.nair.demo@example.com",
        "phone": "9876543208",
        "college": "Anna University",
        "degree": "B.Tech",
        "course": "ECE",
        "year_of_graduation": 2025,
        "job_role": "Embedded Engineer",
        "result_status": "Shortlisted",
        "schedule_date": _ymd(-20),
        "scores": [
            {"round_name": "C++", "date": _ymd(-19), "score": 85, "command": "Strong embedded fundamentals", "status": "Shortlisted"},
            {"round_name": "Java", "date": _ymd(-18), "score": 72, "command": "Decent OOP grasp", "status": "Shortlisted"},
            {"round_name": "ZA", "date": _ymd(-17), "score": 79, "command": "Good zonal aptitude", "status": "Shortlisted"},
        ],
        "date_of_joining": _ymd(25),
        "date_of_documentation": _ymd(28),
        "date_of_induction": "",
        "overall_status": "Shortlisted",
    },
    {
        "name": "Arjun Menon",
        "email": "arjun.menon.demo@example.com",
        "phone": "9876543209",
        "college": "IIT Bombay",
        "degree": "B.Tech",
        "course": "Computer Science",
        "year_of_graduation": 2025,
        "job_role": "Full Stack Developer",
        "result_status": "Scheduled",
        "schedule_date": _ymd(3),
        "scores": [],
        "date_of_joining": "",
        "date_of_documentation": "",
        "date_of_induction": "",
        "overall_status": "Scheduled",
    },
    {
        "name": "Ishita Verma",
        "email": "ishita.verma.demo@example.com",
        "phone": "9876543210",
        "college": "Manipal Institute",
        "degree": "B.Tech",
        "course": "AI & DS",
        "year_of_graduation": 2025,
        "job_role": "AI/ML Engineer",
        "result_status": "Active/On-track",
        "schedule_date": _ymd(-12),
        "scores": [
            {"round_name": "Mensa", "date": _ymd(-11), "score": 91, "command": "Outstanding reasoning", "status": "Active/On-track"},
            {"round_name": "Mensa Org", "date": _ymd(-10), "score": 84, "command": "Strong org skills", "status": "Active/On-track"},
            {"round_name": "Java", "date": _ymd(-9), "score": 87, "command": "Solid backend exposure", "status": "Active/On-track"},
            {"round_name": "BA", "date": _ymd(-8), "score": 90, "command": "Top-tier analytical thinking", "status": "Active/On-track"},
        ],
        "date_of_joining": "",
        "date_of_documentation": "",
        "date_of_induction": "",
        "overall_status": "Active/On-track",
    },
]


async def seed():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    inserted, updated = 0, 0
    for c in CANDIDATES:
        em = c["email"].lower()
        # 1) pipeline_data — basic info + dates
        pd_doc = {
            "name": c["name"],
            "email": em,
            "phone": c["phone"],
            "college": c["college"],
            "degree": c["degree"],
            "course": c["course"],
            "year_of_graduation": c["year_of_graduation"],
            "job_role": c["job_role"],
            "result_status": c["result_status"],
            "schedule_date": c["schedule_date"],
            "schedule_time": "10:30:00",
            "date_of_joining": c["date_of_joining"],
            "date_of_documentation": c["date_of_documentation"],
            "date_of_induction": c["date_of_induction"],
            "isTest": True,
            "seed": SEED_TAG,
            "updated_at": NOW,
            "otp_verified": "1",  # so it shows up in attended-for-scores too
        }
        res = await db.pipeline_data.update_one(
            {"email": em, "seed": SEED_TAG},
            {"$set": pd_doc, "$setOnInsert": {"created_at": NOW}},
            upsert=True,
        )
        if res.upserted_id:
            inserted += 1
        else:
            updated += 1
        # 2) bb_applicant_updates — scores + status
        scores_with_ts = [
            {**s, "updated_at": NOW} for s in c["scores"]
        ]
        await db.bb_applicant_updates.update_one(
            {"email": em},
            {"$set": {
                "email": em,
                "phone": c["phone"],
                "scores": scores_with_ts,
                "status": c["overall_status"],
                "isTest": True,
                "seed": SEED_TAG,
                "updated_at": NOW,
            }},
            upsert=True,
        )
    print(f"[seed] inserted={inserted} updated={updated} total={len(CANDIDATES)}")


async def cleanup():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    r1 = await db.pipeline_data.delete_many({"seed": SEED_TAG})
    emails = [c["email"].lower() for c in CANDIDATES]
    r2 = await db.bb_applicant_updates.delete_many({"email": {"$in": emails}, "seed": SEED_TAG})
    print(f"[cleanup] pipeline_data deleted={r1.deleted_count} bb_applicant_updates deleted={r2.deleted_count}")


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        asyncio.run(cleanup())
    else:
        asyncio.run(seed())
