
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.transaction import TransactionRequest, QueryRequest, APIResponse
from repositories.lnmo_repository import LNMORepository
from database import get_database
from typing import Dict, Any



router = APIRouter(prefix="/ipn/daraja/lnmo", tags=["LNMO"])
lnmo_repository = LNMORepository()

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
