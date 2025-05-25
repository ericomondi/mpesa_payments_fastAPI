
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, JSON
from sqlalchemy.sql import func
from database import Base
from datetime import datetime

class Transaction(Base):
    __tablename__ = 'transactions'
    
    # Define the transaction status as constants
    PENDING = 0
    PROCESSING = 1
    PROCESSED = 2
    REJECTED = 3
    ACCEPTED = 4

    # Define the transaction categories
    PURCHASE_ORDER = 0
    PAYOUT = 1

    # Define the transaction types
    DEBIT = 0
    CREDIT = 1

    # Define the transaction channels
    C2B = 0
    LNMO = 1
    B2C = 2
    B2B = 3

    # Define the transaction aggregator
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
