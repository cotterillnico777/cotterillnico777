"""Kosten- und Ausführungsmodell. Alle Annahmen sind hier gebündelt und stressbar."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..config.schema import CostConfig


@dataclass(frozen=True)
class CostModel:
    taker_fee: float
    maker_fee: float
    slippage_bps: float
    slippage_range_frac: float
    funding_fallback_rate: float
    liquidation_fee: float

    @classmethod
    def from_config(cls, c: CostConfig) -> "CostModel":
        return cls(
            c.taker_fee, c.maker_fee, c.slippage_bps, c.slippage_range_frac,
            c.funding_fallback_rate, c.liquidation_fee,
        )

    def stressed(self, fee_mult: float = 1.0, slippage_mult: float = 1.0) -> "CostModel":
        return replace(
            self,
            taker_fee=self.taker_fee * fee_mult,
            maker_fee=self.maker_fee * fee_mult,
            slippage_bps=self.slippage_bps * slippage_mult,
            slippage_range_frac=self.slippage_range_frac * slippage_mult,
        )

    def slippage(self, price: float, high: float, low: float) -> float:
        """Preisabstand (immer >= 0), den eine Marktorder schlechter als ``price`` gefüllt wird."""
        return price * self.slippage_bps / 10_000 + max(high - low, 0.0) * self.slippage_range_frac

    def fill_price(self, reference: float, side: int, high: float, low: float) -> float:
        """Ausführungspreis einer Marktorder. side: +1 kaufen, -1 verkaufen."""
        return reference + side * self.slippage(reference, high, low)

    def fee(self, notional: float, maker: bool = False) -> float:
        return abs(notional) * (self.maker_fee if maker else self.taker_fee)
