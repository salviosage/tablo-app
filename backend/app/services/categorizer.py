"""
Category inference — maps merchant descriptors to expense categories.
"""

from app.models.normalized import ExpenseCategory


# (pattern, category) — checked in order, first match wins
CATEGORY_RULES: list[tuple[str, ExpenseCategory]] = [
    # Software
    ("adobe", ExpenseCategory.SOFTWARE),
    ("canva", ExpenseCategory.SOFTWARE),
    ("google *workspace", ExpenseCategory.SOFTWARE),
    ("shopify", ExpenseCategory.SOFTWARE),
    ("chatgpt", ExpenseCategory.SOFTWARE),
    ("openai", ExpenseCategory.SOFTWARE),
    ("figma", ExpenseCategory.SOFTWARE),
    ("slack", ExpenseCategory.SOFTWARE),
    ("zoom", ExpenseCategory.SOFTWARE),
    ("notion", ExpenseCategory.SOFTWARE),

    # Hosting & Domains
    ("namecheap", ExpenseCategory.HOSTING),
    ("godaddy", ExpenseCategory.HOSTING),
    ("cloudflare", ExpenseCategory.HOSTING),
    ("aws", ExpenseCategory.HOSTING),
    ("digitalocean", ExpenseCategory.HOSTING),
    ("vercel", ExpenseCategory.HOSTING),
    ("heroku", ExpenseCategory.HOSTING),

    # Personal (non-deductible)
    ("netflix", ExpenseCategory.PERSONAL),
    ("petco", ExpenseCategory.PERSONAL),
    ("spotify", ExpenseCategory.PERSONAL),
    ("disney+", ExpenseCategory.PERSONAL),

    # Office supplies
    ("amazon", ExpenseCategory.OFFICE_SUPPLIES),
    ("staples", ExpenseCategory.OFFICE_SUPPLIES),
    ("bureau en gros", ExpenseCategory.OFFICE_SUPPLIES),
    ("jean coutu", ExpenseCategory.OFFICE_SUPPLIES),
    ("art supply", ExpenseCategory.OFFICE_SUPPLIES),

    # Shipping
    ("postes canada", ExpenseCategory.SHIPPING),
    ("canada post", ExpenseCategory.SHIPPING),
    ("fedex", ExpenseCategory.SHIPPING),
    ("ups", ExpenseCategory.SHIPPING),
    ("purolator", ExpenseCategory.SHIPPING),

    # Transport
    ("waymo", ExpenseCategory.TRANSPORT),
    ("uber", ExpenseCategory.TRANSPORT),
    ("lyft", ExpenseCategory.TRANSPORT),
    ("taxi", ExpenseCategory.TRANSPORT),
    ("stationnement", ExpenseCategory.TRANSPORT),
    ("parking", ExpenseCategory.TRANSPORT),

    # Coworking
    ("coworking", ExpenseCategory.COWORKING),
    ("wework", ExpenseCategory.COWORKING),

    # Meals
    ("cafe", ExpenseCategory.MEALS),
    ("rest", ExpenseCategory.MEALS),
    ("restaurant", ExpenseCategory.MEALS),
    ("dep rest", ExpenseCategory.MEALS),
    ("tim horton", ExpenseCategory.MEALS),
    ("starbuck", ExpenseCategory.MEALS),
]


def categorize(description: str) -> ExpenseCategory:
    """Infer expense category from a merchant descriptor."""
    desc_lower = description.lower()
    for pattern, category in CATEGORY_RULES:
        if pattern in desc_lower:
            return category
    return ExpenseCategory.OTHER
