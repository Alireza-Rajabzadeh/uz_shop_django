from decimal import Decimal

from django.db.models import Sum


class InventoryCostService:
    # Landed-cost calculations for InventorySupply batches. All formulas use
    # the original supplied quantity; remaining_quantity is reserved for later
    # FIFO consumption and must never influence these values.

    def get_base_cost_total(self, supply):
        # Decimal(...) accepts both persisted DecimalField values and raw
        # string inputs that have not been round-tripped through the database.
        return Decimal(supply.unit_buy_price) * Decimal(supply.quantity)

    def get_extra_cost_total(self, supply):
        return supply.costs.aggregate(total=Sum("amount", default=Decimal("0")))["total"]

    def get_landed_cost_total(self, supply):
        return self.get_base_cost_total(supply) + self.get_extra_cost_total(supply)

    def get_landed_unit_cost(self, supply):
        return self.get_landed_cost_total(supply) / Decimal(supply.quantity)

    def get_cost_summary(self, supply):
        base_cost_total = self.get_base_cost_total(supply)
        extra_cost_total = self.get_extra_cost_total(supply)
        landed_cost_total = base_cost_total + extra_cost_total
        return {
            "base_cost_total": base_cost_total,
            "extra_cost_total": extra_cost_total,
            "landed_cost_total": landed_cost_total,
            "landed_unit_cost": landed_cost_total / Decimal(supply.quantity),
        }
