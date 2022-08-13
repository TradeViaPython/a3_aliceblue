from AliceBlue import Alice


api_key = "7h7Ar8FRFoVqUSH9l5vP6Co8icUAg6cocfxDpn7RXtXJzHj7soeiILhzDLXZUdzYcIiH5mMqRGzggy3QZ6VQoDxkIaCVgR4tj1tfDOHV6iOkYPjQmQLgxUDEQ0WN4qsn"
user_id = "273666"

# Login 
alice = Alice(user_id=user_id, api_key=api_key)
alice.get_session_id()

# Basic API Calls
print(alice.get_profile())
print(alice.get_balance())
print(alice.get_orderbook())
print(alice.get_trade_book())
print(alice.get_positions(alice.POSITION_DAYWISE))
print(alice.get_positions(alice.POSITION_NETWISE))
print(alice.get_holdings())

# Download master contract df
print(alice.get_master_contract())

# Get specific exchange data from master contract
print(alice.get_master_contract("NSE"))

# Get specific instrument tuple from master contract
print(alice.get_instrument_by_symbol("NSE", "NIFTY 50"))
print(alice.get_instrument_by_symbol("NSE", "UPL-EQ"))


# Scrip Detail
print(alice.get_scrip_details(alice.get_instrument_by_symbol("NSE", "UPL-EQ")))


# Place Order
order = alice.place_order(transaction_type=alice.TRANSACTION_TYPE_BUY,
                          instrument=alice.get_instrument_by_symbol("NSE", "RELIANCE-EQ"),
                          quantity=5,
                          price_type=alice.PRICE_TYPE_LIMIT,
                          product_type=alice.PRODUCT_TYPE_CNC,
                          price=33.0,
                          trigger_price=None,
                          stop_loss=None,
                          square_off=None,
                          trailing_sl=None,
                          complexty=alice.COMPLEXTY_REGULAR,
                          validity=alice.VALIDITY_DAY
                          order_tag="TradeViaPython")
print(order)



# Place Bracket Order
order = alice.place_order(transaction_type=alice.TRANSACTION_TYPE_BUY,
                          instrument=alice.get_instrument_by_symbol("NSE", "ACC-EQ"),
                          quantity=5,
                          price_type=alice.PRICE_TYPE_LIMIT,
                          product_type=alice.PRODUCT_TYPE_MIS,
                          price=33.0,
                          trigger_price=None,
                          stop_loss=32,
                          square_off=37,
                          trailing_sl=None,
                          complexty=alice.COMPLEXTY_BO,
                          order_tag="TradeViaPython")
print(order)



# Modify Order
order = alice.modify_order(nestOrderNumber="22081300001897",
                           transaction_type=alice.TRANSACTION_TYPE_BUY,
                           instrument=alice.get_instrument_by_symbol("NFO", "NIFTY22AUGFUT"),
                           quantity=50,
                           price_type=alice.PRICE_TYPE_LIMIT,
                           product_type=alice.PRODUCT_TYPE_NRML,
                           price=17800.0,
                           trigger_price=None)
print(order)


# Cancel Order
order = alice.cancel_order(nestOrderNumber="220813000001897",
                           instrument=alice.get_instrument_by_symbol("NFO", "NIFTY22AUGFUT"))
print(order)







print(instrument)
print(alice.get_scrip_details(instrument))


#WEBSOCKET
def start_websocket():
    global socket_opened
    socket_opened = False
    live_data = {}
    keys_values = {"ltp": "lp", "close": "c", "open": "o", "high": "h", "low": "l", "volume": "v", "atp": "ap",  "best_bid_price": "bp1", "best_ask_price": "sp1", "oi": "toi"}

    def event_handler_quote_update(message):
        global live_data
        if f"{message['e']}:{message['ts']}" not in list(live_data.keys()):
            live_data[f"{message['e']}:{message['ts']}"] = {}
        for k, v in keys_values.items():
            try:
                live_data[f"{message['e']}:{message['ts']}"][k] = message[v]
            except:
                live_data[f"{message['e']}:{message['ts']}"][k] = 0
        print(message)

    def open_callback():
        global socket_opened
        socket_opened = True

    alice.invalidate_socket_session()
    alice.create_socket_session()
    alice.start_websocket(subscribe_callback=event_handler_quote_update,
                          socket_open_callback=open_callback)
    while not socket_opened:
        pass
    print("Websocket : Connected")
    alice.subscribe([alice.get_instrument_by_symbol("NSE", i) for i in ["ACC-EQ", "RELIANCE-EQ", "UPL-EQ", "LUPIN-EQ"]])
    time.sleep(30)
    alice.unsubscribe([alice.get_instrument_by_symbol("NSE", i) for i in ["ACC-EQ", "RELIANCE-EQ"]])

start_websocket()
