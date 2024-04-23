from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup, NavigableString


class WebCrawler:
    """
    A web crawler class that uses Selenium WebDriver to load dynamic web pages
    and provide some other useful functionality.
    """
    def __init__(self, headless=True):
        """
        Initialize the WebCrawler instance.
        """
        self.url = None  # URL of the web page to be crawled.
        self.driver = self._get_driver(headless=headless)  # Selenium WebDriver instance.

    def _get_driver(self, headless=True):
        """
        Create and return a Selenium WebDriver instance with headless mode enabled.
        """
        options = Options()
        if headless:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        return driver

    def load_url(self, url):
        """
        Load the web page at the given URL.
        
        Args:
            url (str): URL of the web page to be loaded.
        """
        self.url = url
        self.driver.get(self.url)

    def find_links(self, pattern=r'.*'):
        """
        Find all links on the web page that match a given regular expression pattern.
        
        Args:
            pattern (str): Regular expression pattern to match links.
                default: r'.*' (match all links)
        
        Returns:
            list: List of matching links.
        """
        links = self.driver.find_elements(By.TAG_NAME, 'a')
        matching_links = []
        for link in links:
            href = link.get_attribute('href')
            if href is not None and re.search(pattern, href):
                matching_links.append(href)
        return matching_links

    def find_links_with_text(self, pattern=r'.*'):
        """
        Find all links on the web page that match a given regular expression pattern.

        Args:
            pattern (str): Regular expression pattern to match links.
                default: r'.*' (match all links)

        Returns:
            list: List of tuples, where each tuple contains the link text and the corresponding href attribute.
        """
        links = self.driver.find_elements(By.TAG_NAME, 'a')
        matching_links = []
        for link in links:
            href = link.get_attribute('href')
            text = link.text
            if href is not None and re.search(pattern, href):
                matching_links.append((text, href))
        return matching_links

    def get_cleaned_html(self):
        """
        Get the cleaned HTML of the current web page, keeping only elements that contain
        visible text or have subelements with visible text.

        Returns:
            str: Cleaned HTML content of the web page.
        """
        # Get the current page source
        html_content = self.driver.page_source

        # Ensure the content is treated as UTF-8
        html_content = html_content.encode('utf-8', errors='replace').decode('utf-8', errors='replace')

        # Parse the HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove script, style elements, and images
        for unwanted_tag in soup(['script', 'style', 'img']):
            unwanted_tag.decompose()

        # Remove all attributes except href in <a> tags
        for tag in soup.find_all(True):
            tag.attrs = {key: tag.attrs[key] for key in tag.attrs if key == 'href'}

        # Function to check if an element contains visible text
        def contains_visible_text(element):
            if isinstance(element, NavigableString):
                return element.strip() != ''
            return any(contains_visible_text(child) for child in element.children)

        # Remove elements without visible text or subelements with visible text
        for element in soup.find_all(True):
            if not contains_visible_text(element):
                element.decompose()

        # make all hrefs absolute
        for link in soup.find_all('a'):
            if 'href' in link.attrs:
                link['href'] = urljoin(self.url, link['href'])

        # Return the cleaned HTML as a string
        return str(soup)

    def close(self):
        """
        Close the Selenium WebDriver instance.
        """
        self.driver.quit()


if __name__ == "__main__":
    # Example usage
    url = 'https://online.stat.psu.edu/stat505/lesson/6/6.1'

    crawler = WebCrawler()
    crawler.load_url(url)

    cleaned_html = crawler.get_cleaned_html()
    # open the cleaned html in a browser
    with open('./cleaned.html', 'w') as f:
        f.write(cleaned_html)

    crawler.close()
