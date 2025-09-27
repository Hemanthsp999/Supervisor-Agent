import requests
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.tools import tool


@tool
def getProductLinks(productName: str) -> dict:
    """
    Use {productName} to get links from the different e-commerce websites like amazon.com, ebay.com, flipkart.com and etc.. 
    """

    try:
        search = GoogleSerperAPIWrapper()

        productDetails = search.results(productName)

        product_detail = []

        for result in productDetails['organic']:
            if any['amazon.com', 'flipkart.com', 'ebay.com'] in result["link"]:
                product_detail.append(result)

        return product_detail

    except Exception as e:
        return f"Error: {str(e)}"


@tool
def getProductDetails(links: str) -> list[str]:
    """
    Use {links} to get details of product. And return the details in structured format
    """

    try:

        for link in links["link"]:
            getResponse = requests.get(url=link)
            print(f"Debug: {getResponse}")

    except Exception as e:
        return f"Error while processing links from getProductDetails {str(e)}"
