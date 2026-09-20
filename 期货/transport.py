"""Same request payload/path as Tushare 1.4.24; HTTP errors never become empty data."""
import pandas as pd
import requests

from collector import DataError


class TushareHTTP:
    def __init__(self, token, url, timeout=30):
        if not token:
            raise DataError('TUSHARE_TOKEN not configured')
        self.token, self.url, self.timeout = token, url.rstrip('/'), timeout
        self.session = requests.Session()

    def query(self, name, fields='', **params):
        response = self.session.post(self.url + '/' + name, json={
            'api_name': name, 'token': self.token, 'params': params, 'fields': fields}, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        if result.get('code') != 0:
            # Do not expose gateway messages that may echo credentials.
            raise DataError(f'{name}: API error code {result.get("code")}')
        data = result.get('data')
        if not isinstance(data, dict) or not isinstance(data.get('fields'), list) or not isinstance(data.get('items'), list):
            raise DataError(f'{name}: malformed response')
        return pd.DataFrame(data['items'], columns=data['fields'])
