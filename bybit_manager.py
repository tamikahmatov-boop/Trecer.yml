import aiohttp
import asyncio
import logging
from typing import List
import hmac
import hashlib
import time
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class BybitManager:
    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.bybit.com"
        self.futures_cache = []
        self.cache_time = 0
        self.cache_duration = 300  # 5 минут
        
    async def get_futures_pairs(self) -> List[dict]:
        """Получить список всех фьючерс-пар с Bybit"""
        try:
            # Использовать кэш если не устарел
            current_time = time.time()
            if self.futures_cache and (current_time - self.cache_time) < self.cache_duration:
                logger.info(f"✓ Используется кэш ({len(self.futures_cache)} пар)")
                return self.futures_cache
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/v5/market/instruments-info"
                params = {
                    'category': 'linear',
                    'limit': 1000,
                }
                
                all_pairs = []
                cursor = ''
                
                # Получить все пары через пагинацию
                while True:
                    if cursor:
                        params['cursor'] = cursor
                    
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if data.get('retCode') == 0:
                                list_data = data.get('result', {}).get('list', [])
                                
                                for instrument in list_data:
                                    symbol = instrument.get('symbol', '')
                                    base_coin = instrument.get('baseCoin', '')
                                    status = instrument.get('status', '')
                                    
                                    # Только USDT фьючерсы и активные
                                    if symbol.endswith('USDT') and status == 'Trading':
                                        all_pairs.append({
                                            'symbol': base_coin,
                                            'name': base_coin.lower(),
                                            'trading_pair': symbol,
                                            'price_precision': instrument.get('priceFilter', {}).get('tickSize', '0.01'),
                                        })
                                
                                # Проверить, есть ли еще страницы
                                next_cursor = data.get('result', {}).get('nextPageCursor', '')
                                if not next_cursor:
                                    break
                                
                                cursor = next_cursor
                            else:
                                logger.error(f"Ошибка API: {data.get('retMsg', 'Unknown')}")
                                break
                        else:
                            logger.error(f"HTTP Error: {response.status}")
                            break
                    
                    await asyncio.sleep(0.1)  # Небольшая задержка между запросами
                
                # Кэшировать результаты
                self.futures_cache = all_pairs
                self.cache_time = current_time
                
                logger.info(f"✓ Загружено {len(all_pairs)} фьючерс-пар с Bybit")
                return all_pairs
            
        except asyncio.TimeoutError:
            logger.error("Timeout при получении фьючерс-пар")
            return self.futures_cache  # Вернуть кэшированные данные если есть
        except Exception as e:
            logger.error(f"Ошибка при получении фьючерс-пар: {e}")
            return self.futures_cache
    
    async def get_coin_price(self, symbol: str) -> float:
        """Получить текущую цену монеты"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/v5/market/tickers"
                params = {
                    'category': 'linear',
                    'symbol': f"{symbol}USDT",
                }
                
                async with session.get(
                    url, 
                    params=params, 
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('retCode') == 0 and data.get('result', {}).get('list'):
                            price_str = data['result']['list'][0].get('lastPrice', '0')
                            return float(price_str)
                    
                    return 0.0
                    
        except Exception as e:
            logger.warning(f"Ошибка при получении цены {symbol}: {e}")
            return 0.0
    
    async def get_coin_change(self, symbol: str) -> dict:
        """Получить изменение цены за 24 часа"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/v5/market/tickers"
                params = {
                    'category': 'linear',
                    'symbol': f"{symbol}USDT",
                }
                
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if data.get('retCode') == 0 and data.get('result', {}).get('list'):
                            ticker = data['result']['list'][0]
                            return {
                                'price': float(ticker.get('lastPrice', '0')),
                                'change_24h': float(ticker.get('price24hPcnt', '0')) * 100,
                                'high_24h': float(ticker.get('highPrice24h', '0')),
                                'low_24h': float(ticker.get('lowPrice24h', '0')),
                            }
                    
                    return {'price': 0.0, 'change_24h': 0.0, 'high_24h': 0.0, 'low_24h': 0.0}
                    
        except Exception as e:
            logger.warning(f"Ошибка при получении изменения цены {symbol}: {e}")
            return {'price': 0.0, 'change_24h': 0.0, 'high_24h': 0.0, 'low_24h': 0.0}