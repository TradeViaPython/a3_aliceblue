
import json
import requests
import threading
import websocket
import logging
import hashlib
import pandas as pd
from time import sleep
from collections import namedtuple
import dateutil.parser
import datetime
import os

from .__version__ import __version__, __title__

logger = logging.getLogger(__name__)

Instrument = namedtuple('Instrument', ['exchange', 'token', 'symbol', 'name', 'expiry', 'lot_size'])


class Alice:
    # Price type
    PRICE_TYPE_MARKET = 'MKT'
    PRICE_TYPE_LIMIT = 'L'
    PRICE_TYPE_SL = 'SL'
    PRICE_TYPE_SLM = 'SL-M'

    # Product
    PRODUCT_TYPE_MIS = 'MIS'
    PRODUCT_TYPE_CNC = 'CNC'
    PRODUCT_TYPE_NRML = 'NRML'

    # Complixty
    COMPLEXTY_BO = 'BO'
    COMPLEXTY_AMO = 'AMO'
    COMPLEXTY_REGULAR = 'regular'

    # Validity
    VALIDITY_DAY = "DAY"
    VALIDITY_IOC = "IOC"

    # Position
    POSITION_DAYWISE = "DAY"
    POSITION_NETWISE = "NET"

    # Transaction type
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"

    # Exchanges
    EXCHANGE_NSE = "NSE"
    EXCHANGE_NFO = "NFO"
    EXCHANGE_CDS = "CDS"
    EXCHANGE_BSE = "BSE"
    EXCHANGE_BFO = "BFO"
    EXCHANGE_BCD = "BCD"
    EXCHANGE_MCX = "MCX"

    _root_url = "https://a3.aliceblueonline.com/rest/AliceBlueAPIService/api/"
    _sub_urls = {
        # Authentication
        "ApiEncryptionKey": "/customer/getAPIEncpkey",
        "SessionId": "/customer/getUserSID",
        # "LogoutFromAPI": "/customer/logout",
        # "LogoutFromAllDevices": "/customer/logOutFromAllDevice",

        # Market Watch
        # "MarketWatchList": "/marketWatch/fetchMWList",
        # "MarketWatchScrips": "/marketWatch/fetchMWScrips",
        # "AddScrips": "/marketWatch/addScripToMW",
        # "DeleteScrips": "/marketWatch/deleteMWScrip",
        "ScripDetails": "/ScripDetails/getScripQuoteDetails",

        # Portfolio
        "PositionBook": "/positionAndHoldings/positionBook",
        "Holdings": "/positionAndHoldings/holdings",

        # Order Management
        "PlaceOrder": "/placeOrder/executePlaceOrder",
        # "BracketOrder": "/placeOrder/executePlaceOrder",
        "SquareOfPosition": "/positionAndHoldings/sqrOofPosition",
        "OrderBook": "/placeOrder/fetchOrderBook",
        "TradeBook": "/placeOrder/fetchTradeBook",
        "ExitBracketOrder": "/placeOrder/exitBracketOrder",
        "ModifyOrder": "/placeOrder/modifyOrder",
        # "MarketOrder": "/placeOrder/executePlaceOrder",
        "position_conversion": "/positionAndHoldings/positionConvertion",
        "CancelOrder": "/placeOrder/cancelOrder",
        "OrderHistory": "/placeOrder/orderHistory",

        # Funds
        "GetLimits": "/limits/getRmsLimits",

        # Profile
        "AccountDetails": "customer/accountDetails",

        # websocket
        "ws_root_url": "wss://ws1.aliceblueonline.com/NorenWS/",
        "ws_CreateSession": "ws/createSocketSess",   # But in REST API DOCS "/ws/createWsSession" Not working
        "ws_InvalidateSession": "/ws/invalidateSocketSess"
    }

    def __init__(self, user_id, api_key):

        self.user_id = user_id
        self.api_key = api_key
        self.session_id = None
        self.master_contract = None
        self.__websocket = None
        self.__websocket_connected = False
        self.__ws_mutex = threading.Lock()
        self.__on_error = None
        self.__on_disconnect = None
        self.__on_open = None
        self.__subscribe_callback = None
        self.__order_update_callback = None
        self.__subscribes = {}
        self.root_url = self._root_url

        self.api_name = __title__
        self.version = __version__

    def _request(self, sub_url, req_type, data=None):
        headers = {
            "X-SAS-Version": "2.0",
            "User-Agent": self.api_name + self.version,
            "Authorization": "Bearer " + self.user_id.upper() + " " + (self.session_id if bool(self.session_id) else ""),
            'Content-Type': 'application/json'
        }
        try:
            if req_type == "GET":
                response = requests.get(self.root_url + self._sub_urls[sub_url], json=data, headers=headers, )
            if req_type == "POST":
                response = requests.post(self.root_url + self._sub_urls[sub_url], json=data, headers=headers, )
        except (requests.ConnectionError, requests.Timeout) as exception:
            raise Exception("Check Your Internet Connection")
        if response.status_code == 200:
            return json.loads(response.text)
        else:
            raise Exception(f"{response.status_code} : {response.reason}")

    def create_session(self):
        data = {'userId': self.user_id.upper()}
        response = self._request("ApiEncryptionKey", "POST", data)
        if response['encKey'] is None:
            raise Exception(response["emsg"])
        else:
            data = hashlib.sha256((self.user_id.upper() + self.api_key + response['encKey']).encode()).hexdigest()
        data = {'userId': self.user_id.upper(), 'userData': data}
        response = self._request("SessionId", "POST", data)

        if response['stat'] == 'Ok':
            self.session_id = response['sessionID']
            return response
        else:
            raise Exception(response["emsg"])

    def __ws_run_forever(self):
        while self.__stop_event.is_set() is False:
            try:
                self.__websocket.run_forever(ping_interval=3, ping_payload='{"t":"h"}')
            except Exception as e:
                logger.warning(f"websocket run forever ended in exception, {e}")
            sleep(0.1)  # Sleep for 100ms between reconnection.

    def __ws_send(self, *args, **kwargs):
        while self.__websocket_connected == False:
            sleep(0.05)  # sleep for 50ms if websocket is not connected, wait for reconnection
        with self.__ws_mutex:
            ret = self.__websocket.send(*args, **kwargs)
        return ret

    def __on_close_callback(self, wsapp, close_status_code, close_msg):
        logger.debug(close_status_code)
        logger.debug(wsapp)

        self.__websocket_connected = False
        if self.__on_disconnect:
            self.__on_disconnect()

    def __on_open_callback(self, ws=None):
        self.__websocket_connected = True

        payload = json.dumps({
                            "susertoken": self.__susertoken,
                            "t": "c",
                            "actid": self.user_id + "_API",
                            "uid": self.user_id + "_API",
                            "source": "API"
                         })
        logger.debug(payload)
        self.__ws_send(payload)
        # self.__resubscribe()

    def __on_error_callback(self, ws=None, error=None):
        if type(ws) is not websocket.WebSocketApp:  # This workaround is to solve the websocket_client's compatiblity issue of older versions. ie.0.40.0 which is used in upstox. Now this will work in both 0.40.0 & newer version of websocket_client
            error = ws
        if self.__on_error:
            self.__on_error(error)

    def __on_data_callback(self, ws=None, message=None, data_type=None, continue_flag=None):
        # print(ws)
        # print(message)
        # print(data_type)
        # print(continue_flag)
        res = json.loads(message)

        if self.__subscribe_callback is not None:
            if res['t'] == 'tk' or res['t'] == 'tf':
                res["ts"] = self.__subscribes[f"{res['e']}|{res['tk']}"]
                self.__subscribe_callback(res)
                return
            if res['t'] == 'dk' or res['t'] == 'df':
                res["ts"] = self.__subscribes[f"{res['e']}|{res['tk']}"]
                self.__subscribe_callback(res)
                return

        if self.__on_error is not None:
            if res['t'] == 'ck' and res['s'] != 'OK':
                self.__on_error(res)
                return

        if self.__order_update_callback is not None:
            if res['t'] == 'om':
                self.__order_update_callback(res)
                return

        if self.__on_open:
            if res['t'] == 'ck' and res['s'] == 'OK':
                self.__on_open()
                return

    def invalidate_socket_session(self):
        response = self._request("ws_InvalidateSession", "POST", data={"loginType": "API"})
        return response

    def create_socket_session(self):
        response = self._request("ws_CreateSession", "POST", data={"loginType": "API"})
        return response

    def start_websocket(self, subscribe_callback=None,
                        order_update_callback=None,
                        socket_open_callback=None,
                        socket_close_callback=None,
                        socket_error_callback=None,
                        run_in_background=False):
        """ Start a websocket connection for getting live data """
        self.__on_open = socket_open_callback
        self.__on_disconnect = socket_close_callback
        self.__on_error = socket_error_callback
        self.__subscribe_callback = subscribe_callback
        self.__order_update_callback = order_update_callback
        self.__stop_event = threading.Event()
        sha256_encryption1 = hashlib.sha256(self.session_id.encode('utf-8')).hexdigest()
        self.__susertoken = hashlib.sha256(sha256_encryption1.encode('utf-8')).hexdigest()
        url = self._sub_urls["ws_root_url"]
        logger.debug('connecting to {}'.format(url))

        self.__websocket = websocket.WebSocketApp(url,
                                                  on_data=self.__on_data_callback,
                                                  on_error=self.__on_error_callback,
                                                  on_close=self.__on_close_callback,
                                                  on_open=self.__on_open_callback)
        # th = threading.Thread(target=self.__send_heartbeat)
        # th.daemon = True
        # th.start()
        if run_in_background is True:
            self.__ws_thread = threading.Thread(target=self.__ws_run_forever)
            self.__ws_thread.daemon = True
            self.__ws_thread.start()
        else:
            self.__ws_run_forever()

    def close_websocket(self):
        if self.__websocket_connected == False:
            return
        self.__stop_event.set()
        self.__websocket_connected = False
        self.__websocket.close()
        self.__ws_thread.join()

    def subscribe(self, instrument):
        if type(instrument) is not list:
            instrument = [instrument]
        for i in instrument:
            try:
                i.exchange, i.token
            except:
                continue
            self.__subscribes[f"{i.exchange}|{i.token}"] = f"{i.symbol}"
        values = ""
        for i in list(self.__subscribes.keys()):
            values += f"{i}#"
        self.__ws_send(json.dumps({
            "k": values[:-1],
            "t": 'd'
        }))

    def unsubscribe(self, instrument):
        if type(instrument) is not list:
            instrument = [instrument]
        values = ""
        for i in instrument:
            try:
                i.exchange, i.token
            except:
                continue
            i = f"{i.exchange}|{i.token}"
            if i in self.__subscribes.keys():
                values += f"{i}#"
                del self.__subscribes[i]
        self.__ws_send(json.dumps({
            "k": values[:-1],
            "t": 'ud'
        }))

    def get_scrip_details(self, instrument):
        try:
            instrument.exchange, instrument.token
        except:
            raise Exception('Provide Valid Instrument')
        return self._request("ScripDetails", "POST", data={"exch":str(instrument.exchange), "symbol":str(instrument.token)})

    def get_trade_book(self):
        return self._request("TradeBook", "GET")

    def get_profile(self):
        return self._request("AccountDetails", "GET")

    def get_balance(self):
        return self._request("GetLimits", "GET")

    def get_holdings(self):
        return self._request("Holdings", "GET")

    def get_orderbook(self):
        return self._request("OrderBook", "GET")

    def get_order_history(self, nestOrderNumber):
        if nestOrderNumber == '':
            return self._request("OrderBook", "GET")
        else:
            return self._request("OrderHistory", "POST", {'nestOrderNumber': nestOrderNumber})

    def place_order(self, transaction_type, instrument, quantity, price_type,
                    product_type, price=0.0, trigger_price=None,
                    stop_loss=None, square_off=None, trailing_sl=None,
                    validity="DAY",
                    order_tag=None,
                    complexty="regular"):
        """ placing an order, many fields are optional and are not required
                    for all order types
                """
        if transaction_type is None:
            raise TypeError("Required parameter transaction_type not of type TransactionType")
        if not isinstance(instrument, Instrument):
            raise TypeError("Required parameter instrument not of type Instrument")
        if not isinstance(quantity, int):
            raise TypeError("Required parameter quantity not of type int")
        if price_type is None:
            raise TypeError("Required parameter price_type not of type PRICE_TYPE")
        if product_type is None:
            raise TypeError("Required parameter product_type not of type PRODUCT_TYPE")
        if price is not None and not isinstance(price, float):
            raise TypeError("Optional parameter price not of type float")
        if trigger_price is not None and not isinstance(trigger_price, float):
            raise TypeError("Optional parameter trigger_price not of type float")
        data = [{'discqty': 0,
                 'exch': instrument.exchange,
                 'pCode': product_type,
                 'price': price,
                 'prctyp': price_type,
                 'qty': quantity,
                 'ret': validity,
                 'symbol_id': str(instrument.token),
                 'trading_symbol': instrument.symbol,
                 'transtype': transaction_type,
                 "stopLoss": stop_loss,
                 "target": square_off,
                 "trailing_stop_loss": trailing_sl,
                 "trigPrice": trigger_price,
                 "orderTag": order_tag,
                 'complexty': complexty}]
        return self._request("PlaceOrder", "POST", data)

    def cancel_order(self, instrument, nestOrderNumber):
        return self._request("CancelOrder", "POST", {'exch': instrument.exchange,
                                          'nestOrderNumber': nestOrderNumber,
                                          'trading_symbol': instrument.symbol})

    def modify_order(self, transaction_type, instrument, product_type, nestOrderNumber, price_type, quantity, price=0.0,
                     trigger_price=0.0):
        if not isinstance(instrument, Instrument):
            raise TypeError("Required parameter instrument not of type Instrument")

        if not isinstance(nestOrderNumber, str):
            raise TypeError("Required parameter nestOrderNumber not of type str")

        if not isinstance(quantity, int):
            raise TypeError("Optional parameter quantity not of type int")

        if price_type is None:
            raise TypeError("Optional parameter price_type not of type PRICE_TYPE")

        if product_type is None:
            raise TypeError("Required parameter product_type not of type PRODUCT_TYPE")

        if price is not None and not isinstance(price, float):
            raise TypeError("Optional parameter price not of type float")

        if trigger_price is not None and not isinstance(trigger_price, float):
            raise TypeError("Optional parameter trigger_price not of type float")
        data = {'discqty': 0,
                'exch': instrument.exchange,
                'nestOrderNumber': nestOrderNumber,
                'prctyp': price_type,
                'price': price,
                'qty': quantity,
                'trading_symbol': instrument.symbol,
                'trigPrice': trigger_price,
                'transtype': transaction_type,
                'pCode': product_type}
        return self._request("ModifyOrder", "POST", data)

    def exit_bracket_order(self, nestOrderNumber, symbolOrderId, status, ):
        return self._request("ExitBracketOrder", "POST",
                             {'nestOrderNumber': nestOrderNumber,
                              'symbolOrderId': symbolOrderId,
                              'status': status, })

    def get_positions(self, position=POSITION_DAYWISE, ):
        return self._request("PositionBook", "POST", {'ret': position, })

    def place_basket_order(self, orders):
        data = []
        for i in range(len(orders)):
            order_data = orders[i]
            complexty = order_data['complexty']
            instrument = order_data['instrument']
            product_type = order_data["product_type"]
            price = order_data['price'] if 'price' in order_data else 0
            price_type = order_data['price_type']
            quantity = order_data['quantity']
            validity = order_data["validity"]
            transaction_type = order_data['transaction_type']
            trigger_price = order_data['trigger_price'] if 'trigger_price' in order_data else None
            stop_loss = order_data['stop_loss'] if 'stop_loss' in order_data else None
            trailing_sl = order_data['trailing_sl'] if 'trailing_sl' in order_data else None
            square_off = order_data['square_off'] if 'square_off' in order_data else None
            order_tag = order_data['order_tag'] if 'order_tag' in order_data else None
            request_data = {'discqty': 0,
                             'exch': instrument.exchange,
                             'pCode': product_type,
                             'price': price,
                             'prctyp': price_type,
                             'qty': quantity,
                             'ret': validity,
                             'symbol_id': str(instrument.token),
                             'trading_symbol': instrument.symbol,
                             'transtype': transaction_type,
                             "stopLoss": stop_loss,
                             "target": square_off,
                             "trailing_stop_loss": trailing_sl,
                             "trigPrice": trigger_price,
                             "orderTag": order_tag,
                             'complexty': complexty}

            data.append(request_data)
        order = self._request("PlaceOrder", "POST", data)
        return order

    def download_master_contract(self, to_csv=False):
        print("Master Contract Downloading (After 8:00am today data available else previous day)....", end="")
        all_Exchanges = ["INDICES", "NSE", "BSE", "NFO", "BCD", "MCX", "CDS", "BFO"]
        for i in all_Exchanges:
            if self.master_contract is None:
                self.master_contract = pd.read_csv(
                    f"https://v2api.aliceblueonline.com/restpy/static/contract_master/{i}.csv")
                self.master_contract.columns = self.master_contract.columns.str.title()
                self.master_contract["Trading Symbol"] = self.master_contract["Symbol"]
            else:
                self.master_contract = pd.concat([self.master_contract, pd.read_csv(
                    f"https://v2api.aliceblueonline.com/restpy/static/contract_master/{i}.csv")], ignore_index=True)
                self.master_contract.columns = self.master_contract.columns.str.title()
        self.master_contract = self.master_contract[self.master_contract["Exch"] != ""]
        self.master_contract["Expiry Date"] = self.master_contract["Expiry Date"].apply(
            lambda x: dateutil.parser.parse(str(x)).date() if str(x).strip() != "nan" and bool(x) else x)
        self.master_contract = self.master_contract.rename(
            columns={"Exch": "exchange", "Symbol": "name", "Token": "instrument_token",
                     "Trading Symbol": "trading_symbol", "Instrument Type": "segment", "Lot Size": "lot_size",
                     "Strike Price": "strike", "Option Type": "instrument_type", "Expiry Date": "expiry"})
        self.master_contract = self.master_contract[
            ["exchange", "name", "instrument_token", "segment", "expiry", "instrument_type", "strike", "lot_size",
             "trading_symbol"]]
        if bool(to_csv):
            self.master_contract.to_csv("Exchange.csv", index=False)
        print("Completed")
        return self.master_contract

    def get_master_contract(self, exchange=None):
        if self.master_contract is None:
            try:
                self.master_contract = pd.read_csv("Exchange.csv")
                self.master_contract["expiry"] = self.master_contract["expiry"].apply(
                    lambda x: dateutil.parser.parse(str(x)).date() if str(x).strip() != "nan" and bool(x) else x)
            except:
                self.download_master_contract()
        if exchange is None:
            return self.master_contract
        else:
            contract = self.master_contract[self.master_contract['exchange'] == exchange]
            if len(contract) == 0:
                raise Exception("Provide valid data")
            else:
                return contract

    def get_instrument_by_symbol(self, exchange, symbol):
        if self.master_contract is None:
            raise Exception("Download Master Contract First")
        contract = self.master_contract[self.master_contract['exchange'] == exchange]
        contract = contract[contract["trading_symbol"] == symbol]
        if len(contract) == 0:
            raise Exception("Provide valid data")
        return Instrument(list(contract['exchange'])[0], list(contract['instrument_token'])[0],
                          list(contract['trading_symbol'])[0], list(contract['name'])[0],
                          list(contract['expiry'])[0], list(contract['lot_size'])[0])

    def get_instrument_by_token(self, exchange, token):
        if self.master_contract is None:
            raise Exception("Download Master Contract First")
        contract = self.master_contract[self.master_contract['exchange'] == exchange]
        contract = contract[contract["instrument_token"] == float(token)]
        if len(contract) == 0:
            raise Exception("Provide valid data")
        return Instrument(list(contract['exchange'])[0], list(contract['instrument_token'])[0],
                          list(contract['trading_symbol'])[0], list(contract['name'])[0],
                          list(contract['expiry'])[0], list(contract['lot_size'])[0])

    def get_instrument_for_fno(self, exchange, name, expiry_date, is_fut=True, strike=None, is_CE=False):
        if self.master_contract is None:
            raise Exception("Download Master Contract First")
        contract = self.master_contract[self.master_contract['exchange'] == exchange]
        contract = contract[contract["name"] == name]
        contract = contract[contract["expiry"] == expiry_date]
        contract = contract[contract["instrument_type"] == ("XX" if bool(is_fut) else ("CE" if bool(is_CE) else "PE"))]
        if strike is not None and not bool(is_fut):
            contract = contract[contract["strike"] == float(strike)]
        if len(contract) == 0 or len(contract) > 1:
            raise Exception("Provide valid data")
        return Instrument(list(contract['exchange'])[0], list(contract['instrument_token'])[0],
                      list(contract['trading_symbol'])[0], list(contract['name'])[0],
                      list(contract['expiry'])[0], list(contract['lot_size'])[0])

    def get_historical(self, instrument, from_datetime, to_datetime, interval, indices=False):
        # intervals = ["1", "2", "3", "4", "5", "10", "15", "30", "60", "120", "180", "240", "D", "1W", "1M"]
        params = {"symbol": instrument.token,
                  "exchange": instrument.exchange if not indices else f"{instrument.exchange}::index",
                  "from": str(int(from_datetime.timestamp())),
                  "to": str(int(to_datetime.timestamp())),
                  "resolution": interval,
                  "user": self.user_id}
        lst = requests.get(
            f"https://a3.aliceblueonline.com/rest/AliceBlueAPIService/chart/history?", params=params).json()
        df = pd.DataFrame(lst)
        df = df.rename(columns={'t': 'datetime', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'})
        df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
        df["datetime"] = df["datetime"].apply(lambda x: datetime.datetime.fromtimestamp(x))
        return df

