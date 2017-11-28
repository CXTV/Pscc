import asyncio
import re
from html import unescape
from urllib.parse import urljoin

import aiohttp
from lxml import etree
import re
from pscc.requests import fetch
from utils.Logconfig import load_my_logging_cfg
logger = load_my_logging_cfg("")


class BaseParser(object):
    def __init__(self, rule, item=None):
        self.rule = rule
        self.item = item
        self.parsing_urls = []
        self.pre_parse_urls = []
        self.filter_urls = set()
        self.done_urls = []

    """
    解析子域名
    :param http://www.itmain4.com/forum-44-1.html
    ->"http://itmain4.com"
    ->"http://www.itmian4.com/thread-2993-1-1.html"
    """
    def parse_urls(self, html, base_url):
        if html is None:
            return
        for url in self.abstract_urls(html):
            url = unescape(url)
            if not re.match('(http|https)://', url):
                url = urljoin(base_url, url)

            """
            当urljoin 不能解析的时候，例如下面缺少‘jl/’导致的子域名不能访问
            """
            if base_url=="http://difang.gmw.cn/":
                base_url = 'http://difang.gmw.cn/jl/'
                url = re.sub(r"cn/",r"cn/jl/",url)
                url = urljoin(base_url, url)
            self.add(url)

    def abstract_urls(self, html):
        raise NotImplementedError

    def add(self, urls):
        url = '{}'.format(urls)
        if url not in self.filter_urls:
            self.filter_urls.add(url)
            self.pre_parse_urls.append(url)

    def parse_item(self, html):
        item = self.item(html)
        return item

    async def execute_url(self, url, spider, session, semaphore):
        html = await fetch(url, spider, session, semaphore)

        if html is None:
            spider.error_urls.append(url)
            self.pre_parse_urls.append(url)
            return None

        if url in spider.error_urls:
            spider.error_urls.remove(url)
        spider.urls_count += 1
        self.parsing_urls.remove(url)
        self.done_urls.append(url)

        if self.item is not None:
            item = self.parse_item(html)
            await item.save()
            self.item.count_add()
            logger.info('Parsed({}/{}): {}'.format(len(self.done_urls), len(self.filter_urls), url))
        else:
            spider.parse(html)
            logger.info('Followed({}/{}): {}'.format(len(self.done_urls), len(self.filter_urls), url))

    async def task(self, spider, semaphore):
        with aiohttp.ClientSession() as session:
            while spider.is_running():
                if len(self.pre_parse_urls) == 0:
                    await asyncio.sleep(0.5)
                    continue
                url = self.pre_parse_urls.pop()
                self.parsing_urls.append(url)
                asyncio.ensure_future(self.execute_url(url, spider, session, semaphore))


class Parser(BaseParser):
    def abstract_urls(self, html):
        urls = re.findall(self.rule, html)
        return urls


class XPathParser(BaseParser):
    def abstract_urls(self, html):
        doc = etree.HTML(html)
        urls = doc.xpath(self.rule)
        return urls