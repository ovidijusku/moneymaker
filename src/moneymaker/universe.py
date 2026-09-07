"""The tradable crypto universe.

Sourced from Alpaca's asset list. Every pair here is spot and long-only: Alpaca
reports 0 of 36 crypto pairs as shortable or marginable, so a short is not a
setting this project can turn on. Stablecoins are excluded because advice on a
pegged asset is noise.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict


class Asset(BaseModel):
    """Display metadata plus the text handles used to tag news and posts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    name: str
    #: Matched only in uppercase, so "Trump said" never tags the TRUMP memecoin.
    tickers: tuple[str, ...] = ()
    #: Distinctive enough to match case-insensitively anywhere in a sentence.
    aliases: tuple[str, ...] = ()


def _asset(symbol: str, name: str, *aliases: str, tickers: tuple[str, ...] = ()) -> Asset:
    base = symbol.split("/")[0]
    return Asset(symbol=symbol, name=name, tickers=tickers or (base,), aliases=aliases)


ASSETS: Final[tuple[Asset, ...]] = (
    _asset("BTC/USD", "Bitcoin", "bitcoin", tickers=("BTC", "XBT")),
    _asset("ETH/USD", "Ethereum", "ethereum", "ether"),
    _asset("SOL/USD", "Solana", "solana"),
    _asset("XRP/USD", "XRP", "ripple"),
    _asset("DOGE/USD", "Dogecoin", "dogecoin"),
    _asset("ADA/USD", "Cardano", "cardano"),
    _asset("AVAX/USD", "Avalanche", "avalanche"),
    _asset("LINK/USD", "Chainlink", "chainlink"),
    _asset("LTC/USD", "Litecoin", "litecoin"),
    _asset("DOT/USD", "Polkadot", "polkadot"),
    _asset("BCH/USD", "Bitcoin Cash", "bitcoin cash"),
    _asset("UNI/USD", "Uniswap", "uniswap"),
    _asset("AAVE/USD", "Aave", "aave"),
    _asset("ARB/USD", "Arbitrum", "arbitrum"),
    _asset("POL/USD", "Polygon", "polygon", tickers=("POL", "MATIC")),
    _asset("FIL/USD", "Filecoin", "filecoin"),
    _asset("GRT/USD", "The Graph", "the graph"),
    _asset("CRV/USD", "Curve", "curve dao", "curve finance"),
    _asset("LDO/USD", "Lido", "lido"),
    _asset("SHIB/USD", "Shiba Inu", "shiba inu"),
    _asset("PEPE/USD", "Pepe"),
    _asset("BONK/USD", "Bonk"),
    _asset("WIF/USD", "dogwifhat", "dogwifhat"),
    _asset("ONDO/USD", "Ondo", "ondo finance"),
    _asset("RENDER/USD", "Render", "render network"),
    _asset("SKY/USD", "Sky", "sky protocol", "makerdao"),
    _asset("HYPE/USD", "Hyperliquid", "hyperliquid"),
    _asset("TRUMP/USD", "Official Trump", "official trump"),
    _asset("SUSHI/USD", "SushiSwap", "sushiswap"),
    _asset("XTZ/USD", "Tezos", "tezos"),
    _asset("YFI/USD", "Yearn", "yearn finance", "yearn.finance"),
    _asset("PAXG/USD", "PAX Gold", "pax gold", "paxos gold"),
)

BY_SYMBOL: Final[dict[str, Asset]] = {asset.symbol: asset for asset in ASSETS}

DEFAULT_SYMBOLS: Final[tuple[str, ...]] = tuple(asset.symbol for asset in ASSETS)

#: Pegged to the dollar; there is no move to trade.
STABLECOINS: Final[frozenset[str]] = frozenset({"USDC/USD", "USDT/USD", "USDG/USD"})


def display_name(symbol: str) -> str:
    asset = BY_SYMBOL.get(symbol)
    return asset.name if asset else symbol
