"""
Futu/Moomoo broker service - FastAPI backend.
Runs locally to serve position data to Next.js frontend.

OpenD must be running locally before syncing. Download from:
https://openapi.futunn.com

Environment variables:
  FUTU_HOST — OpenD host (default: 127.0.0.1)
  FUTU_PORT — OpenD port (default: 11111)
  FUTU_TRADE_PWD — Trading password (optional)
  PORT — API server port (default: 8000)
"""
import os
import json
import httpx
from typing import List, Dict, Tuple, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime

_HKD_USD_FALLBACK = 1 / 7.78


def _fetch_hkdusd_rate() -> float:
    """Fetch live HKD/USD rate from Yahoo Finance. Falls back to 1/7.78."""
    try:
        with httpx.Client(timeout=8, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = client.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/HKDUSD=X",
                params={"interval": "1d", "range": "1d"},
            )
            resp.raise_for_status()
            data = resp.json()
            price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
            rate = float(price)
            print(f"[Futu] HKDUSD rate: {rate}")
            return rate
    except Exception as e:
        print(f"[Futu] Failed to fetch HKDUSD rate ({e}), using fallback {_HKD_USD_FALLBACK:.4f}")
        return _HKD_USD_FALLBACK


def _parse_futu_code(code: str) -> Tuple[str, str]:
    """
    Convert Futu code to (symbol, asset_type).
      HK.00700 → ('700.HK', 'STOCK')
      US.AAPL  → ('AAPL',   'STOCK')
    """
    parts = code.split(".", 1)
    if len(parts) != 2:
        return code, "STOCK"

    market, ticker = parts
    if market == "HK":
        stripped = ticker.lstrip("0") or ticker
        return f"{stripped}.HK", "STOCK"
    elif market == "US":
        return ticker, "STOCK"
    else:
        return f"{ticker}.{market}", "STOCK"


def _fetch_account_balance(host: str, port: int, trade_pwd: str = "") -> Optional[Dict]:
    """
    Fetch account balance from Futu OpenD.
    Returns balance in USD for US stocks account.
    """
    try:
        import futu
    except ImportError:
        raise ImportError("futu-api not installed. Run: pip install futu-api")

    # Use US market to get USD account
    ctx = futu.OpenSecTradeContext(filter_trdmarket=futu.TrdMarket.US, host=host, port=port)
    try:
        if trade_pwd:
            ret_unlock, _ = ctx.unlock_trade(trade_pwd)
            if ret_unlock != futu.RET_OK:
                raise ValueError("unlock_trade failed — check your trading password")

        ret_acc, acc_list = ctx.get_acc_list()
        if ret_acc != futu.RET_OK:
            raise ValueError(f"get_acc_list failed: {acc_list}")

        # Find REAL + ACTIVE US account
        active_us_acc_ids = [
            int(row["acc_id"])
            for _, row in acc_list.iterrows()
            if str(row.get("trd_env", "")).upper() == "REAL"
            and str(row.get("acc_status", "")).upper() == "ACTIVE"
            and row.get("acc_type") in [2, "2"]  # US account type
        ]

        # If no US account, try first active account
        if not active_us_acc_ids:
            active_us_acc_ids = [
                int(row["acc_id"])
                for _, row in acc_list.iterrows()
                if str(row.get("trd_env", "")).upper() == "REAL"
                and str(row.get("acc_status", "")).upper() == "ACTIVE"
            ]

        print(f"[Futu] Looking for account balance, acc_ids: {active_us_acc_ids}")

        if not active_us_acc_ids:
            raise ValueError("No REAL+ACTIVE accounts found")

        # Try to get USD balance from first account
        for acc_id in active_us_acc_ids:
            ret, data = ctx.accinfo_query(
                trd_env=futu.TrdEnv.REAL,
                acc_id=acc_id,
                currency=futu.Currency.USD,
                refresh_cache=True,
            )
            print(f"[Futu] acc_id={acc_id} accinfo_query ret={ret}")
            if ret == futu.RET_OK and not data.empty:
                row = data.iloc[0]
                return {
                    "currency": "USD",
                    "cash": float(row.get("cash", 0) or 0),
                    "market_value": float(row.get("market_value", 0) or 0),
                    "total_assets": float(row.get("total_assets", 0) or 0),
                    "buying_power": float(row.get("buying_power", 0) or 0),
                    "withdrawable": float(row.get("withdrawable", 0) or 0),
                }

        return None
    finally:
        ctx.close()


# Pydantic models
class Position(BaseModel):
    symbol: str
    name: str
    quantity: float
    cost_price: Optional[float] = None
    current_price: Optional[float] = None
    asset_type: str = "STOCK"


class SyncResponse(BaseModel):
    success: bool
    positions: List[Position]
    message: str
    timestamp: str


class AccountBalance(BaseModel):
    currency: str
    cash: float
    market_value: float
    total_assets: float
    buying_power: float
    withdrawable: float


class BalanceResponse(BaseModel):
    success: bool
    account_balance: Optional[AccountBalance]
    message: str
    timestamp: str


# FastAPI app
app = FastAPI(title="Futu Broker API", version="1.0.0")


def _fetch_positions(host: str, port: int, trade_pwd: str = "") -> List[Dict]:
    """
    Fetch all open positions from OpenD via OpenSecTradeContext (supports HK + US in one call).
    Only queries REAL + ACTIVE accounts.
    Returns list of position dicts.
    """
    try:
        import futu
    except ImportError:
        raise ImportError("futu-api not installed. Run: pip install futu-api")

    # Try both HK and US markets to get all positions
    all_positions = []
    
    for market in [futu.TrdMarket.HK, futu.TrdMarket.US]:
        print(f"[Futu] Trying market: {market}")
        ctx = futu.OpenSecTradeContext(filter_trdmarket=market, host=host, port=port)
        try:
            if trade_pwd:
                ret_unlock, _ = ctx.unlock_trade(trade_pwd)
                if ret_unlock != futu.RET_OK:
                    raise ValueError("unlock_trade failed — check your trading password")

            ret_acc, acc_list = ctx.get_acc_list()
            if ret_acc != futu.RET_OK:
                print(f"[Futu] get_acc_list failed for {market}: {acc_list}")
                continue
            print(f"[Futu] {market} acc_list: {acc_list.to_dict()}")

            # Only use REAL + ACTIVE accounts
            active_acc_ids = [
                int(row["acc_id"])
                for _, row in acc_list.iterrows()
                if str(row.get("trd_env", "")).upper() == "REAL"
                and str(row.get("acc_status", "")).upper() == "ACTIVE"
            ]
            print(f"[Futu] {market} REAL+ACTIVE acc_ids: {active_acc_ids}")

            if not active_acc_ids:
                continue

            for acc_id in active_acc_ids:
                ret, data = ctx.position_list_query(
                    trd_env=futu.TrdEnv.REAL,
                    acc_id=acc_id,
                    refresh_cache=True,
                )
                print(f"[Futu] acc_id={acc_id} positions ret={ret}, rows={len(data) if ret == futu.RET_OK else 'ERR'}")
                if ret != futu.RET_OK or data.empty:
                    continue
                for _, row in data.iterrows():
                    qty = float(row.get("qty", 0))
                    if qty <= 0:
                        continue
                    code = str(row.get("code", ""))
                    symbol, asset_type = _parse_futu_code(code)
                    cost_price = float(row.get("cost_price", 0) or 0)
                    nominal_price = float(row.get("nominal_price", 0) or 0)
                    print(f"[Futu] Position found: {symbol} qty={qty}")
                    all_positions.append({
                        "symbol": symbol,
                        "name": str(row.get("stock_name", symbol)),
                        "quantity": qty,
                        "cost_price": cost_price if cost_price > 0 else None,
                        "current_price": nominal_price if nominal_price > 0 else None,
                        "asset_type": asset_type,
                    })
        finally:
            ctx.close()
    
    return all_positions


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/positions", response_model=SyncResponse)
def get_positions():
    """
    Get all stock/ETF positions from Futu/Moomoo.
    Converts HKD prices to USD.
    """
    # Get config from environment
    host = os.getenv("FUTU_HOST", "127.0.0.1")
    port = int(os.getenv("FUTU_PORT", "11111"))
    trade_pwd = os.getenv("FUTU_TRADE_PWD", "")

    try:
        assets = _fetch_positions(host, port, trade_pwd)
        
        # Convert HKD-priced holdings to USD
        if any(a["symbol"].endswith(".HK") for a in assets):
            hkdusd = _fetch_hkdusd_rate()
            for a in assets:
                if a["symbol"].endswith(".HK"):
                    if a["current_price"] is not None:
                        a["current_price"] = a["current_price"] * hkdusd
                    if a["cost_price"] is not None:
                        a["cost_price"] = a["cost_price"] * hkdusd

        positions = [Position(**a) for a in assets]
        
        return SyncResponse(
            success=True,
            positions=positions,
            message=f"Synced {len(positions)} positions",
            timestamp=datetime.utcnow().isoformat(),
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to OpenD at {host}:{port}. Make sure OpenD is running. Error: {e}"
        )


@app.get("/balance", response_model=BalanceResponse)
def get_account_balance():
    """
    Get account balance in USD from Futu/Moomoo US account.
    """
    # Get config from environment
    host = os.getenv("FUTU_HOST", "127.0.0.1")
    port = int(os.getenv("FUTU_PORT", "11111"))
    trade_pwd = os.getenv("FUTU_TRADE_PWD", "")

    try:
        balance = _fetch_account_balance(host, port, trade_pwd)
        
        if balance:
            return BalanceResponse(
                success=True,
                account_balance=AccountBalance(**balance),
                message=f"Account balance fetched",
                timestamp=datetime.utcnow().isoformat(),
            )
        else:
            return BalanceResponse(
                success=False,
                account_balance=None,
                message="No account balance found",
                timestamp=datetime.utcnow().isoformat(),
            )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to OpenD at {host}:{port}. Make sure OpenD is running. Error: {e}"
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
