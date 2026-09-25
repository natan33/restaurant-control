DEFAULT_SETTINGS = {"show_seller_type": True, "theme_key": "default"}

def get_organization_settings(organization):
    settings = dict(DEFAULT_SETTINGS)
    settings.update(organization.settings or {})
    return settings
