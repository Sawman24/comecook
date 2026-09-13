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

# 2. Zero-tolerance hate speech, slurs & severe identity slurs (checked across all normalized & homoglyph variants)
SEVERE_SLURS_AND_HATE_SPEECH = [
    # Racial, ethnic, religious & identity slurs
    "nigger", "nigga", "nigg", "n1gger", "n1gga", "n1gg", "nlgg", "nlgger", "nlgga",
    "negr", "negro", "negroes", "nigglet", "nlglet", "n1glet",
    "faggot", "fag", "fagg", "f@g", "f@ggot", "f1g", "flg", "faggots", "fagg0t",
    "kike", "k1ke", "kyke", "klke",
    "chink", "ch1nk", "chlnk", "gook", "g00k", "zipperhead",
    "spic", "sp1c", "splc", "wetback", "beaner",
    "tranny", "trann1e", "shemale",
    "retard", "r3tard", "tard", "retarded",
    "cunt", "c*nt", "c0nt", "cvnt",
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

# 4. Explicit profanities that should never appear even as substrings in usernames/words
SUBSTRING_PROFANITIES = [
    "fuck", "fuk", "fck", "bitch", "cunt", "motherfuck", "dickhead", "asshole",
    "bullshit", "cocksuck", "pussy", "dildo", "blowjob", "handjob",
    "cumshot", "deepthroat", "dick", "cock", "penis", "vagina", "clit",
    "jizz", "porno", "porn", "masturbat"
]

# 5. Whitelisted genuine culinary/everyday terms to prevent false positives
CULINARY_WHITELIST = {
    "cocktail", "cocktails", "spatchcock", "spatchcocked", "spatchcocking",
    "peacock", "cockle", "cockles", "cumin", "cucumber", "cucumbers",
    "cumquat", "cumquats", "shiitake", "shitake", "nigella", "bass",
    "cassava", "molasses", "passion", "appetite", "snicker", "snickerdoodle",
    "document", "classic", "association", "assistant", "glasses", "brass",
    "black", "big"
}

# 6. Word stems and bounded profanities & prohibited stems
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

# Comprehensive Unicode homoglyphs mapping table (Cyrillic, Greek, Math, Leetspeak, etc.)
HOMOGLYPH_MAP = {
    # Cyrillic homoglyphs
    'а': 'a', 'А': 'a', 'б': 'b', 'Б': 'b', 'в': 'b', 'В': 'b', 'г': 'g', 'Г': 'g',
    'д': 'd', 'Д': 'd', 'е': 'e', 'Е': 'e', 'ё': 'e', 'Ё': 'e', 'ж': 'zh', 'Ж': 'zh',
    'з': 'e', 'З': 'e', 'Ӡ': 'e', 'ӡ': 'e', 'э': 'e', 'Э': 'e', 'є': 'e', 'Є': 'e',
    'и': 'u', 'И': 'u', 'й': 'i', 'Й': 'i', 'і': 'i', 'І': 'i', 'ї': 'i', 'Ї': 'i',
    'к': 'k', 'К': 'k', 'л': 'l', 'Л': 'l', 'м': 'm', 'М': 'm', 'н': 'h', 'Н': 'h',
    'о': 'o', 'О': 'o', 'п': 'p', 'П': 'p', 'р': 'p', 'Р': 'p', 'с': 's', 'С': 's',
    'т': 't', 'Т': 't', 'у': 'y', 'У': 'y', 'ф': 'f', 'Ф': 'f', 'х': 'x', 'Х': 'x',
    'ц': 'c', 'Ц': 'c', 'ч': 'ch', 'Ч': 'ch', 'ш': 'sh', 'Ш': 'sh', 'щ': 'sh', 'Щ': 'sh',
    'ъ': 'b', 'Ъ': 'b', 'ы': 'bl', 'Ы': 'bl', 'ь': 'b', 'Ь': 'b', 'ю': 'yu', 'Ю': 'yu',
    'я': 'ya', 'Я': 'ya',

    # Greek homoglyphs
    'α': 'a', 'Α': 'a', 'β': 'b', 'Β': 'b', 'γ': 'g', 'Γ': 'g', 'δ': 'd', 'Δ': 'd',
    'ε': 'e', 'Ε': 'e', 'ζ': 'z', 'Ζ': 'z', 'η': 'h', 'Η': 'h', 'θ': 'o', 'Θ': 'o',
    'ι': 'i', 'Ι': 'i', 'κ': 'k', 'Κ': 'k', 'λ': 'l', 'Λ': 'l', 'μ': 'm', 'Μ': 'm',
    'ν': 'v', 'Ν': 'v', 'ξ': 'x', 'Ξ': 'x', 'ο': 'o', 'Ο': 'o', 'π': 'p', 'Π': 'p',
    'ρ': 'r', 'Ρ': 'r', 'σ': 's', 'ς': 's', 'Σ': 's', 'τ': 't', 'Τ': 't', 'υ': 'u',
    'Υ': 'u', 'φ': 'f', 'Φ': 'f', 'χ': 'x', 'Χ': 'x', 'ψ': 'ps', 'Ψ': 'ps', 'ω': 'w', 'Ω': 'w',

    # Common leetspeak & symbolic homoglyphs
    '3': 'e', '€': 'e', '£': 'e', 'ɛ': 'e',
    '1': 'i', '!': 'i', '|': 'i', '¡': 'i', '¦': 'i',
    '0': 'o', 'ø': 'o', 'Ø': 'o', 'θ': 'o', '°': 'o',
    '5': 's', '$': 's', '§': 's',
    '7': 't', '+': 't', '†': 't', '‡': 't',
    '8': 'b', 'ß': 'b',
    '4': 'a', '@': 'a', '^': 'a',
    '9': 'g', '6': 'g',
    '2': 'z',
    '¥': 'y',
    '(': 'c', '<': 'c', '[': 'c', '{': 'c',
}

def apply_homoglyphs(text: str) -> str:
    """Map foreign letters (Cyrillic, Greek), math symbols, and leetspeak to basic Latin equivalents."""
    if not text:
        return ""
    # Strip invisible/zero-width formatting
    text = re.sub(r'[\u200B-\u200D\uFEFF\u00AD\u2060]', '', text)
    res = []
    for ch in text:
        res.append(HOMOGLYPH_MAP.get(ch, ch))
    return "".join(res)

def normalize_text(text: str) -> str:
    """Normalize text by decoding unicode homoglyphs, removing accents, and lowercasing."""
    if not text:
        return ""
    homo = apply_homoglyphs(text)
    normalized = unicodedata.normalize("NFKD", homo).encode("ascii", "ignore").decode("utf-8")
    return normalized.lower()

def collapse_repeated_chars(text: str) -> str:
    """Reduce repeated characters to single character (e.g. fuuuuck -> fuck)."""
    return re.sub(r'(.)\1{2,}', r'\1', text)

def generate_variants(text: str) -> list[str]:
    """Generate all normalized, leetspeak, l-to-i swapped, and compressed variants for inspection."""
    norm = normalize_text(text)
    norm_collapsed = collapse_repeated_chars(norm)

    # Variant with lowercase 'l' swapped to 'i' (since 'l' is widely used to evade 'i' in slurs like nlgg/dlck)
    l_to_i = norm.replace('l', 'i')
    l_to_i_collapsed = collapse_repeated_chars(l_to_i)

    # Spaced versions
    spaced_norm = re.sub(r'[^a-z0-9]', ' ', norm)
    spaced_l_to_i = re.sub(r'[^a-z0-9]', ' ', l_to_i)

    # Condensed alphanumeric (spaces/punctuation completely removed)
    condensed_alpha = re.sub(r'[^a-z]', '', norm)
    condensed_alpha_collapsed = re.sub(r'[^a-z]', '', norm_collapsed)
    condensed_l_to_i = re.sub(r'[^a-z]', '', l_to_i)
    condensed_l_to_i_collapsed = re.sub(r'[^a-z]', '', l_to_i_collapsed)

    variants = [
        norm, norm_collapsed, l_to_i, l_to_i_collapsed,
        spaced_norm, spaced_l_to_i,
        condensed_alpha, condensed_alpha_collapsed,
        condensed_l_to_i, condensed_l_to_i_collapsed
    ]
    return list(dict.fromkeys(variants))

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

    # 1. Check Dogwhistles & Numerical Hate Tropes
    for pattern in DOGWHISTLE_PATTERNS:
        if re.search(pattern, raw_str, re.IGNORECASE) or re.search(pattern, norm, re.IGNORECASE):
            return (True, pattern)

    # Generate all inspection variants
    variants = generate_variants(raw_str)
    collapsed_variants = [collapse_repeated_chars(v) for v in variants]
    all_eval_strings = list(dict.fromkeys(variants + collapsed_variants))

    # 2. Check Severe Slurs & Hate Speech (ZERO TOLERANCE across any variant or substring)
    for slur in SEVERE_SLURS_AND_HATE_SPEECH:
        clean_slur = re.sub(r'[^a-z0-9]', '', slur)
        for s in all_eval_strings:
            if clean_slur in s or slur in s:
                return (True, slur)

    # 3. Check Extremist, Supremacist & Slavery Terms
    STRICT_HATE_SUBSTRINGS = ["kkk", "nazi", "hitler", "swastika", "slave", "slavery", "lynch", "whitepower", "siegheil", "klan"]
    for s in all_eval_strings:
        for sub in STRICT_HATE_SUBSTRINGS:
            if sub in s:
                return (True, sub)

    for term in HATE_AND_SUPREMACIST_TERMS:
        clean_term = re.sub(r'[^a-z0-9]', '', term)
        term_pattern = r'\b' + re.escape(term) + r'[a-z]*\b'
        for s in all_eval_strings:
            if clean_term in s and len(clean_term) >= 4:
                return (True, term)
            if re.search(term_pattern, s):
                return (True, term)

    # 4. Check Substring Profanities in stripped/condensed string (e.g. f_u_c_k_chef, bad_b1tch, dlck)
    for bad in SUBSTRING_PROFANITIES:
        for s in all_eval_strings:
            if bad in s:
                # Whitelist check for legitimate culinary words
                is_whitelisted = False
                for safe_word in CULINARY_WHITELIST:
                    if safe_word in raw_lower or safe_word in norm:
                        # If the whole match is within a safe culinary word, permit
                        if bad in safe_word:
                            is_whitelisted = True
                            break
                if not is_whitelisted:
                    return (True, bad)

    # 5. Check Word Stems & Regex Patterns across all variants
    for pattern in PROFANITY_WORD_STEMS:
        for s in all_eval_strings:
            if re.search(pattern, s, re.IGNORECASE):
                return (True, pattern)

    # 6. Check Spaced-Out / Delimited Variations (e.g. "f u c k", "s h i t", "s l a v e", "k k k")
    all_spaced_targets = SUBSTRING_PROFANITIES + ["slave", "slavery", "kkk", "nazi", "hitler", "lynch"]
    for bad in all_spaced_targets:
        spaced_pattern = r'\b' + r'[\s\.\-_*~=+/]*'.join(list(bad)) + r'\b'
        for s in all_eval_strings:
            if re.search(spaced_pattern, s, re.IGNORECASE):
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
