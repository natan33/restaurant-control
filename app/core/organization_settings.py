DEFAULT_SETTINGS = {
    "show_seller_type": True,
    "theme_key": "default",
    "dashboard_mode": "church",
    "show_financial_dashboard": False,
    "show_expenses": False,
    "app_display_name": "Restaurant Control",
}

def get_organization_settings(organization):
    settings = dict(DEFAULT_SETTINGS)
    settings.update(organization.settings or {})
    return settings
