import xml.etree.ElementTree as ET
import json
import os
import urllib.request
import anthropic

FEED_URL = "https://b2bzago.com/exchange/B0AF3240-D6D6-45BA-877A-03609E6A1122/xml/feed.xml"

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def fetch_xml() -> list[dict]:
    print("  Stahuji feed z URL...")
    with urllib.request.urlopen(FEED_URL, timeout=120) as response:
        content = response.read()
    root = ET.fromstring(content)
    products = []
    for item in root.findall("product"):
        params = {}
        for param in item.findall("parameters/param"):
            n = param.findtext("n", "").strip()
            v = param.findtext("value", "").strip()
            if n:
                params[n] = v
        add_images = [img.text for img in item.findall("add_images") if img.text]
        products.append({
            "product_id":         item.findtext("product_id", ""),
            "sku":                item.findtext("sku", ""),
            "ean":                item.findtext("ean", ""),
            "manufacturer":       item.findtext("manufacturer", ""),
            "product_name":       item.findtext("product_name", ""),
            "short_description":  item.findtext("short_description", ""),
            "long_description":   item.findtext("long_description", ""),
            "category_text":      item.findtext("category_text", ""),
            "parameters":         params,
            "img_url":            item.findtext("img_url", ""),
            "add_images":         add_images,
            "retail_price":       item.findtext("retail_price", ""),
            "wholesale_price":    item.findtext("wholesale_price", ""),
            "wholesale_discount": item.findtext("wholesale_discount", ""),
            "stock":              item.findtext("stock", ""),
            "daystodelivery":     item.findtext("daystodelivery", ""),
            "sale":               item.findtext("sale", ""),
            "new":                item.findtext("new", ""),
            "weight":             item.findtext("weight", ""),
            "warranty":           item.findtext("warranty", ""),
        })
    return products

def load_existing(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {str(p["product_id"]): p for p in data}

def translate_batch(products: list[dict], target_lang: str) -> list[dict]:
    lang_names = {"is": "Icelandic", "en": "English"}
    lang_name = lang_names[target_lang]
    BATCH = 15
    translated_all = []
    for i in range(0, len(products), BATCH):
        chunk = products[i:i+BATCH]
        to_translate = [{
            "product_id":        p["product_id"],
            "product_name":      p["product_name"],
            "short_description": p["short_description"],
            "long_description":  p["long_description"],
            "category_text":     p["category_text"],
            "parameters":        p["parameters"],
        } for p in chunk]
        payload = json.dumps(to_translate, ensure_ascii=False, indent=2)
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": f"""You are a professional B2B jewelry and watch catalog translator.
Translate ONLY these fields into {lang_name}:
- product_name
- short_description
- long_description
- category_text
- parameters (translate both keys and values)

Keep product_id exactly as-is.
Keep brand names (SWATCH, Just Cavalli, etc.) unchanged.
Return ONLY a valid JSON array, no markdown, no explanation.

{payload}"""
            }]
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        translations = json.loads(raw.strip())
        trans_map = {str(t["product_id"]): t for t in translations}
        for p in chunk:
            merged = dict(p)
            t = trans_map.get(str(p["product_id"]), {})
            merged["product_name"]      = t.get("product_name", p["product_name"])
            merged["short_description"] = t.get("short_description", p["short_description"])
            merged["long_description"]  = t.get("long_description", p["long_description"])
            merged["category_text"]     = t.get("category_text", p["category_text"])
            merged["parameters"]        = t.get("parameters", p["parameters"])
            translated_all.append(merged)
        done = min(i + BATCH, len(products))
        print(f"  [{target_lang.upper()}] {done}/{len(products)}")
    return translated_all

def save_json(data: list[dict], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Uloženo: {path} ({len(data)} produktů)")

if __name__ == "__main__":
    print("📦 Načítám feed...")
    products_cs = fetch_xml()
    print(f"  Nalezeno {len(products_cs)} produktů")

    os.makedirs("data", exist_ok=True)
    save_json(products_cs, "data/products.cs.json")

    existing_is = load_existing("data/products.is.json")
    existing_en = load_existing("data/products.en.json")

    new_products = [p for p in products_cs
                    if str(p["product_id"]) not in existing_is]
    print(f"  Nových k překladu: {len(new_products)}")

    if new_products:
        print("🌐 Překládám → IS...")
        new_is = translate_batch(new_products, "is")
        all_is = list(existing_is.values()) + new_is
        save_json(all_is, "data/products.is.json")

        print("🌐 Překládám → EN...")
        new_en = translate_batch(new_products, "en")
        all_en = list(existing_en.values()) + new_en
        save_json(all_en, "data/products.en.json")
    else:
        print("  Žádné nové produkty.")

    print("✅ Hotovo!")
