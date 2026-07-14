import aiohttp
import feedparser
import asyncio
import logging
import re
from typing import List, Tuple
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class NewsAnalyzer:
    def __init__(self):
        self.impact_keywords = {
            # Очень высокое влияние (9-10)
            'exploit': 10,
            'hack': 10,
            'breach': 10,
            'ransomware': 10,
            'bankruptcy': 10,
            'liquidation': 10,
            'sec ban': 10,
            'delisting': 9,
            'regulatory ban': 9,
            'sec enforcement': 9,
            
            # Высокое влияние (7-8)
            'partnership': 8,
            'listing': 8,
            'major exchange': 8,
            'mainnet launch': 8,
            'merger': 8,
            'acquisition': 8,
            'approval': 7,
            'etf': 7,
            'sec approval': 7,
            'regulatory approval': 7,
            
            # Среднее влияние (5-6)
            'update': 6,
            'upgrade': 6,
            'fork': 6,
            'airdrop': 6,
            'token burn': 6,
            'rebrand': 6,
            'development': 5,
            'partnership news': 5,
            'funding': 5,
        }
        
        self.rss_feeds = [
            'https://cointelegraph.com/feed',
            'https://cryptonews.com/news/feed/',
            'https://www.coindesk.com/arc/outboundfeeds/rss/',
            'https://blog.coinbase.com/feed',
            'https://www.crypto-news-flash.com/feed/',
        ]
        
        self.api_sources = {
            'cryptopanic': 'https://cryptopanic.com/api/v1/posts/',
            'coingecko': 'https://api.coingecko.com/api/v3/events',
        }
        
    async def get_news_from_all_sources(self, coin_name: str) -> List[dict]:
        """Получить новости из всех источников"""
        all_news = []
        
        tasks = [
            self.get_rss_news(coin_name),
            self.get_cryptopanic_news(coin_name),
            self.get_coingecko_news(coin_name),
            self.get_reddit_news(coin_name),
            self.get_coinmarketcap_news(coin_name),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                all_news.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Ошибка при получении новостей: {result}")
        
        # Удалить дубликаты
        unique_news = []
        seen_titles = set()
        
        for news in all_news:
            title = news.get('title', '').lower()
            if title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(news)
        
        logger.info(f"Получено {len(unique_news)} уникальных новостей для {coin_name}")
        return unique_news[:10]  # Возвращаем топ-10 новостей
    
    async def get_rss_news(self, coin_name: str) -> List[dict]:
        """Получить новости из RSS лент"""
        news = []
        
        for feed_url in self.rss_feeds:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)
                            
                            for entry in feed.entries[:20]:  # Последние 20 записей
                                title = entry.get('title', '').lower()
                                
                                if coin_name.lower() in title or self.is_relevant_news(title):
                                    news.append({
                                        'title': entry.get('title', 'Unknown'),
                                        'description': entry.get('summary', '')[:200],
                                        'source': feed.feed.get('title', feed_url),
                                        'url': entry.get('link', ''),
                                        'date': entry.get('published', ''),
                                        'type': 'rss'
                                    })
            except asyncio.TimeoutError:
                logger.warning(f"Timeout при запросе RSS {feed_url}")
            except Exception as e:
                logger.warning(f"Ошибка при парсинге RSS {feed_url}: {e}")
        
        return news
    
    async def get_cryptopanic_news(self, coin_name: str) -> List[dict]:
        """Получить новости из CryptoPanic"""
        news = []
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'filter': 'hot',
                    'kind': 'news',
                    'region': 'en',
                }
                
                async with session.get(
                    self.api_sources['cryptopanic'],
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for result in data.get('results', [])[:50]:
                            title = result.get('title', '').lower()
                            
                            if coin_name.lower() in title:
                                news.append({
                                    'title': result.get('title', 'Unknown'),
                                    'description': result.get('body', '')[:200],
                                    'source': 'CryptoPanic',
                                    'url': result.get('url', ''),
                                    'date': result.get('published_at', ''),
                                    'type': 'api'
                                })
        except Exception as e:
            logger.warning(f"Ошибка при получении новостей CryptoPanic: {e}")
        
        return news
    
    async def get_coingecko_news(self, coin_name: str) -> List[dict]:
        """Получить события из CoinGecko"""
        news = []
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.coingecko.com/api/v3/events"
                params = {'limit': 50}
                
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for event in data.get('data', []):
                            title = event.get('title', '').lower()
                            
                            if coin_name.lower() in title:
                                news.append({
                                    'title': event.get('title', 'Unknown'),
                                    'description': event.get('description', '')[:200],
                                    'source': 'CoinGecko',
                                    'url': event.get('link', ''),
                                    'date': event.get('created_at', ''),
                                    'type': 'api'
                                })
        except Exception as e:
            logger.warning(f"Ошибка при получении событий CoinGecko: {e}")
        
        return news
    
    async def get_reddit_news(self, coin_name: str) -> List[dict]:
        """Получить новости из Reddit"""
        news = []
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://www.reddit.com/r/cryptocurrency/search.json"
                params = {
                    'q': coin_name,
                    'sort': 'hot',
                    'limit': 30,
                    'restrict_sr': False
                }
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for post in data.get('data', {}).get('children', [])[:20]:
                            post_data = post.get('data', {})
                            title = post_data.get('title', '').lower()
                            
                            if coin_name.lower() in title:
                                news.append({
                                    'title': post_data.get('title', 'Unknown'),
                                    'description': post_data.get('selftext', '')[:200],
                                    'source': 'Reddit',
                                    'url': f"https://reddit.com{post_data.get('permalink', '')}",
                                    'date': datetime.fromtimestamp(post_data.get('created_utc', 0)).isoformat(),
                                    'type': 'social'
                                })
        except Exception as e:
            logger.warning(f"Ошибка при получении новостей Reddit: {e}")
        
        return news
    
    async def get_coinmarketcap_news(self, coin_name: str) -> List[dict]:
        """Получить новости из CoinMarketCap"""
        news = []
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.coinmarketcap.com/dexscreener/latest/dex/tokens"
                headers = {
                    'User-Agent': 'Mozilla/5.0'
                }
                
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info("Новые данные с CoinMarketCap получены")
        except Exception as e:
            logger.warning(f"Ошибка при получении данных CoinMarketCap: {e}")
        
        return news
    
    def is_relevant_news(self, title: str) -> bool:
        """Проверить, релевантна ли новость криптовалютам"""
        crypto_keywords = [
            'crypto', 'bitcoin', 'ethereum', 'blockchain', 'defi',
            'nft', 'token', 'exchange', 'trading', 'wallet',
            'altcoin', 'coin', 'market', 'price', 'rally'
        ]
        
        for keyword in crypto_keywords:
            if keyword in title:
                return True
        
        return False
    
    async def analyze_impact(self, coin_name: str, news: List[dict]) -> Tuple[int, str, str]:
        """Анализировать влияние новостей на цену (1-10 баллов)"""
        try:
            max_impact = 0
            summaries = []
            sources_set = set()
            
            for item in news:
                title = item.get('title', '').lower()
                source = item.get('source', 'Unknown')
                sources_set.add(source)
                
                # Проверить ключевые слова для определения влияния
                item_impact = 0
                for keyword, impact in self.impact_keywords.items():
                    if keyword.lower() in title:
                        item_impact = max(item_impact, impact)
                
                if item_impact > 0:
                    max_impact = max(max_impact, item_impact)
                    summaries.append(f"• {item.get('title', 'Unknown')}")
            
            # Если новостей нет, возвращаем низкий скор
            if max_impact == 0:
                max_impact = 3
            
            # Форматировать источники
            sources_text = ', '.join(list(sources_set)[:5])
            if len(sources_set) > 5:
                sources_text += f" (+{len(sources_set)-5})"
            
            summary = '\n'.join(summaries[:3]) if summaries else "Обновление информации"
            
            return max_impact, summary, sources_text
            
        except Exception as e:
            logger.error(f"Ошибка при анализе влияния: {e}")
            return 3, "Обновление информации", "Unknown"