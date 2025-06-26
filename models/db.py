from typing import List, Optional, Type, TypeVar, Union
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pydantic import BaseModel, Field as PydanticField
from bson import ObjectId
from tools import LanguageSingleton

T = TypeVar("T", bound=BaseModel)


# -----------------------------
# Utility Pydantic + BSON ID
# -----------------------------

class PyObjectId(ObjectId):

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)


# -----------------------------
# Data Models
# -----------------------------

class ChapterFile(BaseModel):
    id: PyObjectId = PydanticField(default_factory=PyObjectId, alias="_id")
    url: str
    file_id: Optional[str] = None
    file_unique_id: Optional[str] = None
    cbz_id: Optional[str] = None
    cbz_unique_id: Optional[str] = None
    telegraph_url: Optional[str] = None


class MangaOutput(BaseModel):
    id: PyObjectId = PydanticField(default_factory=PyObjectId, alias="_id")
    user_id: str
    output: int


class Subscription(BaseModel):
    id: PyObjectId = PydanticField(default_factory=PyObjectId, alias="_id")
    url: str
    user_id: str


class LastChapter(BaseModel):
    id: PyObjectId = PydanticField(default_factory=PyObjectId, alias="_id")
    url: str
    chapter_url: str


class MangaName(BaseModel):
    id: PyObjectId = PydanticField(default_factory=PyObjectId, alias="_id")
    url: str
    name: str


# -----------------------------
# MongoDB Database Handler
# -----------------------------

class DB(metaclass=LanguageSingleton):
    def __init__(self, uri: str = "mongodb://localhost:27017", db_name: str = "manga"):
        self.client: AsyncIOMotorClient = AsyncIOMotorClient(uri)
        self.db: AsyncIOMotorDatabase = self.client[db_name]

    async def connect(self):
        # Optional connection test
        try:
            await self.client.admin.command('ping')  # Verify connection
            print("MongoDB connected successfully.")
        except Exception as e:
            print(f"Error connecting to MongoDB: {e}")

    async def add(self, collection: str, document: BaseModel):
        collection_name = collection.__name__.lower()
        existing = await self.db[collection_name].find_one({"_id": document.id})
        if not existing:
            await self.db[collection_name].insert_one(document.dict(by_alias=True))

    async def update_last(self, collection: str, document: BaseModel):
        collection_name = collection.__name__.lower()
        existing = await self.db[collection_name].find_one({"_id": document.id})
        if not existing:
            await self.db[collection_name].insert_one(document.dict(by_alias=True))
        else:
            await self.db[collection_name].update_one({"_id": document.id}, {"$set": document.dict(by_alias=True)})



    async def get(self, collection: str, query: dict) -> Optional[dict]:
        collection_name = collection.__name__.lower()
        s = await self.db[collection_name].find_one({"url": query[0]})
        return s


    async def get_all(self, model: Type[T]) -> List[T]:
        collection_name = model.__name__.lower()
        cursor = self.db[collection_name].find()
        documents = await cursor.to_list(length=None)
        return [model(**doc) for doc in documents]


    async def erase(self, collection: str, query: dict):
        collection_name = collection.__name__.lower()
        await self.db[collection_name].delete_one(query)

    async def get_chapter_file_by_id(self, id: str) -> Optional[dict]:
        query = {
            "$or": [
                {"file_unique_id": id},
                {"cbz_unique_id": id},
                {"telegraph_url": id},
            ]
        }
        return await self.db["chapterfile"].find_one(query)

    async def get_subs(self, user_id: str, filters: Optional[List[str]] = None) -> List[dict]:
        match_stage = {"$match": {"user_id": user_id}}
        pipeline = [
            {"$lookup": {
                "from": "manganame",
                "localField": "url",
                "foreignField": "url",
                "as": "manga"
            }},
            {"$unwind": "$manga"},
            match_stage,
        ]
        if filters:
            regex_filters = [{"manga.name": {"$regex": f, "$options": "i"}} for f in filters]
            pipeline.append({"$match": {"$or": regex_filters}})
        cursor = self.db["subscription"].aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def erase_subs(self, user_id: str):
        await self.db["subscription"].delete_many({"user_id": user_id})
