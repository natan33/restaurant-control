GRACAS_NA_MESA_PRODUCTS = (
    ("Moqueca de Peixe - Marmita M", 30.00),
    ("Frango ao Molho - Marmita M", 25.00),
    ("Refrigerante Pepsi 1 litro", 8.00),
    ("Refrigerante Pepsi lata 350 ml", 5.00),
    ("Combo 1 - Moqueca + Pepsi 1L", 37.90),
    ("Combo 2 - Moqueca + Pepsi lata", 34.90),
    ("Combo 3 - Frango + Pepsi 1L", 33.90),
    ("Combo 4 - Frango + Pepsi lata", 29.90),
    ("Combo 5 - 2 Moquecas + Pepsi 1L", 67.70),
    ("Combo 6 - 2 Frangos + Pepsi 1L", 57.70),
)


def sync_gracas_products(organization, product_model, session):
    """Synchronize the confirmed catalog for one organization only."""
    result = {"created": [], "existing": [], "updated": []}
    for name, price in GRACAS_NA_MESA_PRODUCTS:
        product = product_model.query.filter_by(
            organization_id=organization.id, nome=name
        ).one_or_none()
        if product is None:
            session.add(product_model(
                organization_id=organization.id, nome=name, preco=price
            ))
            result["created"].append(name)
        elif round(float(product.preco), 2) != price:
            result["updated"].append((name, float(product.preco), price))
            product.preco = price
        else:
            result["existing"].append(name)
    session.commit()
    return result
