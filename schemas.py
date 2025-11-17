"""
Database Schemas for Deal Admin Hub

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase of the class name.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Deal(BaseModel):
    client_name: str
    client_company: Optional[str] = None
    client_contact: Optional[str] = None
    project_name: str
    project_description: Optional[str] = None
    my_name: str = Field(default="Dimiro Networks / 59 Shift")
    my_contact: Optional[str] = None
    status: str = Field(default="active", description="active|archived")

class Mou(BaseModel):
    deal_id: str
    my_details: Dict[str, Any]
    client_details: Dict[str, Any]
    project: Dict[str, Any]
    terms: Dict[str, Any]
    status: str = Field(default="sent", description="draft|sent|signed")
    sign_token: str
    signed_at: Optional[datetime] = None
    client_signature_name: Optional[str] = None
    client_signature_title: Optional[str] = None

class Invoice(BaseModel):
    deal_id: str
    my_details: Dict[str, Any]
    client_name: str
    project_name: str
    invoice_number: str
    invoice_date: str
    due_date: Optional[str] = None
    amount: float
    currency: str
    bank_details: Dict[str, Any]
    payment_reference: str
    status: str = Field(default="sent", description="draft|sent|paid")
    view_token: str
    paid_at: Optional[str] = None
    payment_method: Optional[str] = None
    amount_received: Optional[float] = None

class Receipt(BaseModel):
    invoice_token: str
    deal_id: str
    my_details: Dict[str, Any]
    client_name: str
    project_name: str
    invoice_number: str
    original_amount: float
    amount_paid: float
    payment_date: str
    payment_method: str
    payment_reference: str
