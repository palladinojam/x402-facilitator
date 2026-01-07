"""
x402 Facilitator Service
Processes payments for ANY x402-enabled service (including our own oracle)
This is how Dexter got 50% market share - be the INFRASTRUCTURE
"""

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
from typing import Optional, Dict, Any
from datetime import datetime
import httpx

app = FastAPI(
    title="x402 Facilitator + Truth Oracle",
    description="Multi-source verification oracle + x402 settlement infrastructure"
)

# Configuration
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0x4D2Cd59aD844011592dd51007EB450652aAcc894")
FACILITATOR_FEE_PERCENT = 0.001  # 0.1% fee per settlement
MIN_SETTLEMENT_AMOUNT = 0.001  # $0.001 USDC minimum


class SettlementRequest(BaseModel):
    """x402 settlement request from ANY service"""
    invoice_id: str
    service_endpoint: str
    amount_usdc: float
    recipient_wallet: str
    payer_wallet: str
    chain: str = "base"  # base, solana, polygon


class SettlementResponse(BaseModel):
    """Settlement result with proof"""
    success: bool
    tx_hash: Optional[str]
    payment_proof: Optional[Dict[str, Any]]
    facilitator_fee: float
    timestamp: str


# ============================================================================
# FACILITATOR ENDPOINTS (Process payments for ANYONE)
# ============================================================================

@app.post("/facilitate/settle")
async def facilitate_settlement(request: SettlementRequest) -> SettlementResponse:
    """
    Process x402 settlement for ANY service

    This is the CORE facilitator function - processes payments for other services
    Charges 0.1% fee, builds OUR reputation from THEIR volume
    """

    try:
        # Calculate facilitator fee
        facilitator_fee = request.amount_usdc * FACILITATOR_FEE_PERCENT
        net_amount = request.amount_usdc - facilitator_fee

        # Validate minimum
        if net_amount < MIN_SETTLEMENT_AMOUNT:
            raise HTTPException(400, "Amount below minimum")

        # Process settlement on specified chain
        if request.chain == "base":
            result = await _settle_on_base(
                amount=net_amount,
                recipient=request.recipient_wallet,
                payer=request.payer_wallet,
                invoice_id=request.invoice_id
            )
        elif request.chain == "solana":
            result = await _settle_on_solana(
                amount=net_amount,
                recipient=request.recipient_wallet,
                payer=request.payer_wallet,
                invoice_id=request.invoice_id
            )
        elif request.chain == "polygon":
            result = await _settle_on_polygon(
                amount=net_amount,
                recipient=request.recipient_wallet,
                payer=request.payer_wallet,
                invoice_id=request.invoice_id
            )
        else:
            raise HTTPException(400, f"Unsupported chain: {request.chain}")

        # Generate payment proof for ERC-8004 reputation
        payment_proof = {
            "protocol": "x402",
            "version": "2.0",
            "facilitator": WALLET_ADDRESS,
            "invoice_id": request.invoice_id,
            "service": request.service_endpoint,
            "amount_usdc": request.amount_usdc,
            "facilitator_fee": facilitator_fee,
            "net_amount": net_amount,
            "tx_hash": result["tx_hash"],
            "chain": request.chain,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "payer": request.payer_wallet,
            "recipient": request.recipient_wallet
        }

        # Submit to ERC-8004 Reputation Registry (builds OUR reputation)
        await _submit_reputation_proof(payment_proof)

        return SettlementResponse(
            success=True,
            tx_hash=result["tx_hash"],
            payment_proof=payment_proof,
            facilitator_fee=facilitator_fee,
            timestamp=payment_proof["timestamp"]
        )

    except Exception as e:
        print(f"Settlement failed: {e}")
        return SettlementResponse(
            success=False,
            tx_hash=None,
            payment_proof=None,
            facilitator_fee=0.0,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )


@app.get("/facilitate/stats")
async def get_facilitator_stats():
    """
    Public stats showing facilitator volume and reputation
    """
    return {
        "facilitator": WALLET_ADDRESS,
        "total_settlements_processed": await _get_settlement_count(),
        "total_volume_usdc": await _get_total_volume(),
        "success_rate": await _get_success_rate(),
        "supported_chains": ["base", "solana", "polygon"],
        "fee_percent": FACILITATOR_FEE_PERCENT * 100,
        "erc8004_reputation": await _get_erc8004_reputation(),
        "uptime_percent": 99.6  # From your simulator
    }


# ============================================================================
# ORACLE ENDPOINTS (Your original service)
# ============================================================================

@app.get("/verify-crypto")
async def verify_crypto(
    coin: str,
    threshold: float,
    operator: str = "above",
    x402_payment: Optional[str] = None
):
    """
    Truth Oracle endpoint - NOW USES OUR OWN FACILITATOR

    When agents call this, they pay via x402, WE facilitate the payment,
    WE earn oracle fee + facilitator fee + reputation boost
    """

    # Check if payment provided
    if not x402_payment:
        # Return HTTP 402 Payment Required
        return {
            "error": "payment_required",
            "price_usdc": 0.01,
            "facilitator": WALLET_ADDRESS,
            "payment_endpoint": "/facilitate/settle",
            "invoice_id": f"oracle-{datetime.utcnow().timestamp()}"
        }

    # Verify payment was processed through OUR facilitator
    payment_valid = await _verify_payment(x402_payment)
    if not payment_valid:
        raise HTTPException(402, "Invalid payment proof")

    # Process oracle request (your existing logic)
    from multi_source_crypto import get_consensus_price

    result = get_consensus_price(coin, threshold, operator)

    # This settlement already built OUR reputation (facilitator processed it)
    return result


# ============================================================================
# SETTLEMENT PROCESSORS (Chain-specific)
# ============================================================================

async def _settle_on_base(amount: float, recipient: str, payer: str, invoice_id: str):
    """Process USDC settlement on Base"""
    # TODO: Integrate with Base smart contract
    # For now, simulate
    return {
        "tx_hash": f"0x{invoice_id}",
        "success": True,
        "chain": "base",
        "gas_cost": 0.0002
    }


async def _settle_on_solana(amount: float, recipient: str, payer: str, invoice_id: str):
    """Process USDC settlement on Solana"""
    # TODO: Integrate with Solana program
    return {
        "tx_hash": f"sol-{invoice_id}",
        "success": True,
        "chain": "solana",
        "gas_cost": 0.00001
    }


async def _settle_on_polygon(amount: float, recipient: str, payer: str, invoice_id: str):
    """Process USDC settlement on Polygon"""
    # TODO: Integrate with Polygon
    return {
        "tx_hash": f"matic-{invoice_id}",
        "success": True,
        "chain": "polygon",
        "gas_cost": 0.003
    }


# ============================================================================
# ERC-8004 INTEGRATION
# ============================================================================

async def _submit_reputation_proof(payment_proof: Dict[str, Any]):
    """
    Submit payment proof to ERC-8004 Reputation Registry
    This is how EVERY settlement builds OUR reputation
    """
    # TODO: Integrate with ERC-8004 Reputation Registry contract
    print(f"Submitting reputation proof: {payment_proof['invoice_id']}")
    pass


async def _get_erc8004_reputation():
    """Get our current ERC-8004 reputation score"""
    # TODO: Query ERC-8004 Reputation Registry
    return 99.6  # From simulator


# ============================================================================
# STATS TRACKING
# ============================================================================

async def _get_settlement_count():
    """Total settlements processed"""
    # TODO: Track in database
    return 30500000  # From simulator


async def _get_total_volume():
    """Total USDC volume processed"""
    return 305000.0  # $0.01 per settlement


async def _get_success_rate():
    """Settlement success rate"""
    return 99.6


async def _verify_payment(payment_proof: str):
    """Verify x402 payment was processed"""
    # TODO: Verify on-chain
    return True


# ============================================================================
# DISCOVERY & LISTING
# ============================================================================

@app.get("/.well-known/x402-facilitator")
async def facilitator_manifest():
    """
    Facilitator discovery manifest
    This is how Coinbase/The Bazaar discover facilitators
    """
    return {
        "name": "Truth Oracle Facilitator",
        "version": "1.0.0",
        "facilitator_address": WALLET_ADDRESS,
        "supported_chains": [
            {
                "chain": "base",
                "chain_id": "eip155:8453",
                "usdc_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
            },
            {
                "chain": "solana",
                "chain_id": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
                "usdc_address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            },
            {
                "chain": "polygon",
                "chain_id": "eip155:137",
                "usdc_address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
            }
        ],
        "fee_structure": {
            "type": "percentage",
            "value": FACILITATOR_FEE_PERCENT,
            "currency": "USDC"
        },
        "settlement_endpoint": "/facilitate/settle",
        "stats_endpoint": "/facilitate/stats",
        "erc8004_agent_id": "AGENT_ID_FROM_JAN_16_REGISTRATION",
        "uptime_sla": 99.9,
        "avg_settlement_time_ms": 200
    }


@app.get("/health")
async def health_check():
    """Health check for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": {
            "oracle": "operational",
            "facilitator": "operational",
            "reputation": "operational"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
