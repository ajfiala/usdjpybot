import pandas as pd 
import numpy as np
import tpqoa
from datetime import datetime, timedelta
import ta 
import json
import time
import logging

# create logger 
logger = logging.getLogger('MACD_bot')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


class MACDTrader(tpqoa.tpqoa):
    def __init__(self, conf_file, instrument, bar_length, units):
        super().__init__(conf_file)
        self.instrument = instrument
        logger.info(f"Initializing {self.instrument} live trading bot")
        self.bar_length = pd.to_timedelta(bar_length)
        self.tick_data = pd.DataFrame()
        self.raw_data = None
        self.data = None # first defined in get_most_recent
        self.last_bar = None # first defined in get_most_recent
        self.units = units
        self.long_price = 0 
        self.position = 0 
        if self.get_positions():
            for i in self.get_positions():
                if i['instrument'] == self.instrument:
                    logger.info(f"Open positions: {i['long']}")
                    self.position = 1
                    logger.info(f"open long position: {self.position}")
        else:
            logger.info(f"No open positions: {self.get_positions()}")
        self.profits = []
        #*********************** Trading Strategy Specific Attributes ***************
        
        
    def get_most_recent(self, days = 100):
        while True: # repeat until we get all historical bars
            time.sleep(2)
            logger.info("retrieving historical data")
            now = datetime.utcnow()
            now = now - timedelta(microseconds = now.microsecond)
            past = now - timedelta(days = days)
            try:
                # H1
                df = self.get_history(instrument = self.instrument, start = past, end = now,
                                    granularity = "D", price = "M", localize = False).c.dropna().to_frame()
            except Exception as ex:
                print(f"Exception occurred retrieving data: {ex}")
            df.rename(columns = {"c":self.instrument}, inplace = True)
            df['MACD'] = ta.trend.MACD(close=df[self.instrument]).macd()
            df['MACD_signal'] = ta.trend.MACD(close=df[self.instrument]).macd_signal()
            df = df.resample(self.bar_length, label = "right").last().dropna().iloc[:-1]
            self.data = df.copy() # first defined
            self.last_bar = self.data.index[-1] # first defined 
            # accept, if leff than [bar_length] has elapsed since the last full historical
            # bar and now
            # print(pd.to_datetime(datetime.utcnow()).tz_localize("UTC") - self.last_bar)
            # print(self.last_bar)
            # print(self.last_bar)
            # print(pd.to_datetime(datetime.utcnow()).tz_localize("UTC"))
            # print(self.bar_length)
            # daily so .today() instaed of utcnow()
            # doesn't work in container 
            # if pd.to_datetime(datetime.today()).tz_localize("UTC") - self.last_bar <= self.bar_length:
            #     break
            break
        
    def on_success(self, time, bid, ask):
        # print(self.ticks, end = " ")
        # collect and store tick data
        recent_tick = pd.to_datetime(time)
        df = pd.DataFrame({self.instrument:(ask + bid)/2},
                         index = [recent_tick])
        df['MACD'] = ta.trend.MACD(close=df[self.instrument]).macd()
        df['MACD_signal'] = ta.trend.MACD(close=df[self.instrument]).macd_signal()
        self.tick_data = pd.concat([self.tick_data, df])
        # if a time longer than the bar length has elapsed between last full bar and most recent tick, 
        # resample and join
        if recent_tick - self.last_bar > self.bar_length:
            self.resample_and_join()
            self.define_strategy()
            # print(f"price: {self.data[self.instrument].iloc[-1]} MACD: {self.data['MACD'].iloc[-1]} MACD_signal: {self.data['MACD_signal'].iloc[-1]} " +   
            #       f"EMA5: {self.data['ema5'].iloc[-1]} EMA10: {self.data['ema10'].iloc[-1]}")
            self.execute_trades()
            
    def define_strategy(self):
        df = self.raw_data.copy() # self.raw_data
        df['MACD'] = ta.trend.MACD(close=df[self.instrument]).macd()
        df['MACD_signal'] = ta.trend.MACD(close=df[self.instrument]).macd_signal()
        df['ema5'] = ta.trend.EMAIndicator(close=df[self.instrument],window=5).ema_indicator()
        df['ema10'] = ta.trend.EMAIndicator(close=df[self.instrument],window=10).ema_indicator()
        self.data = df.copy()
        
    def resample_and_join(self):
        #self.data = self.tick_data.resample(self.bar_length, label = "right")
        #append most recent resampled ticks to self.data
        self.raw_data = pd.concat([self.data, self.tick_data.resample(self.bar_length, label="right").last().ffill().iloc[:-1]])
        self.tick_data = self.tick_data.iloc[-1:]
        self.last_bar = self.data.index[-1] # raw
        
        
        

    def execute_trades(self):
        if np.logical_and(self.data['MACD'].iloc[-2] < self.data['MACD_signal'].iloc[-2], self.data['MACD'].iloc[-1] > self.data['MACD_signal'].iloc[-1]): # if position is long, go/stay long
            if self.position == 0:
                order = self.create_order(self.instrument, self.units, suppress = True, ret = True)
                self.report_trade(order, "OPENING LONG")
                self.long_price = order['price']
            self.position = 1
        elif np.logical_and(self.data['MACD'].iloc[-2] > self.data['MACD_signal'].iloc[-2], self.data['MACD'].iloc[-1] < self.data['MACD_signal'].iloc[-1]): # if position is short, go/stay short
            if self.position == 1:
                if self.data[self.instrument].iloc[-1] > self.long_price:
                    order = self.create_order(self.instrument, -self.units, suppress = True, ret = True)
                    self.report_trade(order, "CLOSING LONG")
            self.position = 0
            self.long_price = 0 



    def report_trade(self, order, going):
        time = order["time"]
        units = order['units']
        price = order['price']
        pl = float(order['pl'])
        self.profits.append(pl)
        cumpl = sum(self.profits)
        print("\n" + 100 * "-")
        logger.info(f"{time} | {going}")
        logger.info(f"MACD: {self.data['MACD'].iloc[-1]} MACD_signal: {self.data['MACD_signal'].iloc[-1]}")
        logger.info(f"{time} | units = {units} | price = {price} | P&L = {pl} | cum P&L = {cumpl}")
        print(100 * "-" + "\n")
        



if __name__ == "__main__":
    trader = MACDTrader("oanda_live.cfg", "USD_JPY", "1Day", units = 7000)
    try:
        trader.get_most_recent()
    except Exception as ex:
        logger.error(f"Exception raised while retrieving historical data: {ex}")
    try:
         trader.stream_data(trader.instrument, ret=True)
    except Exception as ex:
         logger.error(f"Error occured streaming data: {ex}")
