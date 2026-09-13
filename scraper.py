import json
import re
import requests
from bs4 import BeautifulSoup
from recipe_scrapers import scrape_html, WebsiteNotImplementedError, NoSchemaFoundInWildMode

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1"
}

def parse_ingredient_line(line: str) -> dict:
    """Parse raw ingredient line into structured amount, unit, and name."""
    clean = line.strip()
    if not clean:
        return {"name": "", "amount": "", "unit": "", "category": "Pantry"}

    # Clean leading bullets, dashes, checkboxes, or numbered list prefixes like "1." or "1)"
    clean = re.sub(r"^(?:[\*\-•▪▫\+]+|\d+[\.\)])\s*", "", clean)

    # Match amount at start (numbers, mixed fractions, unicode fractions, ranges)
    amount_match = re.match(
        r"^((?:\d+\s+)?\d+/\d+|\d+(?:\.\d+)?|[\u00BC-\u00BE\u2150-\u215E]+)"
        r"(?:\s*-\s*(?:(?:\d+\s+)?\d+/\d+|\d+(?:\.\d+)?|[\u00BC-\u00BE\u2150-\u215E]+))?\s*",
        clean
    )
    amount = ""
    rest = clean
    if amount_match and amount_match.group(0).strip():
        amount = amount_match.group(0).strip()
        rest = clean[amount_match.end():].strip()

    # Match common culinary units
    unit = ""
    unit_match = re.match(
        r"^(cups?|tbsp?|tablespoons?|tsp?|teaspoons?|grams?|g|kg|kilograms?|lbs?|pounds?|oz|ounces?|ml|l|liters?|pinches?|pinch|cloves?|slices?|cans?|heads?|bunch|bunches|sprigs?|stalks?|pkg|packages?|medium|large|small)\b\s*",
        rest,
        re.IGNORECASE
    )
    if unit_match:
        unit = unit_match.group(1).strip()
        rest = rest[unit_match.end():].strip()

    # Strip optional "of " prefix (e.g. "cups of flour")
    rest = re.sub(r"^of\s+", "", rest, flags=re.IGNORECASE).strip()
    name = rest if rest else clean

    return {
        "name": name,
        "amount": amount,
        "unit": unit,
        "category": categorize_ingredient(name)
    }

def categorize_ingredient(name: str) -> str:
    """Assign default grocery/pantry category based on ingredient name."""
    name_lower = name.lower()
    if any(k in name_lower for k in ["onion", "garlic", "tomato", "lemon", "lime", "herb", "basil", "parsley", "rosemary", "thyme", "potato", "carrot", "celery", "spinach", "lettuce", "pepper", "avocado", "apple", "banana", "berry", "mushroom", "cilantro", "ginger"]):
        return "Produce"
    if any(k in name_lower for k in ["milk", "butter", "cream", "cheese", "parmesan", "pecorino", "yogurt", "cheddar", "mozzarella", "egg"]):
        return "Dairy"
    if any(k in name_lower for k in ["beef", "chicken", "pork", "steak", "turkey", "bacon", "salmon", "shrimp", "fish", "lamb", "sausage", "veal"]):
        return "Meat"
    if any(k in name_lower for k in ["salt", "black pepper", "paprika", "cumin", "oregano", "cinnamon", "nutmeg", "chili powder", "cayenne", "turmeric", "coriander", "bay leaf"]):
        return "Spices"
    if any(k in name_lower for k in ["flour", "yeast", "sugar", "baking powder", "baking soda", "cocoa", "vanilla"]):
        return "Bakery"
    return "Pantry"

def find_recipe_in_json_ld(data):
    """Recursively search for @type Recipe in JSON-LD objects or graphs."""
    if isinstance(data, list):
        for item in data:
            found = find_recipe_in_json_ld(item)
            if found:
                return found
    elif isinstance(data, dict):
        typ = data.get("@type", "")
        if typ == "Recipe" or (isinstance(typ, list) and "Recipe" in typ):
            return data
        if "@graph" in data and isinstance(data["@graph"], list):
            for item in data["@graph"]:
                found = find_recipe_in_json_ld(item)
                if found:
                    return found
    return None

def fallback_json_ld_scrape(url: str, html: str) -> dict:
    """Multi-tiered fallback parser: JSON-LD -> Microdata -> CMS classes -> OpenGraph."""
    soup = BeautifulSoup(html, "html.parser")
    json_ld_scripts = soup.find_all("script", type="application/ld+json")

    recipe_data = None
    for script in json_ld_scripts:
        try:
            if not script.string:
                continue
            data = json.loads(script.string)
            recipe_data = find_recipe_in_json_ld(data)
            if recipe_data:
                break
        except Exception:
            continue

    if recipe_data:
        title = recipe_data.get("name", "")
        description = recipe_data.get("description", "")
        image = recipe_data.get("image")
        image_url = ""
        if isinstance(image, str):
            image_url = image
        elif isinstance(image, list) and image:
            image_url = image[0] if isinstance(image[0], str) else image[0].get("url", "")
        elif isinstance(image, dict):
            image_url = image.get("url", "")

        raw_ingredients = recipe_data.get("recipeIngredient", [])
        ingredients = [parse_ingredient_line(ing) for ing in raw_ingredients if ing]

        raw_instructions = recipe_data.get("recipeInstructions", [])
        steps = []
        step_num = 1
        if isinstance(raw_instructions, str):
            for line in raw_instructions.split("\n"):
                if line.strip():
                    steps.append({"step_number": step_num, "instruction": line.strip()})
                    step_num += 1
        elif isinstance(raw_instructions, list):
            for item in raw_instructions:
                if isinstance(item, str) and item.strip():
                    steps.append({"step_number": step_num, "instruction": item.strip()})
                    step_num += 1
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("name") or ""
                    if text.strip():
                        steps.append({"step_number": step_num, "instruction": text.strip()})
                        step_num += 1

        yield_val = recipe_data.get("recipeYield", "4")
        servings = 4
        if isinstance(yield_val, int):
            servings = yield_val
        elif isinstance(yield_val, str):
            match = re.search(r"\d+", yield_val)
            if match:
                servings = int(match.group(0))

        if title and (ingredients or steps):
            return {
                "title": str(title).strip(),
                "description": str(description).strip(),
                "prep_time_min": 15,
                "cook_time_min": 25,
                "servings": servings,
                "difficulty": "Medium",
                "cuisine": recipe_data.get("recipeCuisine", "Global") if isinstance(recipe_data.get("recipeCuisine"), str) else "Global",
                "tags": ["Imported", "WebRecipe"],
                "ingredients": ingredients or [{"name": "Check original recipe", "amount": "", "unit": "", "category": "Pantry"}],
                "steps": steps or [{"step_number": 1, "instruction": "Follow original instructions on site."}],
                "image_url": image_url,
                "source_url": url
            }

    # Tier 2: Microdata & CMS Class Selectors (WPRM, Tasty, Mediavine)
    title = ""
    title_el = (
        soup.find(class_=re.compile(r"wprm-recipe-name|tasty-recipes-title|recipe-title|entry-title", re.I)) or
        soup.find("h1")
    )
    if title_el:
        title = title_el.get_text(strip=True)

    # Ingredients extraction
    ingredients = []
    ing_els = soup.find_all(class_=re.compile(r"wprm-recipe-ingredient|tasty-recipes-ingredients|recipe-ingredient|ingredient", re.I))
    if not ing_els:
        # Look inside ul/ol with ingredient in id or class
        ing_container = soup.find(["ul", "ol", "div"], class_=re.compile(r"ingredient", re.I))
        if ing_container:
            ing_els = ing_container.find_all("li")

    for el in ing_els:
        text = el.get_text(" ", strip=True)
        if text and len(text) > 2:
            ingredients.append(parse_ingredient_line(text))

    # Instructions extraction
    steps = []
    step_els = soup.find_all(class_=re.compile(r"wprm-recipe-instruction|tasty-recipes-instructions|recipe-instruction|instruction|direction", re.I))
    if not step_els:
        step_container = soup.find(["ul", "ol", "div"], class_=re.compile(r"instruction|direction|method", re.I))
        if step_container:
            step_els = step_container.find_all("li")

    for idx, el in enumerate(step_els, 1):
        text = el.get_text(" ", strip=True)
        if text and len(text) > 3:
            steps.append({"step_number": idx, "instruction": text})

    # Image
    og_img = soup.find("meta", property="og:image")
    image_url = og_img["content"] if og_img else ""

    og_desc = soup.find("meta", property="og:description")
    description = og_desc["content"] if og_desc else ""

    if not title:
        og_title = soup.find("meta", property="og:title")
        title = og_title["content"] if og_title else (soup.title.get_text(strip=True) if soup.title else "Imported Recipe")

    return {
        "title": title.strip(),
        "description": description.strip(),
        "prep_time_min": 15,
        "cook_time_min": 25,
        "servings": 4,
        "difficulty": "Medium",
        "cuisine": "Global",
        "tags": ["Imported", "WebRecipe"],
        "ingredients": ingredients or [{"name": "Ingredients available on original website", "amount": "", "unit": "", "category": "Pantry"}],
        "steps": steps or [{"step_number": 1, "instruction": f"Visit {url} for full step-by-step preparation instructions."}],
        "image_url": image_url,
        "source_url": url
    }

def parse_raw_recipe_text(text: str) -> dict:
    """Parse raw pasted recipe text or pasted HTML into structured recipe format."""
    clean_input = text.strip()
    if not clean_input:
        raise ValueError("Provided text is empty")

    # If raw HTML was pasted, try the HTML/JSON-LD fallback extractor first
    if ("<html" in clean_input.lower() or 
        "<script" in clean_input.lower() or 
        "wprm-recipe" in clean_input.lower() or 
        ("class=" in clean_input.lower() and "<div" in clean_input.lower())):
        try:
            parsed_html = fallback_json_ld_scrape("", clean_input)
            if parsed_html and parsed_html.get("title") and (parsed_html.get("ingredients") or parsed_html.get("steps")):
                return parsed_html
        except Exception:
            pass

    lines = [line.strip() for line in clean_input.split("\n") if line.strip()]
    if not lines:
        raise ValueError("Provided text is empty")

    title = lines[0]
    description = ""
    ingredients = []
    steps = []

    current_mode = "desc"  # 'desc', 'ing', 'step'
    step_num = 1

    for line in lines[1:]:
        lower = line.lower()
        if any(h in lower for h in ["ingredient", "what you need", "materials"]):
            current_mode = "ing"
            continue
        elif any(h in lower for h in ["instruction", "direction", "preparation", "how to cook", "method", "steps"]):
            current_mode = "step"
            continue

        if current_mode == "desc" and not ingredients:
            if re.match(r"^[\d\s/\.,\-]+(cups?|tbsp|tsp|g|kg|oz|lbs?|cloves?|pinch)", lower):
                current_mode = "ing"
                ingredients.append(parse_ingredient_line(line))
            else:
                description += (" " + line if description else line)
        elif current_mode == "ing":
            if re.match(r"^(step\s*\d+|\d+\.|\d+\))", lower) or len(line) > 100:
                current_mode = "step"
                steps.append({"step_number": step_num, "instruction": re.sub(r"^(step\s*\d+[:\.]?|\d+[\.\)])\s*", "", line)})
                step_num += 1
            else:
                ingredients.append(parse_ingredient_line(line))
        elif current_mode == "step":
            cleaned_step = re.sub(r"^(step\s*\d+[:\.]?|\d+[\.\)])\s*", "", line)
            steps.append({"step_number": step_num, "instruction": cleaned_step})
            step_num += 1

    if not ingredients:
        ingredients = [{"name": "See recipe description", "amount": "", "unit": "", "category": "Pantry"}]
    if not steps:
        steps = [{"step_number": 1, "instruction": description or "Follow preparation notes."}]

    return {
        "title": title[:100],
        "description": description[:300],
        "prep_time_min": 15,
        "cook_time_min": 25,
        "servings": 4,
        "difficulty": "Medium",
        "cuisine": "Global",
        "tags": ["Imported", "CustomNotes"],
        "ingredients": ingredients,
        "steps": steps,
        "image_url": "",
        "source_url": ""
    }

def scrape_recipe_from_url(url_or_text: str) -> dict:
    """Scrape and normalize recipe details from URL or raw text."""
    clean_input = url_or_text.strip()

    # Check if input is raw text or pasted HTML rather than a single URL
    if "\n" in clean_input or "<" in clean_input or not (clean_input.startswith("http://") or clean_input.startswith("https://") or ("." in clean_input and "/" in clean_input and len(clean_input.split()) == 1)):
        return parse_raw_recipe_text(clean_input)

    url = clean_input
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    html_text = ""
    fetch_error = None

    # 1. First attempt: curl_cffi with Chrome TLS impersonation (bypasses Akamai/Cloudflare bot blocking)
    try:
        try:
            from curl_cffi import requests as cffi_requests
            resp = cffi_requests.get(url, impersonate="chrome124", timeout=12)
            if resp.status_code == 200:
                html_text = resp.text
            elif resp.status_code != 403 and resp.status_code != 429:
                resp.raise_for_status()
        except ImportError:
            pass
    except Exception as e:
        fetch_error = e

    # 2. Second attempt: standard requests session with modern browser headers
    if not html_text:
        try:
            session = requests.Session()
            session.headers.update(BROWSER_HEADERS)
            resp = session.get(url, timeout=12)
            resp.raise_for_status()
            html_text = resp.text
        except Exception as req_err:
            domain = re.sub(r"^https?://", "", url).split("/")[0]
            raise ValueError(
                f"Could not connect to '{domain}' (Network unreachable or request blocked). "
                f"If the site blocks automated requests or you are offline, switch to the 'Paste Recipe Text' tab to import directly!"
            ) from (fetch_error or req_err)

    # 2. Try recipe-scrapers using the pre-fetched HTML
    try:
        scraper = scrape_html(html=html_text, org_url=url, wild_mode=True)
        title = scraper.title()
        description = scraper.description() if hasattr(scraper, "description") else ""
        total_time = scraper.total_time() if hasattr(scraper, "total_time") else 30
        yields = scraper.yields() if hasattr(scraper, "yields") else "4 servings"
        image_url = scraper.image() if hasattr(scraper, "image") else ""
        raw_ingredients = scraper.ingredients()
        raw_instructions = scraper.instructions_list() if hasattr(scraper, "instructions_list") else scraper.instructions().split("\n")

        servings = 4
        if yields:
            match = re.search(r"\d+", str(yields))
            if match:
                servings = int(match.group(0))

        ingredients = [parse_ingredient_line(ing) for ing in raw_ingredients if ing.strip()]
        steps = []
        for idx, inst in enumerate(raw_instructions, 1):
            if inst.strip():
                steps.append({"step_number": idx, "instruction": inst.strip()})

        if not steps:
            steps = [{"step_number": 1, "instruction": "See original website for directions."}]

        prep_time = max(5, int(total_time * 0.4)) if total_time else 15
        cook_time = max(5, int(total_time * 0.6)) if total_time else 25

        cuisine = "Global"
        if hasattr(scraper, "cuisine") and scraper.cuisine():
            cuisine = scraper.cuisine()

        if title and (ingredients or steps):
            return {
                "title": title.strip() if title else "Scraped Recipe",
                "description": description.strip() if description else "",
                "prep_time_min": prep_time,
                "cook_time_min": cook_time,
                "servings": servings,
                "difficulty": "Medium",
                "cuisine": cuisine,
                "tags": ["Imported", "WebRecipe"],
                "ingredients": ingredients,
                "steps": steps,
                "image_url": image_url or "",
                "source_url": url
            }
    except Exception:
        pass

    # 3. Fallback to schema.org / microdata / CMS class parser
    return fallback_json_ld_scrape(url, html_text)

