
# Official Python SDK for Alice Blue API V2

The Official Python library for communicating with the Alice Blue APIs.

Alice Blue Python library provides an easy to use wrapper over the HTTPS APIs.

The HTTP calls have been converted to methods and JSON responses are wrapped into Python-compatible objects.

* __Author: [TradeViaPython](https://www.youtube.com/c/TradeViaPython)__
* **Current Version: 1.0.0**

## Installation

This module is installed via:

```
# Copy Code file and put in the same directory where you want to import
```

### Prerequisites

Python >=3.7


* `requests`
* `pandas`
* `websocket_client`

## Getting started with API

### REST Documentation
Alice Blue REST API Documentation : 
   [Alice Blue REST API Documentation](https://v2api.aliceblueonline.com)

## Using the API
### Get a Session ID
1. Import AliceBlue
```python

########################################################################
api_key = "___"         # Get from https://a3.aliceblueonline.com      After Login go to "Apps" section and create API
user_id = "___"

# Login
from AliceBlue import Alice

alice = Alice(user_id=user_id, api_key=api_key)
print(alice.create_session())           # Must "log in" to Alice platform before create session
alice.get_master_contract()

########################################################################
# Basic API Calls
print(alice.get_profile())
print(alice.get_balance())
print(alice.get_orderbook())
print(alice.get_trade_book())
print(alice.get_positions(alice.POSITION_DAYWISE))
print(alice.get_positions(alice.POSITION_NETWISE))
print(alice.get_holdings())

#######################################################################
# Get Master Contract
print(alice.get_master_contract())

# Get specific exchange
print(alice.get_master_contract("NSE"))
print(alice.get_master_contract("NFO"))
print(alice.get_master_contract("MCX"))   # BSE, CDS, BFO also available


import datetime
# Get Instrument
print(alice.get_instrument_by_symbol("NSE", "NIFTY BANK"))                  # NSE Indices NIFTY BANK
print(alice.get_instrument_by_symbol("NSE", "ACC-EQ"))                      # NSE Equity symbol
print(alice.get_instrument_by_symbol("NFO", "NIFTY22AUGFUT"))               # NFO Future symbol
print(alice.get_instrument_by_token("NSE", "3499"))
print(alice.get_instrument_for_fno("NFO", "BANKNIFTY", is_fut=True, expiry_date=datetime.date(2022, 8, 25)))
print(alice.get_instrument_for_fno("NFO", "BANKNIFTY", is_fut=False, expiry_date=datetime.date(2022, 8, 18), strike=39000, is_CE=True))


#########################################################################
# Place Order
order = alice.place_order(transaction_type=alice.TRANSACTION_TYPE_SELL,
                          instrument=alice.get_instrument_by_symbol("NFO", "NIFTY22AUGFUT"),
                          quantity=100,
                          price_type=alice.PRICE_TYPE_LIMIT,
                          product_type=alice.PRODUCT_TYPE_NRML,
                          price=17750,
                          trigger_price=None,
                          stop_loss=None,
                          square_off=None,
                          trailing_sl=None,
                          validity=alice.VALIDITY_IOC,
                          complexty=alice.COMPLEXTY_REGULAR,
                          order_tag="TradeViaPython")
print(order)

###########################################################################
# Modify Order
order = alice.modify_order(nestOrderNumber="22081300001897",
                           transaction_type=alice.TRANSACTION_TYPE_BUY,
                           instrument=alice.get_instrument_by_symbol("NSE", "ACC-EQ"),
                           quantity=10,
                           price_type=alice.PRICE_TYPE_LIMIT,
                           product_type=alice.PRODUCT_TYPE_CNC,
                           price=2227,
                           trigger_price=None)

print(order)

#############################################################################
# Cancel Order
order = alice.cancel_order(nestOrderNumber="220813000001897",
                           instrument=alice.get_instrument_by_symbol("NFO", "NIFTY22AUGFUT"))

print(order)

#############################################################################
# Place Bracket Order
order = alice.place_order(transaction_type=alice.TRANSACTION_TYPE_BUY,
                          instrument=alice.get_instrument_by_symbol("NSE", "RELIANCE-EQ"),
                          quantity=5,
                          price_type=alice.PRICE_TYPE_LIMIT,
                          product_type=alice.PRODUCT_TYPE_MIS,
                          price=2633.0,
                          trigger_price=None,
                          stop_loss=2620,
                          square_off=None,
                          trailing_sl=None,
                          validity=alice.VALIDITY_DAY,
                          complexty=alice.COMPLEXTY_BO,      # COMPLEXTY.AMO  for AMO order
                          order_tag="TradeViaPython")
print(order)

################################################################################
# WEBSOCKET
import time

socket_opened = False


def event_handler_quote_update(message):
    print(message)


def open_callback():
    global socket_opened
    socket_opened = True


alice.invalidate_socket_session()
alice.create_socket_session()
alice.start_websocket(subscribe_callback=event_handler_quote_update,
                      socket_open_callback=open_callback,
                      run_in_background=True)
while not socket_opened:
    pass
print("Websocket : Connected")
alice.subscribe([alice.get_instrument_by_symbol("NSE", i) for i in ["ACC-EQ", "RELIANCE-EQ", "UPL-EQ", "LUPIN-EQ"]])
time.sleep(30)
alice.unsubscribe([alice.get_instrument_by_symbol("NSE", i) for i in ["ACC-EQ", "RELIANCE-EQ"]])
time.sleep(10)


####################################################################################
# Get Historical Data
import datetime

instrument = alice.get_instrument_by_symbol("NSE", "LUPIN-EQ")
from_datetime = datetime.datetime.now() - datetime.timedelta(days=7)     # From last & days
to_datetime = datetime.datetime.now()                                    # To now
interval = "1"       # ["1", "2", "3", "4", "5", "10", "15", "30", "60", "120", "180", "240", "D", "1W", "1M"]
indices = False      # For Getting index data
print(alice.get_historical(instrument, from_datetime, to_datetime, interval, indices))


```

## Read this before creating an issue
Before creating an issue in this library, please follow the following steps.

1. Search the problem you are facing is already asked by someone else. There might be some issues already there, either solved/unsolved related to your problem.
2. If you feel your problem is not asked by anyone or no issues are related to your problem, then create a new issue.
3. Describe your problem in detail while creating the issue. If you don't have time to detail/describe the problem you are facing, assume that I also won't be having time to respond to your problem.
4. Post a sample code of the problem you are facing. If I copy paste the code directly from issue, I should be able to reproduce the problem you are facing.
5. Before posting the sample code, test your sample code yourself once. Only sample code should be tested, no other addition should be there while you are testing.
6. Have some print() function calls to display the values of some variables related to your problem.
7. Post the results of print() functions also in the issue.
8. Use the insert code feature of github to inset code and print outputs, so that the code is displayed neat. ![image](https://user-images.githubusercontent.com/38440742/85207234-4dc96f80-b2f5-11ea-990c-df013dd69cf2.png)
9. If you have multiple lines of code, use triple grave accent ( ``` ) to insert multiple lines of code. [Example:](https://docs.github.com/en/github/writing-on-github/creating-and-highlighting-code-blocks) ![image](https://user-images.githubusercontent.com/38440742/89105781-343a3e00-d3f2-11ea-9f86-92dda88aa5bf.png)
10. [Here](https://github.com/jerokpradeep) is an example of what I'm expecting while you are creating an issue.
