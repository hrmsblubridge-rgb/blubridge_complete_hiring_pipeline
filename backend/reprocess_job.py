import asyncio, os, re, sys

# Load .env
with open('/app/backend/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, val = line.split('=', 1)
            os.environ[key.strip()] = val.strip().strip('"')

from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=30000, connectTimeoutMS=30000, socketTimeoutMS=600000)
db = client[os.environ['DB_NAME']]

def normalize_email(e):
    if not e: return ''
    return str(e).strip().lower()

def normalize_phone(p):
    if not p: return ''
    digits = re.sub(r'[^\d]', '', str(p))
    if len(digits) > 10: digits = digits[-10:]
    return digits if len(digits) == 10 else ''

LOG = '/tmp/reprocess.log'
def log(msg):
    with open(LOG, 'a') as f:
        f.write(msg + '\n')
        f.flush()
    print(msg, flush=True)

async def reprocess():
    with open(LOG, 'w') as f:
        f.write('')

    log('Phase 1: Loading pipeline emails/phones...')
    # Only load email+phone from pipeline first (lightweight)
    pbe = {}
    pbp = {}
    count = 0
    async for p in db.pipeline_data.find({}, {'email': 1, 'phone': 1}):
        em = normalize_email(p.get('email'))
        ph = normalize_phone(p.get('phone'))
        pid = str(p['_id'])
        if em: pbe[em] = pid
        if ph: pbp[ph] = pid
        count += 1
        if count % 10000 == 0:
            log(f'  pipeline scanned: {count}')
    log(f'Pipeline index done: {count} records, {len(pbe)} emails, {len(pbp)} phones')

    log('Phase 2: Loading naukri and finding matches...')
    matched_pipeline_ids = set()
    naukri_by_pid = {}
    ncount = 0
    async for n in db.naukri_applies.find({}):
        ncount += 1
        email = normalize_email(n.get('email'))
        phone = normalize_phone(n.get('phone'))
        pid = pbe.get(email) or pbp.get(phone)
        if pid:
            n.pop('_id', None)
            matched_pipeline_ids.add(pid)
            naukri_by_pid[pid] = n
        if ncount % 10000 == 0:
            log(f'  naukri scanned: {ncount}')
    log(f'Naukri done: {ncount} records, {len(naukri_by_pid)} matches')

    log(f'Phase 3: Loading {len(matched_pipeline_ids)} matched pipeline docs...')
    from bson import ObjectId
    pid_list = [ObjectId(p) for p in matched_pipeline_ids]
    
    await db.registered_candidates.drop()
    skip = {'_id', '_is_registered', 'created_at', 'updated_at'}
    docs = []
    batch_num = 0
    
    # Load pipeline docs in chunks
    chunk_size = 5000
    for i in range(0, len(pid_list), chunk_size):
        chunk = pid_list[i:i+chunk_size]
        pdocs = await db.pipeline_data.find({'_id': {'$in': chunk}}).to_list(None)
        for pm in pdocs:
            pid = str(pm['_id'])
            n = naukri_by_pid.get(pid)
            if not n:
                continue
            d = {k: v for k, v in pm.items() if k not in skip}
            for k, v in n.items():
                if k not in skip:
                    if v is not None and v != '':
                        d[k] = v
                    elif k not in d:
                        d[k] = v
            docs.append(d)
        
        # Insert in batches as we go
        while len(docs) >= 2000:
            batch = docs[:2000]
            docs = docs[2000:]
            await db.registered_candidates.insert_many(batch)
            batch_num += 1
            log(f'  Inserted batch {batch_num}')
    
    # Insert remaining
    if docs:
        await db.registered_candidates.insert_many(docs)
        batch_num += 1
        log(f'  Inserted final batch {batch_num}')
    
    log('Phase 4: Creating indexes...')
    await db.registered_candidates.create_index([('email', 1), ('phone', 1)])
    await db.registered_candidates.create_index('email_type')
    await db.registered_candidates.create_index('otp_verified')
    
    c = await db.registered_candidates.count_documents({})
    log(f'DONE! registered_candidates: {c}')

asyncio.run(reprocess())
