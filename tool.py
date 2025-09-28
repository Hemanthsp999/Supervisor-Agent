# tool.py
import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.tools import tool
# from bs4 import BeautifulSoup
import logging
from dotenv import load_dotenv
import os


load_dotenv()
serper_api_key = os.getenv("serper_api_key")

logging.basicConfig(level=logging.INFO)
USER_AGENT = "Mozilla/5.0 (compatible; ProductScraper/1.0; +https://example.com/bot)"

ALLOWED_DOMAINS = ["amazon.", "flipkart.", "ebay.", "walmart.", "bestbuy."]


def _is_allowed_url(url: str) -> bool:
    return any(domain in url.lower() for domain in ALLOWED_DOMAINS)


def _clean_text(txt: Optional[str]) -> Optional[str]:
    if not txt:
        return None
    return " ".join(txt.strip().split())


def GetAsin(url: str) -> str:
    return re.search(r'B0[A-Z0-9]{8}', url)


@tool
def getProductLinks(productName: str, top_k: int = 8) -> Dict[str, Any]:
    """
    Search for productName across search API and return a list of
    candidate product links from allowed marketplaces.
    Output schema:
    {
        "organic":[
            {
                "title": "1 Liter Stainless Steel Water Bottle » Ocean Bottle",
                "link": "https://oceanbottle.co/en-us/collections/big-ocean-bottle",
                "snippet": "Our Big Ocean Bottle is a reusable stainless steel water bottle with a 1 liter (34oz) capacity. Made from recycled materials, every order directly supports ...",
                "priceRange": "$9 delivery",
                "position": 1
            },
            {
                "title": "Yonder® 1L / 34 oz Water Bottle",
                "link": "https://www.yeti.com/drinkware/hydration/yonder-34oz.html",
                "snippet": "Our 1L / 34 oz plastic water bottle is light enough to carry you deep into the backcountry. Bottle is BPA-free and 50% recycled plastic; * ...",
                "rating": 4.7,
                "ratingCount": 1846,
                "currency": "$",
                "price":28,
                "position": 2
            }
        ]
    }
    """
    try:
        search = GoogleSerperAPIWrapper(
            serper_api_key=serper_api_key
        )

        raw = search.results(productName)
        org = raw.get("organic", []) if isinstance(raw, dict) else []

        items = []
        for r in org:
            link = r.get("link") or r.get("url") or ""
            if not link:
                continue
            if _is_allowed_url(link):
                title = _clean_text(r.get("title") if r.get("title") else "")
                snippet = _clean_text(r.get("snippet") or r.get("description") or "")

                print(f"Debug title: {title}")

                domain = ""
                for d in ALLOWED_DOMAINS:
                    if d in link.lower():
                        domain = d.strip(".")
                        break
                items.append({"source": domain or "unknown", "url": link,
                             "title": title, "snippet": snippet})
                if len(items) >= top_k:
                    break

        return {"query": productName, "results": items}

    except Exception as e:
        logging.exception("getProductLinks failed")
        return {"error": f"getProductLinks exception: {str(e)}", "query": productName, "results": []}


@tool
def getProductDetails(links: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Given a list of link dicts (each must contain 'url'), fetch page(s) and try to extract structured data.
    Input:
        links = [
            {
                "title": "1 Liter Stainless Steel Water Bottle » Ocean Bottle",
                "link": "https://oceanbottle.co/en-us/collections/big-ocean-bottle",
                "snippet": "Our Big Ocean Bottle is a reusable stainless steel water bottle with a 1 liter (34oz) capacity. Made from recycled materials, every order directly supports ...",
                "priceRange": "$9 delivery",
                "position": 1
            },
            {
                "title": "Yonder® 1L / 34 oz Water Bottle",
                "link": "https://www.yeti.com/drinkware/hydration/yonder-34oz.html",
                "snippet": "Our 1L / 34 oz plastic water bottle is light enough to carry you deep into the backcountry. Bottle is BPA-free and 50% recycled plastic; * ...",
                "rating": 4.7,
                "ratingCount": 1846,
                "currency": "$",
                "price":28,
                "position": 2
            },
            ....

      ]

    Output:
        {
            "results": [
                {
                    "url": "...",
                    "source": "...",
                    "asin": "..." 'extract asin from url only for amazon.in website'
                    "title": "...",
                    "price": {"value": 123.45, "currency":"INR"},
                    "availability": "In Stock" / "Out of stock" / null,
                    "images": ["..."],
                    "specs": {"key": "value", ...},
                    "rating": 4.2,
                    "raw_html_snippet": "... (short)",
                    "error": null
                },
            ...
            ]
      }
    NOTE: This tool MUST NOT HALLUCINATE. If a field is not found, set null.
    """
    results = []
    headers = {"User-Agent": USER_AGENT}

    for link_obj in links:
        print(f"Debug link: {link_obj}")

        try:
            resp = requests.get(url=link_obj["link"], headers=headers)
            print(f"Debug request: {resp.content}")

            soup = BeautifulSoup(resp.content, 'html_parser')

            contents = soup.find_all('div')

            for content in contents:
                title = content.find('title')
                link = content.find('href')

                if "amazon.com" in link:
                    asin = GetAsin(link)

        except Exception as e:
            logging.exception(f"Error in getProductDetails: {str(e)}")
