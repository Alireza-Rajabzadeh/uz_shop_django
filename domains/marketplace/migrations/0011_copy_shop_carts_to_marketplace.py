from django.db import migrations


def copy_shop_carts(apps, schema_editor):
    Cart = apps.get_model("cart", "Cart")
    CartItem = apps.get_model("cart", "CartItem")
    MarketplaceCart = apps.get_model("marketplace", "MarketplaceCart")
    MarketplaceCartItem = apps.get_model("marketplace", "MarketplaceCartItem")

    for cart in Cart.objects.prefetch_related("items").all():
        marketplace_cart, _created = MarketplaceCart.objects.get_or_create(
            customer_id=cart.customer_id,
            defaults={"address_info": cart.address_info},
        )
        if cart.address_info and not marketplace_cart.address_info:
            marketplace_cart.address_info = cart.address_info
            marketplace_cart.save(update_fields=["address_info"])

        existing = {
            item.variant_id: item
            for item in marketplace_cart.items.all()
        }
        for item in cart.items.all():
            target = existing.get(item.variant_id)
            if target is None:
                target = MarketplaceCartItem.objects.create(
                    cart=marketplace_cart,
                    variant_id=item.variant_id,
                    offer_id=item.offer_id,
                    quantity=item.quantity,
                )
                existing[item.variant_id] = target
                continue
            changed = []
            if item.quantity > target.quantity:
                target.quantity = item.quantity
                changed.append("quantity")
            if target.offer_id is None and item.offer_id is not None:
                target.offer_id = item.offer_id
                changed.append("offer")
            if changed:
                target.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ("cart", "0002_cartitem_offer"),
        ("marketplace", "0010_marketplacecartitem_offer"),
    ]

    operations = [
        migrations.RunPython(copy_shop_carts, migrations.RunPython.noop),
    ]
