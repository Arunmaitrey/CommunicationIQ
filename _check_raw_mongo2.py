import asyncio, os, sys
os.chdir(r'C:\Users\vinay\Downloads\CommunicationIQ\backend')
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

async def c():
    client = AsyncIOMotorClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    db = client[settings.control_db_name]
    
    # Count all documents with that exact _id string
    count = await db.exam_tests.count_documents({"_id": "6aa9336b08cb80f6c3a858f5"})
    print(f"Count with _id=6aa9336b08cb80f6c3a858f5: {count}")
    
    # Get all documents with is_active true
    active = await db.exam_tests.find({"is_active": True}).to_list(50)
    print(f"\nActive tests in DB: {len(active)}")
    for t in active:
        if not t.get('company'):
            print(f"  {t['_id']} - {t.get('name')} - is_active: {t.get('is_active')}")
    
    # Get all general tests
    general = await db.exam_tests.find({"$or": [{"company": ""}, {"company": None}]}).to_list(50)
    print(f"\nAll general tests: {len(general)}")
    for t in general:
        print(f"  {t['_id']} - {t.get('name')} - is_active: {t.get('is_active')}")
    
    # Check if there are any documents with _id as ObjectId vs string
    # The _id field in MongoDB might be stored as string or ObjectId
    docs = await db.exam_tests.find({}).to_list(50)
    print(f"\nAll exam_tests documents: {len(docs)}")
    id_types = {}
    for d in docs:
        id_type = type(d['_id']).__name__
        if id_type not in id_types:
            id_types[id_type] = 0
        id_types[id_type] += 1
        if not d.get('company'):
            print(f"  {d['_id']} ({id_type}) - {d.get('name')} - is_active: {d.get('is_active')}")
    
    print(f"\nID types: {id_types}")
    
    client.close()

asyncio.run(c())