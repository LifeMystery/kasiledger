"""Keyword lists for the free rule-based parser.

The isiZulu / Sesotho / Setswana / Afrikaans words here are a starting point.
Have native speakers check and extend them before relying on them.
Add a word by putting it in the right dictionary - no other code changes needed.
"""

# Words (or word stems) that tell us what kind of entry it is.
# Exact words are checked first, then stems (substring match).
TYPE_WORDS = {
    "sale": {"sale", "sales", "sold", "sell", "sells", "selling", "verkoop", "rekisitse", "rekisa", "rekisitswe"},
    "purchase": {"buy", "bought", "purchase", "purchased", "restock", "stock", "stocked", "gekoop", "koop",
                 "rekile", "reka", "thengile", "thenga", "ngithenge"},
    "expense": {"expense", "expenses", "spent", "spend", "uitgawe", "sebenzisile"},
    "credit": {"owe", "owes", "owed", "credit", "account", "borrowed", "skuld", "kweleta", "kolota"},
    "repayment": {"repaid", "repay", "repayment", "paidback", "returned", "khokhile", "lefile", "betaal"},
}

# Stems: order matters ("thengis" = sell must be checked before "theng" = buy).
TYPE_STEMS = [
    ("thengis", "sale"),   # isiZulu: ngithengise / ngithengisile = I sold
    ("rekis", "sale"),     # Sesotho/Setswana: ke rekisitse = I sold
    ("kwelet", "credit"),  # isiZulu: uyangikweleta = owes me
    ("kolot", "credit"),   # Sesotho: o kolota = owes
    ("theng", "purchase"), # isiZulu: ngithenge = I bought
]

# Multi-word phrases are joined into one token before parsing.
PHRASES = {
    "mealie meal": "maize meal",
    "mielie meal": "maize meal",
    "maize meal": "maize meal",
    "cool drink": "cooldrink",
    "soft drink": "cooldrink",
    "car wash": "car wash",
    "paid back": "paidback",
}

# Item synonyms -> standard item name
ITEMS = {
    "bread": "bread", "breads": "bread", "loaf": "bread", "loaves": "bread", "isinkwa": "bread",
    "izinkwa": "bread", "bohobe": "bread", "borotho": "bread", "brood": "bread",
    "milk": "milk", "ubisi": "milk", "lebese": "milk", "melk": "milk",
    "amasi": "amasi", "maas": "amasi",
    "cooldrink": "cooldrink", "cooldrinks": "cooldrink", "coke": "cooldrink", "cola": "cooldrink",
    "soda": "cooldrink", "isiphuzo": "cooldrink", "iziphuzo": "cooldrink", "koeldrank": "cooldrink",
    "airtime": "airtime", "data": "data",
    "electricity": "electricity", "ugesi": "electricity", "motlakase": "electricity", "lights": "electricity",
    "sugar": "sugar", "ushukela": "sugar", "tswekere": "sugar", "swekere": "sugar", "suiker": "sugar",
    "maize meal": "maize meal", "upapa": "maize meal", "impuphu": "maize meal", "phofo": "maize meal",
    "eggs": "eggs", "egg": "eggs", "amaqanda": "eggs", "iqanda": "eggs", "mahe": "eggs", "eiers": "eggs",
    "chips": "chips", "crisps": "chips",
    "sweets": "sweets", "amaswidi": "sweets", "lekkers": "sweets",
    "paraffin": "paraffin", "uphalafini": "paraffin", "parafini": "paraffin",
    "candles": "candles", "candle": "candles", "amakhandlela": "candles", "kerese": "candles",
    "oil": "cooking oil", "amafutha": "cooking oil",
    "rice": "rice", "irayisi": "rice", "raese": "rice", "rys": "rice",
    "soap": "soap", "insipho": "soap", "sesepa": "soap", "seep": "soap",
    "polony": "polony", "kota": "kota", "vetkoek": "vetkoek", "amagwinya": "vetkoek", "magwinya": "vetkoek",
    "haircut": "haircut", "cut": "haircut", "braids": "braids", "braiding": "braids",
    "car wash": "car wash", "carwash": "car wash", "wash": "car wash",
    "rent": "rent", "transport": "transport", "taxi": "transport",
}

# Items that are services or digital - no physical stock to check.
NON_STOCK_ITEMS = {"airtime", "data", "electricity", "haircut", "braids", "car wash", "rent", "transport", "kota"}

# Number words
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "dozen": 12, "twenty": 20,
    "een": 1, "twee": 2, "drie": 3, "vier": 4, "vyf": 5,
    "nngwe": 1, "pedi": 2, "tharo": 3, "nne": 4, "hlano": 5, "leshome": 10,
    "kunye": 1, "isithupha": 6, "ishumi": 10,
}
# isiZulu numbers take noun-class prefixes (ezintathu, ezimbili, amathathu) so match the endings.
NUMBER_STEMS = [("ntathu", 3), ("thathu", 3), ("mbili", 2), ("bili", 2), ("hlanu", 5), ("zine", 4)]

# Words that split one entry into several items
SEPARATORS = {",", ";", "and", "ne", "na", "le", "plus", "&", "+", "en"}

# Words after which a number is a total, not a quantity
TOTAL_MARKERS = {"for", "total", "=", "kuyi", "yi", "ka", "vir", "totaal"}
# Words after which a number is a price per item
EACH_MARKERS = {"@", "at", "each", "per"}

STOPWORDS = {
    "i", "a", "the", "of", "to", "my", "me", "items", "item", "today", "x", "rand", "r", "from", "by", "with",
    "namhlanje", "kajeno", "ke", "ngi", "o", "u", "uya", "uyangi", "for", "total", "each", "at", "per", "is",
    "has", "have", "on", "in", "worth", "of", "some", "ek", "het", "it", "was", "just", "please", "pls",
    "customer", "client", "paid", "money", "cash", "kuyi", "yi", "ka", "vir",
}
