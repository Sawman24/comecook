import re
import unicodedata

# 1. Numerical & Dogwhistle hate tropes (checked across raw, normalized, and punctuation-stripped strings)
DOGWHISTLE_PATTERNS = [
    r'13[\s%/_=\-:*~]*50',           # 13%=50%, 13% = 50%, 13=50, 13/50, 13-50, 1350, 13:50, 13% 50%
    r'\b1350\b',
    r'14[\s%/_=\-:*~]*88',           # 1488, 14/88, 14-88, 14 88, 14_88
    r'\b1488\b',
    r'\b14[\s_\-\.]*words\b',
    r'\bfourteen[\s_\-\.]*words\b',
    r'\b88[\s_\-\.]*prez\b',
    r'\bheil[\s_\-\.]*88\b',
    r'\b88[\s_\-\.]*heil\b',
]

# 2. Zero-tolerance hate speech, slurs & severe vulgarities (checked anywhere in text & stripped strings)
SEVERE_SLURS_AND_HATE_SPEECH = [
    # Racial, ethnic, religious & identity slurs
    "nigger", "nigga", "nigg", "n1gger", "n1gga", "negro", "negroes",
    "faggot", "fag", "fagg", "f@g", "f@ggot", "f1g",
    "kike", "k1ke", "kyke",
    "chink", "ch1nk", "gook", "g00k", "zipperhead",
    "spic", "sp1c", "wetback", "beaner",
    "tranny", "trann1e", "shemale",
    "retard", "r3tard", "tard",
    "cunt", "c*nt", "c0nt",
    "whore", "slut", "twat",
    "kill yourself", "kys", "hang yourself"
]

# 3. Extremist, supremacist, slavery & hate ideology terms
HATE_AND_SUPREMACIST_TERMS = [
    # Slavery, subjugation & racial terror
    "slave", "slaves", "slavery", "enslave", "enslaved", "enslaves", "enslaving", "enslavement",
    "slavemaster", "slave master", "plantation master", "chattel",
    "lynch", "lynching", "lynchings", "lynched", "lyncher",

    # Extremist groups, neo-nazi & supremacist symbols/figures
    "kkk", "ku klux klan", "ku klux", "klansman", "klansmen", "klan",
    "nazi", "nazis", "nazism", "neo-nazi", "neo nazi", "neonazi",
    "swastika", "swastikas", "hakenkreuz",
    "hitler", "adolf hitler", "adolf", "third reich", "3rd reich",
    "zyklon", "zyklon b",
    "white power", "white supremacy", "white supremacist", "white supremacists",
    "aryan", "aryans", "master race", "blood and soil",
    "sieg heil", "heil hitler",
    "untermensch", "untermenschen", "subhuman", "subhumans",
    "gas chamber", "gas chambers", "gas the", "race war", "genocide", "ethnic cleansing"
]

# 4. Strong profanities that should never appear even inside compound usernames/words
SUBSTRING_PROFANITIES = [
    "fuck", "bitch", "cunt", "motherfuck", "dickhead", "asshole",
    "bullshit", "cocksuck", "pussy", "dildo", "blowjob", "handjob",
    "cumshot", "deepthroat"
]

# 5. Word stems and bounded profanities & prohibited stems
PROFANITY_WORD_STEMS = [
    r'\bf[uv]ck[a-z]*\b',
    r'\bsh1t[a-z]*\b',
    r'\bshit[a-z]*\b',
    r'\bbitch[a-z]*\b',
    r'\bb1tch[a-z]*\b',
    r'\basshole[a-z]*\b',
    r'\bdumbass[a-z]*\b',
    r'\bjackass[a-z]*\b',
    r'\bfatass[a-z]*\b',
    r'\bdick(s|head|heads)?\b',
    r'\bcock(s|sucker|head)?\b',
    r'\bpuss(y|ies)?\b',
    r'\bbastard[a-z]*\b',
    r'\bdildo[a-z]*\b',
    r'\bpenis[a-z]*\b',
    r'\bvagina[a-z]*\b',
    r'\bclit[a-z]*\b',
    r'\bporn[a-z]*\b',
    r'\bmasturbat[a-z]*\b',
    r'\bjizz[a-z]*\b',
    r'\bcum[a-z]*\b',
    r'\bboobs?\b',
    r'\btits?\b',
    r'\btitties\b',
    r'\bpedophile[a-z]*\b',
    r'\bpedo\b',
    r'\bslaves?\b',
    r'\bslavery\b',
    r'\benslave[a-z]*\b',
    r'\bslavemaster[a-z]*\b',
    r'\blynch(ing|ings|ed|er)?\b',
    r'\bkkk\b',
    r'\bklan\b',
    r'\bklansman\b',
    r'\bhitler\b',
    r'\bnazi[a-z]*\b',
    r'\bswastika[a-z]*\b'
]

# Leetspeak translation table for normalization
LEET_MAP = {
    '@': 'a', '4': 'a', '/\\': 'a', '^': 'a',
    '8': 'b', '|3': 'b',
    '(': 'c', '<': 'c', '[': 'c', '{': 'c',
    '3': 'e', '€': 'e',
    '9': 'g', '6': 'g',
    '1': 'i', '!': 'i', '|': 'i',
    '0': 'o',
    '$': 's', '5': 's',
    '7': 't', '+': 't',
    '\\/': 'v', '\\/\\/': 'w',
    '2': 'z'
}

def normalize_text(text: str) -> str:
    """Normalize text by decoding unicode homoglyphs, removing accents, and lowercasing."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    return normalized.lower()

def convert_leetspeak(text: str) -> str:
    """Convert common leetspeak characters to standard alphabet."""
    text_lower = text.lower()
    res = []
    i = 0
    while i < len(text_lower):
        matched = False
        if i + 1 < len(text_lower):
            two_chars = text_lower[i:i+2]
            if two_chars in LEET_MAP:
                res.append(LEET_MAP[two_chars])
                i += 2
                matched = True
        if not matched:
            char = text_lower[i]
            res.append(LEET_MAP.get(char, char))
            i += 1
    return "".join(res)

def collapse_repeated_chars(text: str) -> str:
    """Reduce 3 or more repeated characters to a single character (e.g. fuuuuck -> fuck)."""
    return re.sub(r'(.)\1{2,}', r'\1', text)

def contains_profanity(text: str) -> tuple[bool, str | None]:
    """
    Comprehensive profanity, slur, hate-speech, and hate-dogwhistle check.
    Returns (True, matching_term) if prohibited language is found, otherwise (False, None).
    """
    if not text or not str(text).strip():
        return (False, None)

    raw_str = str(text)
    raw_lower = raw_str.lower()
    norm = normalize_text(raw_str)

    # 1. Check Dogwhistles & Numerical Hate Tropes (checked on raw, norm, and stripped versions)
    for pattern in DOGWHISTLE_PATTERNS:
        if re.search(pattern, raw_str, re.IGNORECASE) or re.search(pattern, norm, re.IGNORECASE):
            return (True, pattern)

    # Normalization and token-spaced variants
    leet = convert_leetspeak(norm)
    leet_collapsed = collapse_repeated_chars(leet)

    spaced_raw = re.sub(r'[^a-zA-Z0-9]', ' ', raw_str)
    spaced_norm = re.sub(r'[^a-z0-9]', ' ', norm)
    spaced_leet = re.sub(r'[^a-z0-9]', ' ', leet)

    # Stripped alphabetic & alphanumeric representations
    condensed_alpha = re.sub(r'[^a-z]', '', leet)
    condensed_alpha_collapsed = re.sub(r'[^a-z]', '', leet_collapsed)
    condensed_alphanumeric = re.sub(r'[^a-z0-9]', '', leet)
    condensed_alphanumeric_collapsed = re.sub(r'[^a-z0-9]', '', leet_collapsed)

    # 2. Check Severe Slurs & Hate Speech (anywhere in raw, normalized, leet, or stripped)
    for slur in SEVERE_SLURS_AND_HATE_SPEECH:
        clean_slur = re.sub(r'[^a-z0-9]', '', slur)
        if (slur in raw_lower or slur in norm or slur in leet or slur in leet_collapsed or
            slur in spaced_raw.lower() or slur in spaced_norm or slur in spaced_leet):
            return (True, slur)
        if clean_slur in condensed_alphanumeric or clean_slur in condensed_alphanumeric_collapsed:
            return (True, slur)

    # 3. Check Extremist, Supremacist & Slavery Terms
    # Unconditional substring matches for unequivocal hate terms & symbols
    STRICT_HATE_SUBSTRINGS = ["kkk", "nazi", "hitler", "swastika", "slave", "slavery", "lynch", "whitepower", "siegheil", "klan"]
    for sub in STRICT_HATE_SUBSTRINGS:
        if sub in condensed_alpha or sub in condensed_alpha_collapsed:
            return (True, sub)

    for term in HATE_AND_SUPREMACIST_TERMS:
        clean_term = re.sub(r'[^a-z0-9]', '', term)
        term_pattern = r'\b' + re.escape(term) + r'[a-z]*\b'
        if (re.search(term_pattern, raw_lower) or
            re.search(term_pattern, norm) or
            re.search(term_pattern, leet) or
            re.search(term_pattern, leet_collapsed) or
            re.search(term_pattern, spaced_raw.lower()) or
            re.search(term_pattern, spaced_norm) or
            re.search(term_pattern, spaced_leet)):
            return (True, term)
        if condensed_alpha == clean_term or condensed_alphanumeric == clean_term:
            return (True, term)
        if clean_term in condensed_alpha and len(clean_term) >= 4:
            return (True, term)

    # 4. Check Substring Profanities in stripped/condensed string (e.g., f_u_c_k_chef, bad_b1tch)
    for bad in SUBSTRING_PROFANITIES:
        if bad in condensed_alphanumeric or bad in condensed_alphanumeric_collapsed:
            return (True, bad)

    # 5. Check Word Stems & Regex Patterns across leet and token-spaced forms
    for pattern in PROFANITY_WORD_STEMS:
        if (re.search(pattern, leet, re.IGNORECASE) or
            re.search(pattern, leet_collapsed, re.IGNORECASE) or
            re.search(pattern, norm, re.IGNORECASE) or
            re.search(pattern, spaced_norm, re.IGNORECASE) or
            re.search(pattern, spaced_leet, re.IGNORECASE) or
            re.search(pattern, spaced_raw, re.IGNORECASE)):
            return (True, pattern)

    # 6. Check Spaced-Out / Delimited Variations (e.g. "f u c k", "s h i t", "s l a v e", "k k k")
    all_spaced_targets = SUBSTRING_PROFANITIES + ["slave", "slavery", "kkk", "nazi", "hitler", "lynch"]
    for bad in all_spaced_targets:
        spaced_pattern = r'\b' + r'[\s\.\-_*~=+/]*'.join(list(bad)) + r'\b'
        if (re.search(spaced_pattern, norm, re.IGNORECASE) or
            re.search(spaced_pattern, raw_lower, re.IGNORECASE) or
            re.search(spaced_pattern, leet, re.IGNORECASE)):
            return (True, bad)

    return (False, None)

def validate_clean_content(text: str, field_name: str = "Content") -> tuple[bool, str | None]:
    """
    Helper to validate user input and return a human-readable error message if blocked.
    """
    has_profanity, term = contains_profanity(text)
    if has_profanity:
        return (
            False,
            f"{field_name} contains prohibited or inappropriate language. Cooked is a welcoming, family-friendly culinary community."
        )
    return (True, None)

def censor_text(text: str) -> str:
    """
    Replace profane words with asterisks while preserving non-profane parts.
    """
    if not text:
        return ""
    result = text
    for bad in SUBSTRING_PROFANITIES + SEVERE_SLURS_AND_HATE_SPEECH + HATE_AND_SUPREMACIST_TERMS:
        pattern = re.compile(r'\b' + re.escape(bad) + r'[a-z]*\b', re.IGNORECASE)
        result = pattern.sub("*" * len(bad), result)
    return result
