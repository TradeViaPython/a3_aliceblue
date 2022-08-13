
import json
import requests
import threading
import websocket
import logging
import hashlib
import time
import pandas as pd
from time import sleep
from collections import namedtuple
import dateutil.parser


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
        "ws_CreateSession": "/ws/createWsSession",
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
        self.__subscribes = []
        self.root_url = self._root_url

        self.api_name = "TradeViaPython"
        self.version = "1.0.0"

    def _user_agent(self):
        return self.api_name + self.version

    def _user_authorization(self):
        if self.session_id:
            return "Bearer " + self.user_id.upper() + " " + self.session_id
        else:
            return ""

    def _get(self, sub_url, data=None):
        url = self.root_url + self._sub_urls[sub_url]
        return self._request(url, "GET", data=data)

    def _request(self, method, req_type, data=None):
        """
        Headers with authorization. For some requests authorization
        is not required. It will be send as empty String
        """
        _headers = {
            "X-SAS-Version": "2.0",
            "User-Agent": self._user_agent(),
            "Authorization": self._user_authorization()
        }
        if req_type == "POST":
            try:
                response = requests.post(method, json=data, headers=_headers, )
            except (requests.ConnectionError, requests.Timeout) as exception:
                return {'stat': 'Not_ok', 'emsg': 'Please Check the Internet connection.', 'encKey': None}
            if response.status_code == 200:
                return json.loads(response.text)
            else:
                emsg=str(response.status_code)+' - '+response.reason
                return {'stat': 'Not_ok', 'emsg': emsg, 'encKey': None}

        elif req_type == "GET":
            try:
                response = requests.get(method, json=data, headers=_headers)
            except (requests.ConnectionError, requests.Timeout) as exception:
                return {'stat': 'Not_ok', 'emsg': 'Please Check the Internet connection.', 'encKey': None}
            return json.loads(response.text)

    def _post(self, sub_url, data=None):
        """Post method declaration"""
        url = self.root_url + self._sub_urls[sub_url]
        return self._request(url, "POST", data=data)

    def get_session_id(self, data=None):
        data = {'userId': self.user_id.upper()}
        response = self._post("ApiEncryptionKey", data)
        if response['encKey'] is None:
            return response['emsg']
        else:
            data = hashlib.sha256((self.user_id.upper() + self.api_key + response['encKey']).encode()).hexdigest()
        data = {'userId': self.user_id.upper(), 'userData': data}
        res = self._post("SessionId", data)

        if res['stat'] == 'Ok':
            self.session_id = res['sessionID']
        return res

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
        if (type(ws) is not websocket.WebSocketApp):  # This workaround is to solve the websocket_client's compatiblity issue of older versions. ie.0.40.0 which is used in upstox. Now this will work in both 0.40.0 & newer version of websocket_client
            error = ws
        if self.__on_error:
            self.__on_error(error)

    def __on_data_callback(self, ws=None, message=None, data_type=None, continue_flag=None):
        # print(ws)
        # print(message)
        # print(data_type)
        # print(continue_flag)
        res = json.loads(message)

        if (self.__subscribe_callback is not None):
            if res['t'] == 'tk' or res['t'] == 'tf':
                self.__subscribe_callback(res)
                return
            if res['t'] == 'dk' or res['t'] == 'df':
                self.__subscribe_callback(res)
                return

        if (self.__on_error is not None):
            if res['t'] == 'ck' and res['s'] != 'OK':
                self.__on_error(res)
                return

        if (self.__order_update_callback is not None):
            if res['t'] == 'om':
                self.__order_update_callback(res)
                return

        if self.__on_open:
            if res['t'] == 'ck' and res['s'] == 'OK':
                self.__on_open()
                return

    def invalidate_socket_session(self):
        url = self._root_url + self._sub_urls["ws_InvalidateSession"]
        headers = {
            'Authorization': 'Bearer ' + self.user_id + ' ' + self.session_id,
            'Content-Type': 'application/json'
        }
        payload = {"loginType": "API"}
        datas = json.dumps(payload)
        response = requests.request("POST", url, headers=headers, data=datas)
        return response.json()

    def create_socket_session(self):
        url = self._root_url + self._sub_urls["ws_CreateSession"]
        headers = {
            'Authorization': 'Bearer ' + self.user_id + ' ' + self.session_id,
            'Content-Type': 'application/json'
        }
        payload = {"loginType": "API"}
        datas = json.dumps(payload)
        response = requests.request("POST", url, headers=headers, data=datas)
        return response.json()

    def start_websocket(self, subscribe_callback=None,
                        order_update_callback=None,
                        socket_open_callback=None,
                        socket_close_callback=None,
                        socket_error_callback=None):
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
        # if run_in_background is True:
        self.__ws_thread = threading.Thread(target=self.__ws_run_forever)
        self.__ws_thread.daemon = True
        self.__ws_thread.start()

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
            self.__subscribes.append(f"{i.exchange}|{i.token}")
        values = ""
        for i in self.__subscribes:
            values += f"{i}#"
        self.__ws_send(json.dumps({
            "k": values[:-1],
            "t": 't'
        }))

    def unsubscribe(self, instrument):
        if type(instrument) is not list:
            instrument = [instrument]
        values = ""
        for i in instrument:
            for i in instrument:
                try:
                    i.exchange, i.token
                except:
                    continue
            i = f"{i.exchange}|{i.token}"
            if i in self.__subscribes:
                values += f"{i}#"
                self.__subscribes.remove(i)
        self.__ws_send(json.dumps({
            "k": values[:-1],
            "t": 'u'
        }))

    def get_scrip_details(self, instrument):
        try:
            instrument.exchange, instrument.token
        except:
            return {'stat': 'Not_Ok', 'emsg': 'Provide Valid Instrument'}
        return self._post("ScripDetails", {"exch":str(instrument.exchange),"symbol":str(instrument.token)})

    def get_trade_book(self):
        return self._get("TradeBook")

    def get_profile(self):
        return self._get("AccountDetails")

    def get_balance(self):
        return self._get("GetLimits")

    def get_holdings(self):
        return self._get("Holdings")

    def get_orderbook(self):
        return self._get("OrderBook")

    def get_order_history(self, nestOrderNumber):
        if nestOrderNumber == '':
            return self._get("OrderBook")
        else:
            return self._get("OrderHistory", {'nestOrderNumber': nestOrderNumber})

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
        return self._post("PlaceOrder", data)

    def cancel_order(self, instrument, nestOrderNumber):
        return self._post("CancelOrder", {'exch': instrument.exchange,
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
        return self._post("ModifyOrder", data)

    def exit_bracket_order(self, nestOrderNumber, symbolOrderId, status, ):
        return self._post("ExitBracketOrder", {'nestOrderNumber': nestOrderNumber,
                                               'symbolOrderId': symbolOrderId,
                                               'status': status, })

    def get_positions(self, position, ):
        return self._post("PositionBook", {'ret': position, })

    def place_basket_order(self, orders):
        data = []
        for i in range(len(orders)):
            order_data = orders[i]
            complexty = order_data['complexty']
            instrument = order_data['instrument']
            product_type = order_data["product_type"]
            price = order_data['price'] if 'price' in order_data else 0
            price_type = order_data['price_type'].value
            quantity = order_data['quantity']
            validity = order_data["validity"]
            transaction_type = order_data['transaction_type'].value
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
                             'trading_symbol': instrument.name,
                             'transtype': transaction_type,
                             "stopLoss": stop_loss,
                             "target": square_off,
                             "trailing_stop_loss": trailing_sl,
                             "trigPrice": trigger_price,
                             "orderTag": order_tag,
                             'complexty': complexty}

            data.append(request_data)
        return self._post("PlaceOrder", data)

    def get_master_contract(self, exchange=None):
        if self.master_contract is None:
            print("Master Contract Downloading(After 8:00am today data available else previous day)....", end="")
            all_Exchanges = ["INDICES", "NSE", "BSE", "NFO", "BCD", "MCX", "CDS", "BFO"]
            for i in all_Exchanges:
                if self.master_contract is None:
                    self.master_contract = pd.read_csv(f"https://v2api.aliceblueonline.com/restpy/static/contract_master/{i}.csv")
                    self.master_contract.columns = self.master_contract.columns.str.title()
                    self.master_contract["Trading Symbol"] = self.master_contract["Symbol"]
                else:
                    self.master_contract = pd.concat([self.master_contract, pd.read_csv(f"https://v2api.aliceblueonline.com/restpy/static/contract_master/{i}.csv")], ignore_index=True)
                    self.master_contract.columns = self.master_contract.columns.str.title()
            self.master_contract = self.master_contract[self.master_contract["Exch"] != ""]
            self.master_contract["Expiry Date"] = self.master_contract["Expiry Date"].apply(lambda x: dateutil.parser.parse(str(x)).date() if str(x).strip() != "nan" and bool(x) else x)
            print("Complected")
        if exchange is None:
            return self.master_contract
        else:
            contract = self.master_contract[self.master_contract['Exch'] == exchange]
            if len(contract) == 0:
                return {"stat": "Not_ok", "emsg": "Provide valid data"}
            else:
                return contract

    def get_instrument_by_symbol(self, exchange, trading_symbol):
        if self.master_contract is None:
            return {"stat": "Not_ok", "emsg": "Download Master Contract First"}
        contract = self.master_contract[self.master_contract['Exch'] == exchange]
        contract = contract[contract["Trading Symbol"] == trading_symbol]
        if len(contract) == 0:
            return {"stat": "Not_ok", "emsg": "Provide valid data"}
        return Instrument(list(contract['Exch'])[0], list(contract['Token'])[0],
                          list(contract['Trading Symbol'])[0], list(contract['Symbol'])[0],
                          list(contract['Expiry Date'])[0], list(contract['Lot Size'])[0])

    def get_instrument_by_token(self, exchange, token):
        if self.master_contract is None:
            return {"stat": "Not_ok", "emsg": "Download Master Contract First"}
        contract = self.master_contract[self.master_contract['Exch'] ==  "NSE" if exchange == self.EXCHANGE_INDICES else exchange]
        contract = contract[contract["Token"] == token]
        if len(contract) == 0:
            return {"stat": "Not_ok", "emsg": "Provide valid data"}
        return Instrument(list(contract['Exch'])[0], list(contract['Token'])[0],
                          list(contract['Trading Symbol'])[0], list(contract['Symbol'])[0],
                          list(contract['Expiry Date'])[0], list(contract['Lot Size'])[0])

    def get_instrument_for_fno(self, exchange, symbol_name, expiry_date, is_fut=True, strike=None, is_CE=False):
        if self.master_contract is None:
            return {"stat": "Not_ok", "emsg": "Download Master Contract First"}
        contract = self.master_contract[self.master_contract['Exch'] == exchange]
        contract = contract[contract["Symbol"] == symbol_name]
        contract = contract[contract["Expiry Date"] == expiry_date]
        if bool(is_fut) or bool(is_CE):
            contract = contract[contract["Option Type"] == "XX" if bool(is_fut) else ("CE" if bool(is_CE) else "PE")]
            if bool(is_CE):
                contract = contract[contract["Strike Price"] == strike]
        if len(contract) == 0:
            return {"stat": "Not_ok", "emsg": "Provide valid data to get particular Instrument"}
        else:
            return Instrument(list(contract['Exch'])[0], list(contract['Token'])[0],
                              list(contract['Trading Symbol'])[0], list(contract['Symbol'])[0],
                              list(contract['Expiry Date'])[0], list(contract['Lot Size'])[0])


