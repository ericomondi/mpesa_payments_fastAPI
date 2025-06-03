import os
from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, JSON, select
from sqlalchemy.sql import func
from databases import Database
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime
from contextlib import asynccontextmanager
import requests
import base64

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:2345@localhost:5432/mpesa")
database = Database(DATABASE_URL)
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# Models
class Transaction(Base):
    __tablename__ = 'transactions'
    
    PENDING = 0
    PROCESSING = 1
    PROCESSED = 2
    REJECTED = 3
    ACCEPTED = 4
    
    PURCHASE_ORDER = 0
    PAYOUT = 1
    
    DEBIT = 0
    CREDIT = 1
    
    C2B = 0
    LNMO = 1
    B2C = 2
    B2B = 3
    
    MPESA_KE = 0
    PAYPAL_USD = 1

    id = Column(Integer, primary_key=True, index=True)
    _pid = Column(String, unique=True, nullable=False, index=True)
    party_a = Column(String, nullable=False)
    party_b = Column(String, nullable=False)
    account_reference = Column(String, nullable=False)
    transaction_category = Column(Integer, nullable=False)
    transaction_type = Column(Integer, nullable=False)
    transaction_channel = Column(Integer, nullable=False)
    transaction_aggregator = Column(Integer, nullable=False)
    transaction_id = Column(String, unique=True, nullable=True, index=True)
    transaction_amount = Column(Numeric(10, 2), nullable=False)
    transaction_code = Column(String, unique=True, nullable=True)
    transaction_timestamp = Column(DateTime, default=datetime.utcnow)
    transaction_details = Column(Text, nullable=False)
    _feedback = Column(JSON, nullable=False)
    _status = Column(Integer, default=PENDING)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

# Schemas
class TransactionRequest(BaseModel):
    Amount: Decimal = Field(..., gt=0)
    PhoneNumber: str = Field(..., min_length=10, max_length=15)
    AccountReference: str = Field(..., min_length=1, max_length=100)

class QueryRequest(BaseModel):
    transaction_id: str

class APIResponse(BaseModel):
    status: str
    message: str
    data: Dict[Any, Any] = {}

# Database dependency
async def get_database() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Repository
class LNMORepository:
    MPESA_LNMO_CONSUMER_KEY = "LO5CCWw0F9QdXWVOMURJGUA8OIEGJ4kL53b2e5ZCm4nKCs7J"
    MPESA_LNMO_CONSUMER_SECRET = "yWbM4wSsOY7CMK4vhdkCgVAcZiBFLA3FtNQV2E3M4odi9gEXXjaHkfcoH42rEsv6"
    MPESA_LNMO_ENVIRONMENT = "sandbox"
    MPESA_LNMO_PASS_KEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
    MPESA_LNMO_SHORT_CODE = "174379"

    async def transact(self, data: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        endpoint = f"https://{self.MPESA_LNMO_ENVIRONMENT}.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
        headers = {
            "Authorization": "Bearer " + self.generate_access_token(),
            "Content-Type": "application/json",
        }
        payload = {
            "BusinessShortCode": self.MPESA_LNMO_SHORT_CODE,
            "Password": self.generate_password(),
            "Timestamp": datetime.now().strftime("%Y%m%d%H%M%S"),
            "TransactionType": "CustomerPayBillOnline",
            "Amount": str(data["Amount"]),
            "PartyA": data["PhoneNumber"],
            "PartyB": self.MPESA_LNMO_SHORT_CODE,
            "PhoneNumber": data["PhoneNumber"],
            "CallBackURL": "https://d270-197-237-26-50.ngrok-free.app/ipn/daraja/lnmo/callback",
            "AccountReference": data["AccountReference"],
            "TransactionDesc": "Payment for order " + data["AccountReference"],
        }

        response = requests.post(endpoint, json=payload, headers=headers)
        response_data = response.json()

        transaction = Transaction(
            _pid=data["AccountReference"],
            party_a=data["PhoneNumber"],
            party_b=self.MPESA_LNMO_SHORT_CODE,
            account_reference=data["AccountReference"],
            transaction_category=Transaction.PURCHASE_ORDER,
            transaction_type=Transaction.CREDIT,
            transaction_channel=Transaction.LNMO,
            transaction_aggregator=Transaction.MPESA_KE,
            transaction_id=response_data.get("CheckoutRequestID"),
            transaction_amount=data["Amount"],
            transaction_code=None,
            transaction_timestamp=datetime.now(),
            transaction_details="Payment for order " + data["AccountReference"],
            _feedback=response_data,
            _status=Transaction.PROCESSING,
        )
        
        db.add(transaction)
        await db.commit()
        await db.refresh(transaction)
        return response_data

    def generate_access_token(self) -> Optional[str]:
        try:
            endpoint = f"https://{self.MPESA_LNMO_ENVIRONMENT}.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
            credentials = f"{self.MPESA_LNMO_CONSUMER_KEY}:{self.MPESA_LNMO_CONSUMER_SECRET}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers = {"Authorization": f"Basic {encoded_credentials}"}
            response = requests.get(endpoint, headers=headers)
            return response.json().get("access_token")
        except Exception as e:
            print(f"Error generating access token: {str(e)}")
            return None

    def generate_password(self) -> Optional[str]:
        try:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            password = base64.b64encode(
                f"{self.MPESA_LNMO_SHORT_CODE}{self.MPESA_LNMO_PASS_KEY}{timestamp}".encode()
            ).decode()
            return password
        except Exception as e:
            print(f"Error generating password: {str(e)}")
            return None

# App setup
@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await database.disconnect()

app = FastAPI(title="MPESA Payments API", lifespan=lifespan)
lnmo_repository = LNMORepository()

@app.post("/ipn/daraja/lnmo/transact", response_model=APIResponse)
async def transact(transaction_data: TransactionRequest, db: AsyncSession = Depends(get_database)):
    try:
        data = {
            "Amount": transaction_data.Amount,
            "PhoneNumber": transaction_data.PhoneNumber,
            "AccountReference": transaction_data.AccountReference
        }
        response = await lnmo_repository.transact(data, db)
        return APIResponse(status="info", message="Transaction processing", data=response)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"status": "danger", "message": str(e)})

@app.get("/")
async def root():
    return {"message": "Welcome to the MPESA Payments API!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("appsingle:app", host="0.0.0.0", port=8000, reload=True)