
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from decimal import Decimal
from datetime import datetime

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
