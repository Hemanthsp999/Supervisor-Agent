from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.tools import tool


@tool
def getProductLinks(productName: str) -> dict:

    try:
        search = GoogleSerperAPIWrapper()

        productDetails = search.results(productName)

        return productDetails

    except Exception as e:
        return f"Error: {str(e)}"


