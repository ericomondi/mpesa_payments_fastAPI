import os
import requests
import base64
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, JSON, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from sqlalchemy import select
from databases import Database

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")
database = Database(DATABASE_URL)
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_database() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# =============================================================================
# DATABASE MODELS
# =============================================================================

class Transaction(Base):
    __tablename__ = 'transactions'
    
    # Transaction status constants
    PENDING = 0
    PROCESSING = 1
    PROCESSED = 2
    REJECTED = 3
    ACCEPTED = 4

    # Transaction categories
    PURCHASE_ORDER = 0
    PAYOUT = 1

    # Transaction types
    DEBIT = 0
    CREDIT = 1

    # Transaction channels
    C2B = 0
    LNMO = 1
    B2C = 2
    B2B = 3

    # Transaction aggregators
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=func.now())

    def __repr__(self):
        return f'<Transaction {self.id} - {self._pid}>'

# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class TransactionRequest(BaseModel):
    Amount: Decimal = Field(..., gt=0, description="Transaction amount")
    PhoneNumber: str = Field(..., min_length=10, max_length=15, description="Phone number")
    AccountReference: str = Field(..., min_length=1, max_length=100, description="Account reference")

class QueryRequest(BaseModel):
    transaction_id: str = Field(..., description="Transaction ID to query")

class APIResponse(BaseModel):
    status: str
    message: str
    data: Dict[Any, Any] = {}

class TransactionResponse(BaseModel):
    id: int
    _pid: str
    party_a: str
    party_b: str
    account_reference: str
    transaction_amount: Decimal
    transaction_id: Optional[str]
    transaction_code: Optional[str]
    _status: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# MPESA LNMO REPOSITORY
# =============================================================================

class LNMORepository:
    # MPESA configurations from environment variables
    MPESA_LNMO_CONSUMER_KEY = os.getenv("MPESA_LNMO_CONSUMER_KEY")
    MPESA_LNMO_CONSUMER_SECRET = os.getenv("MPESA_LNMO_CONSUMER_SECRET")
    MPESA_LNMO_ENVIRONMENT = os.getenv("MPESA_LNMO_ENVIRONMENT")
    MPESA_LNMO_INITIATOR_PASSWORD = os.getenv("MPESA_LNMO_INITIATOR_PASSWORD")
    MPESA_LNMO_INITIATOR_USERNAME = os.getenv("MPESA_LNMO_INITIATOR_USERNAME")
    MPESA_LNMO_PASS_KEY = os.getenv("MPESA_LNMO_PASS_KEY")
    MPESA_LNMO_SHORT_CODE = os.getenv("MPESA_LNMO_SHORT_CODE")
    MPESA_LNMO_CALLBACK_URL = os.getenv("MPESA_LNMO_CALLBACK_URL")

    async def transact(self, data: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        """Handle MPESA LNMO transaction"""
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
            "CallBackURL": self.MPESA_LNMO_CALLBACK_URL,
            "AccountReference": data["AccountReference"],
            "TransactionDesc": "Payment for order " + data["AccountReference"],
        }

        response = requests.post(endpoint, json=payload, headers=headers)
        response_data = response.json()

        # Save transaction to the database
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

    def query(self, transaction_id: str) -> Dict[str, Any]:
        """Query MPESA LNMO transaction status"""
        endpoint = f"https://{self.MPESA_LNMO_ENVIRONMENT}.safaricom.co.ke/mpesa/stkpushquery/v1/query"
        headers = {
            "Authorization": "Bearer " + self.generate_access_token(),
            "Content-Type": "application/json",
        }
        payload = {
            "BusinessShortCode": self.MPESA_LNMO_SHORT_CODE,
            "Password": self.generate_password(),
            "Timestamp": datetime.now().strftime("%Y%m%d%H%M%S"),
            "CheckoutRequestID": transaction_id,
        }

        response = requests.post(endpoint, json=payload, headers=headers)
        return response.json()

    async def callback(self, data: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        """Handle MPESA callback"""
        checkout_request_id = data["Body"]["stkCallback"]["CheckoutRequestID"]

        # Find the transaction in the database
        result = await db.execute(
            select(Transaction).where(Transaction.transaction_id == checkout_request_id)
        )
        transaction = result.scalar_one_or_none()

        if transaction:
            # Store the entire callback response in _feedback
            transaction._feedback = data
            # Get the ResultCode to determine success or failure
            result_code = data["Body"]["stkCallback"]["ResultCode"]

            if result_code == 0:
                # Transaction is successful
                transaction._status = Transaction.ACCEPTED
                # Safely access CallbackMetadata
                callback_metadata = data["Body"]["stkCallback"].get("CallbackMetadata")
                if callback_metadata:
                    items = callback_metadata.get("Item", [])
                    for item in items:
                        if item.get("Name") == "MpesaReceiptNumber" and "Value" in item:
                            transaction.transaction_code = item["Value"]
                            break
            else:
                # Transaction failed
                transaction._status = Transaction.REJECTED

            await db.commit()

        return data

    def generate_access_token(self) -> Optional[str]:
        """Generate an access token for the MPESA API"""
        try:
            endpoint = f"https://{self.MPESA_LNMO_ENVIRONMENT}.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
            credentials = (
                f"{self.MPESA_LNMO_CONSUMER_KEY}:{self.MPESA_LNMO_CONSUMER_SECRET}"
            )
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/json",
            }

            response = requests.get(endpoint, headers=headers)
            response_data = response.json()

            if response.status_code == 200:
                return response_data["access_token"]
            else:
                raise Exception(
                    f"Failed to generate access token: {response_data.get('error_description', 'Unknown error')}"
                )

        except Exception as e:
            print(f"Error generating access token: {str(e)}")
            return None

    def generate_password(self) -> Optional[str]:
        """Generate a password for the MPESA API transaction"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            password = base64.b64encode(
                f"{self.MPESA_LNMO_SHORT_CODE}{self.MPESA_LNMO_PASS_KEY}{timestamp}".encode()
            ).decode()
            return password
        except Exception as e:
            print(f"Error generating password: {str(e)}")
            return None

# =============================================================================
# API ROUTES
# =============================================================================

# Initialize the repository
lnmo_repository = LNMORepository()

# Create router
router = APIRouter(prefix="/ipn/daraja/lnmo", tags=["LNMO"])

@router.post("/transact", response_model=APIResponse)
async def transact(
    transaction_data: TransactionRequest,
    db: AsyncSession = Depends(get_database)
):
    """Handle the transaction request for MPESA LNMO"""
    try:
        data = {
            "Amount": transaction_data.Amount,
            "PhoneNumber": transaction_data.PhoneNumber,
            "AccountReference": transaction_data.AccountReference
        }
        
        response = await lnmo_repository.transact(data, db)
        return APIResponse(
            status="info",
            message="Transaction processing",
            data=response
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "danger", "message": str(e), "data": {}}
        )

@router.post("/query", response_model=APIResponse)
async def query(query_data: QueryRequest):
    """Handle the query request for MPESA LNMO transactions"""
    try:
        response = lnmo_repository.query(query_data.transaction_id)
        return APIResponse(
            status="info",
            message="Query processing",
            data=response
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "danger", "message": str(e), "data": {}}
        )

@router.post("/callback", response_model=APIResponse)
async def callback(
    callback_data: Dict[Any, Any],
    db: AsyncSession = Depends(get_database)
):
    """Handle the callback request from MPESA LNMO"""
    try:
        print("Callback data:", callback_data)  # Debugging line
        
        response = await lnmo_repository.callback(callback_data, db)
        return APIResponse(
            status="info",
            message="Callback processing",
            data=response
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "danger", "message": str(e), "data": {}}
        )

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.connect()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await database.disconnect()

# Create FastAPI app
app = FastAPI(
    title="MPESA Payments API",
    description="FastAPI implementation of MPESA LNMO payments",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Welcome to the MPESA Payments API!"}

# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("single:app", host="0.0.0.0", port=8000, reload=True)