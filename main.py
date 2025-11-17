import os
import io
import base64
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from uuid import uuid4

from database import db, create_document, get_documents
from schemas import Deal, Mou, Invoice, Receipt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Deal Admin Hub Backend"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

# --------- Models for requests ---------
class CreateMouRequest(BaseModel):
    my_details: dict
    client_details: dict
    project: dict
    terms: dict

class SignMouRequest(BaseModel):
    name: str
    title: str
    agree: bool

class CreateInvoiceRequest(BaseModel):
    my_details: dict
    client_name: str
    project_name: str
    invoice_number: str
    invoice_date: str
    due_date: Optional[str] = None
    amount: float
    currency: str
    bank_details: dict
    payment_reference: str

class MarkPaidRequest(BaseModel):
    payment_date: Optional[str] = None
    payment_method: str
    amount_received: float
    payment_reference: str

# Utility

def collection(name: str):
    return db[name]

# --------- MOU endpoints ---------
@app.post("/api/mou")
def create_mou(payload: CreateMouRequest):
    token = uuid4().hex
    deal = Deal(
        client_name=payload.client_details.get("client_name") or payload.client_details.get("name", ""),
        client_company=payload.client_details.get("company"),
        client_contact=payload.client_details.get("contact"),
        project_name=payload.project.get("name", ""),
        project_description=payload.project.get("description"),
    )
    deal_id = create_document("deal", deal)

    mou = Mou(
        deal_id=deal_id,
        my_details=payload.my_details,
        client_details=payload.client_details,
        project=payload.project,
        terms=payload.terms,
        status="sent",
        sign_token=token,
    )
    mou_id = create_document("mou", mou)

    return {"mou_id": mou_id, "sign_url_token": token}

@app.get("/api/mou/{token}")
def get_mou_by_token(token: str):
    doc = collection("mou").find_one({"sign_token": token})
    if not doc:
        raise HTTPException(status_code=404, detail="MOU not found")
    doc["_id"] = str(doc["_id"])
    return doc

@app.post("/api/mou/{token}/sign")
def sign_mou(token: str, payload: SignMouRequest):
    if not payload.agree:
        raise HTTPException(status_code=400, detail="Agreement checkbox is required")
    result = collection("mou").find_one_and_update(
        {"sign_token": token},
        {"$set": {
            "status": "signed",
            "client_signature_name": payload.name,
            "client_signature_title": payload.title,
            "signed_at": datetime.utcnow().isoformat()
        }},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="MOU not found")
    return {"status": "signed"}

# --------- Invoice endpoints ---------
@app.post("/api/invoice")
def create_invoice(payload: CreateInvoiceRequest):
    token = uuid4().hex
    # find (or create) deal for client+project
    deal = collection("deal").find_one({
        "client_name": payload.client_name,
        "project_name": payload.project_name,
    })
    if not deal:
        d = Deal(client_name=payload.client_name, project_name=payload.project_name)
        deal_id = create_document("deal", d)
    else:
        deal_id = str(deal["_id"])

    inv = Invoice(
        deal_id=deal_id,
        my_details=payload.my_details,
        client_name=payload.client_name,
        project_name=payload.project_name,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        amount=payload.amount,
        currency=payload.currency,
        bank_details=payload.bank_details,
        payment_reference=payload.payment_reference,
        status="sent",
        view_token=token,
    )
    inv_id = create_document("invoice", inv)
    return {"invoice_id": inv_id, "view_url_token": token}

@app.get("/api/invoice/{token}")
def get_invoice_by_token(token: str):
    doc = collection("invoice").find_one({"view_token": token})
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    doc["_id"] = str(doc["_id"])
    return doc

@app.post("/api/invoice/{token}/paid")
def mark_invoice_paid(token: str, payload: MarkPaidRequest):
    doc = collection("invoice").find_one({"view_token": token})
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")

    payment_date = payload.payment_date or datetime.utcnow().date().isoformat()
    collection("invoice").update_one({"view_token": token}, {"$set": {
        "status": "paid",
        "paid_at": payment_date,
        "payment_method": payload.payment_method,
        "amount_received": payload.amount_received,
    }})

    receipt = Receipt(
        invoice_token=token,
        deal_id=str(doc["deal_id"]),
        my_details=doc["my_details"],
        client_name=doc["client_name"],
        project_name=doc["project_name"],
        invoice_number=doc["invoice_number"],
        original_amount=doc["amount"],
        amount_paid=payload.amount_received,
        payment_date=payment_date,
        payment_method=payload.payment_method,
        payment_reference=payload.payment_reference,
    )
    receipt_id = create_document("receipt", receipt)
    return {"status": "paid", "receipt_id": receipt_id}

# --------- Simple PDFs (HTML to PDF via browser print) ---------
# We will return HTML content to the frontend; frontend will render and offer PDF download via print.

# --------- Snapshot endpoint ---------
@app.get("/api/deal/snapshot")
def deal_snapshot(client_name: str, project_name: str):
    deal = collection("deal").find_one({"client_name": client_name, "project_name": project_name})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    deal_id = str(deal["_id"]) if "_id" in deal else deal.get("id", "")

    mou = collection("mou").find_one({"deal_id": deal_id}, sort=[("created_at", -1)])
    invoice = collection("invoice").find_one({"deal_id": deal_id}, sort=[("created_at", -1)])
    receipt = None
    if invoice:
        receipt = collection("receipt").find_one({"invoice_token": invoice.get("view_token")}, sort=[("created_at", -1)])

    def mou_status():
        if not mou:
            return {"status": "Draft", "link": None}
        status = mou.get("status", "draft").capitalize()
        link = f"/sign/{mou.get('sign_token')}" if mou.get("sign_token") else None
        return {"status": status, "link": link}

    def invoice_status():
        if not invoice:
            return {"status": "Draft", "link": None}
        status = invoice.get("status", "draft").capitalize()
        link = f"/invoice/{invoice.get('view_token')}" if invoice.get("view_token") else None
        return {"status": status, "link": link}

    # Next step hint
    hint = ""
    ms = mou_status()["status"].lower()
    ins = invoice_status()["status"].lower()
    if ms == "draft":
        hint = "Next: Generate sign link and send to client."
    elif ms == "signed" and ins == "draft":
        hint = "Next: Generate invoice and send."
    elif ins == "paid" and not receipt:
        hint = "Next: Generate receipt and send."

    return {
        "client_name": client_name,
        "project_name": project_name,
        "mou": mou_status(),
        "invoice": invoice_status(),
        "receipt_available": True if receipt else False,
        "next_step": hint
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
