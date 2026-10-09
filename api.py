from fastapi import FastAPI, HTTPException, Header, BackgroundTasks, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import pytz
import os
import uuid
import requests
import logging
from bson import ObjectId

import asyncio
from database import db, xmr_payments_col, get_setting, set_setting
from utils.xmr import usd_to_xmr, get_xmr_price_in_usd, check_xmr_transfers_rpc, create_xmr_subaddress_rpc, verify_xmr_txid_rpc
from config import PORT

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Monero Payment Gateway API",
    description="REST API for processing Monero (XMR) payments and invoices on Render.com",
    version="1.0.0"
)

# Models
class CreateInvoiceRequest(BaseModel):
    amount_usd: float = Field(..., gt=0, description="Amount in USD to charge")
    order_id: Optional[str] = Field(None, description="Client order/reference ID")
    description: Optional[str] = Field("Monero Payment Invoice", description="Invoice description")
    callback_url: Optional[str] = Field(None, description="Webhook URL for payment status updates")
    expiry_minutes: Optional[int] = Field(60, ge=5, le=1440, description="Invoice validity in minutes")

class VerifyPaymentRequest(BaseModel):
    txid: str = Field(..., description="Monero transaction hash/ID")

# Helper to format Mongo Invoice doc for JSON responses
def format_invoice_doc(doc: dict) -> dict:
    created_at = doc.get("created_at")
    expires_at = doc.get("expires_at")

    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    if isinstance(expires_at, datetime):
        expires_at = expires_at.isoformat()

    return {
        "invoice_id": str(doc["_id"]),
        "order_id": doc.get("order_id"),
        "address": doc.get("address"),
        "xmr_amount": doc.get("xmr_amount"),
        "price_usd": doc.get("price_usd"),
        "xmr_rate_usd": doc.get("xmr_rate_usd"),
        "status": doc.get("status", "pending"),
        "is_claimed": doc.get("is_claimed", False),
        "txid": doc.get("txid"),
        "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=monero:{doc.get('address')}?tx_amount={doc.get('xmr_amount', 0):.6f}",
        "created_at": created_at,
        "expires_at": expires_at,
        "callback_url": doc.get("callback_url")
    }

async def trigger_webhook(callback_url: str, payload: dict):
    if not callback_url:
        return
    try:
        res = requests.post(callback_url, json=payload, timeout=10)
        logger.info(f"Webhook delivered to {callback_url}: Status {res.status_code}")
    except Exception as e:
        logger.error(f"Failed to deliver webhook to {callback_url}: {e}")

@app.get("/health", tags=["Health"])
async def health_check():
    db_status = "connected"
    try:
        await db.command("ping")
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "online",
        "service": "Monero Payment Gateway API",
        "database": db_status,
        "timestamp": datetime.now(pytz.utc).isoformat()
    }

@app.post("/api/v1/invoices/create", tags=["Invoices"])
async def create_invoice(req: CreateInvoiceRequest):
    xmr_address = await get_setting("xmr_address", os.getenv("MONERO_ADDRESS", ""))
    rpc_url = os.getenv("MONERO_RPC_URL", "")
    rpc_user = os.getenv("MONERO_RPC_USER", "")
    rpc_pass = os.getenv("MONERO_RPC_PASSWORD", "")

    address_to_use = xmr_address

    # If wallet RPC is available, attempt subaddress generation for clean tracking
    if rpc_url:
        try:
            sub_res = await create_xmr_subaddress_rpc(
                rpc_url=rpc_url,
                label=f"order_{req.order_id or str(uuid.uuid4())[:8]}",
                rpc_user=rpc_user,
                rpc_password=rpc_pass
            )
            if sub_res.get("address"):
                address_to_use = sub_res["address"]
        except Exception as e:
            logger.warning(f"Could not derive subaddress via RPC: {e}")

    if not address_to_use:
        raise HTTPException(status_code=500, detail="Monero primary address or RPC wallet is not configured on the server.")

    xmr_rate = await get_xmr_price_in_usd()
    xmr_amount = await usd_to_xmr(req.amount_usd)

    now_utc = datetime.now(pytz.utc)
    expires_at = now_utc + timedelta(minutes=req.expiry_minutes)

    inv_doc = {
        "user_id": None,
        "order_id": req.order_id or str(uuid.uuid4())[:12],
        "description": req.description,
        "address": address_to_use,
        "xmr_amount": xmr_amount,
        "price_usd": req.amount_usd,
        "xmr_rate_usd": xmr_rate,
        "status": "pending",
        "is_claimed": False,
        "txid": None,
        "created_at": now_utc,
        "expires_at": expires_at,
        "callback_url": req.callback_url
    }

    res = await xmr_payments_col.insert_one(inv_doc)
    inv_doc["_id"] = res.inserted_id

    return {
        "success": True,
        "invoice": format_invoice_doc(inv_doc)
    }

@app.get("/api/v1/invoices/{invoice_id}", tags=["Invoices"])
async def get_invoice(invoice_id: str):
    try:
        inv = await xmr_payments_col.find_one({"_id": ObjectId(invoice_id)})
    except Exception:
        inv = None

    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    # Check if expired
    now_utc = datetime.now(pytz.utc)
    expires_at = inv["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = pytz.utc.localize(expires_at)

    if inv["status"] == "pending" and now_utc > expires_at:
        await xmr_payments_col.update_one({"_id": inv["_id"]}, {"$set": {"status": "expired"}})
        inv["status"] = "expired"

    return {
        "success": True,
        "invoice": format_invoice_doc(inv)
    }

@app.get("/api/v1/invoices", tags=["Invoices"])
async def list_invoices(status: Optional[str] = Query(None, description="Filter by status: pending, confirmed, expired"), limit: int = Query(50, le=200)):
    query = {}
    if status:
        query["status"] = status

    cursor = xmr_payments_col.find(query).sort("created_at", -1).limit(limit)
    invoices = await cursor.to_list(limit)

    return {
        "success": True,
        "count": len(invoices),
        "invoices": [format_invoice_doc(doc) for doc in invoices]
    }

@app.post("/api/v1/invoices/{invoice_id}/verify", tags=["Invoices"])
async def verify_invoice_payment(invoice_id: str, req: VerifyPaymentRequest, background_tasks: BackgroundTasks):
    try:
        inv = await xmr_payments_col.find_one({"_id": ObjectId(invoice_id)})
    except Exception:
        inv = None

    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found.")

    if inv.get("is_claimed") or inv.get("status") == "confirmed":
        return {
            "success": True,
            "message": "Payment already confirmed.",
            "invoice": format_invoice_doc(inv)
        }

    # Verify via Monero RPC if configured
    rpc_url = os.getenv("MONERO_RPC_URL", "")
    rpc_user = os.getenv("MONERO_RPC_USER", "")
    rpc_pass = os.getenv("MONERO_RPC_PASSWORD", "")

    if rpc_url:
        verification = await verify_xmr_txid_rpc(
            rpc_url=rpc_url,
            txid=req.txid.strip(),
            target_address=inv.get("address"),
            min_amount_xmr=inv.get("xmr_amount", 0.0),
            rpc_user=rpc_user,
            rpc_password=rpc_pass
        )
        if not verification.get("valid"):
            raise HTTPException(status_code=400, detail=f"Transaction verification failed: {verification.get('reason')}")

    now_utc = datetime.now(pytz.utc)
    res = await xmr_payments_col.update_one(
        {"_id": inv["_id"], "is_claimed": False},
        {"$set": {
            "status": "confirmed",
            "is_claimed": True,
            "txid": req.txid.strip(),
            "claimed_at": now_utc
        }}
    )

    if res.modified_count == 0:
        raise HTTPException(status_code=400, detail="Payment already processed or expired.")

    inv["status"] = "confirmed"
    inv["is_claimed"] = True
    inv["txid"] = req.txid.strip()

    if inv.get("callback_url"):
        background_tasks.add_task(
            trigger_webhook,
            inv["callback_url"],
            {"event": "invoice.paid", "invoice": format_invoice_doc(inv)}
        )

    return {
        "success": True,
        "message": "Payment verified successfully!",
        "invoice": format_invoice_doc(inv)
    }

async def scan_pending_xmr_invoices_loop():
    """Background task that periodically polls monero-wallet-rpc for transfers on pending invoices."""
    while True:
        try:
            rpc_url = os.getenv("MONERO_RPC_URL", "")
            rpc_user = os.getenv("MONERO_RPC_USER", "")
            rpc_pass = os.getenv("MONERO_RPC_PASSWORD", "")

            if rpc_url:
                now_utc = datetime.now(pytz.utc)
                transfers = await check_xmr_transfers_rpc(rpc_url, min_height=0, rpc_user=rpc_user, rpc_password=rpc_pass)
                pending_invoices = await xmr_payments_col.find({
                    "status": "pending",
                    "is_claimed": False,
                    "expires_at": {"$gt": now_utc}
                }).to_list(100)

                for inv in pending_invoices:
                    inv_addr = inv.get("address")
                    inv_xmr = inv.get("xmr_amount", 0.0)

                    for transfer in transfers:
                        tx_addr = transfer.get("address")
                        tx_amount = transfer.get("amount", 0) / 1e12
                        txid = transfer.get("txid")

                        if tx_addr == inv_addr and tx_amount >= inv_xmr * 0.98:
                            res = await xmr_payments_col.update_one(
                                {"_id": inv["_id"], "is_claimed": False},
                                {"$set": {
                                    "status": "confirmed",
                                    "is_claimed": True,
                                    "txid": txid,
                                    "claimed_at": now_utc
                                }}
                            )
                            if res.modified_count > 0:
                                inv["status"] = "confirmed"
                                inv["is_claimed"] = True
                                inv["txid"] = txid
                                if inv.get("callback_url"):
                                    asyncio.create_task(trigger_webhook(
                                        inv["callback_url"],
                                        {"event": "invoice.paid", "invoice": format_invoice_doc(inv)}
                                    ))
                            break
        except Exception as e:
            logger.error(f"Error in XMR invoice background scanner: {e}")

        await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(scan_pending_xmr_invoices_loop())
